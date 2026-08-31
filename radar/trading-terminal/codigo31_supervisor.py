"""
codigo31_supervisor.py — SUPERVISOR EXTERNO do CÓDIGO 3:1.

Princípio: NÃO confiar que o daemon vai se salvar sozinho.
Processo pai independente que sobe, vigia e MATA + REINICIA o daemon
quando ele trava (Playwright em deadlock).

Fluxo:
  [supervisor]
      │
      ├─ fork→ python3 live_daemon.py ... (process group próprio)
      │
      ├─ loop: ler logs/heartbeat.json
      │   • se não existe após STARTUP_TIMEOUT → kill+restart
      │   • se last_scan_at > STALE_THRESHOLD → kill+restart
      │
      ├─ kill: SIGTERM ao grupo inteiro → wait 10s → SIGKILL se necessário
      │   (mata Playwright/Chromium órfãos juntos)
      │
      ├─ rate limit: máx 10 restarts/hora — se estourar, supervisor para
      │
      └─ Telegram:
           • 🔴 ALERTA — SUPERVISOR CÓDIGO 3:1   (a cada restart por travamento)
           • 🟢 CÓDIGO 3:1 RECUPERADO            (1× quando heartbeat volta)

Uso:
  python3 codigo31_supervisor.py
  python3 codigo31_supervisor.py --no-telegram   # debug
  python3 codigo31_supervisor.py --once          # 1 ciclo (testes/CI)
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Tuple


# ─── Paths e constantes ────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
HEARTBEAT_FILE = LOG_DIR / "heartbeat.json"
SUPERVISOR_LOG = LOG_DIR / "codigo31_supervisor.log"
SUPERVISOR_STATE = LOG_DIR / "codigo31_supervisor_state.json"

# Parâmetros (override por argparse)
DEFAULT_STARTUP_TIMEOUT_S = 420   # 7 min até primeiro heartbeat
DEFAULT_STALE_HEARTBEAT_S = 600   # 10 min sem atualizar = travado
DEFAULT_RESTART_SLEEP_S = 10
DEFAULT_MAX_RESTARTS_PER_HOUR = 10
DEFAULT_CHECK_INTERVAL_S = 30

DAEMON_CMD = [
    "python3", "live_daemon.py",
    "--send-telegram", "--use-watchlist", "--mode", "codigo_3_1",
    "--interval", "120", "--max-games", "20",
]


# ─── .env loader (mesmo padrão do watchdog) ────────────────────────────
def _load_env() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ─── Telegram (sem deps externas) ──────────────────────────────────────
def _send_telegram_default(msg: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat, "text": msg, "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception:
        return False


# ─── Função pura de decisão (testável) ─────────────────────────────────
def evaluate_supervisor_state(
    *,
    now_utc: datetime,
    daemon_start_utc: Optional[datetime],
    heartbeat_path: Path,
    startup_timeout_s: int,
    stale_heartbeat_s: int,
) -> Tuple[bool, str]:
    """Retorna (restart_now: bool, reason: str).

    Casos:
      A) daemon não foi iniciado ainda → restart=True, reason='not_started'
      B) heartbeat NÃO existe e startup_timeout passou → restart, reason='startup_timeout_no_heartbeat'
      C) heartbeat NÃO existe mas ainda dentro do startup_timeout → não, reason='starting_up'
      D) heartbeat existe mas anterior ao daemon_start → restart, reason='stale_pre_start'
         (somente se startup_timeout passou — daemon teve tempo de escrever um novo)
      E) heartbeat existe e age > stale_heartbeat_s → restart, reason='heartbeat_stale'
      F) heartbeat existe e age ≤ stale_heartbeat_s → não, reason='healthy'
    """
    if daemon_start_utc is None:
        return True, "not_started"

    elapsed = (now_utc - daemon_start_utc).total_seconds()

    if not heartbeat_path.exists():
        if elapsed >= startup_timeout_s:
            return True, "startup_timeout_no_heartbeat"
        return False, "starting_up"

    try:
        hb = json.loads(heartbeat_path.read_text())
        ts = hb.get("last_scan_at", "")
        if not ts:
            return True, "heartbeat_no_timestamp"
        last = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception as e:
        return True, f"heartbeat_unreadable:{type(e).__name__}"

    # Heartbeat é anterior ao processo atual (de daemon anterior)
    if last < daemon_start_utc:
        if elapsed >= startup_timeout_s:
            return True, "stale_pre_start"
        return False, "starting_up_old_heartbeat"

    age = (now_utc - last).total_seconds()
    if age > stale_heartbeat_s:
        return True, f"heartbeat_stale_{int(age)}s"
    return False, "healthy"


# ─── Rate limit (testável) ─────────────────────────────────────────────
def is_rate_limited(restart_times: deque, now_utc: datetime, max_per_hour: int) -> bool:
    """Verifica se já estamos no limite de restarts/hora."""
    one_h_ago = now_utc - timedelta(hours=1)
    while restart_times and restart_times[0] < one_h_ago:
        restart_times.popleft()
    return len(restart_times) >= max_per_hour


# ─── Logger estruturado ────────────────────────────────────────────────
def _log(event: str, **fields):
    line = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SUPERVISOR_LOG, "a") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    # também imprime
    print(f"[supervisor] {event}  {fields if fields else ''}", flush=True)


# ─── Supervisor principal ──────────────────────────────────────────────
class Codigo31Supervisor:
    def __init__(
        self,
        *,
        startup_timeout_s: int = DEFAULT_STARTUP_TIMEOUT_S,
        stale_heartbeat_s: int = DEFAULT_STALE_HEARTBEAT_S,
        restart_sleep_s: int = DEFAULT_RESTART_SLEEP_S,
        max_restarts_per_hour: int = DEFAULT_MAX_RESTARTS_PER_HOUR,
        check_interval_s: int = DEFAULT_CHECK_INTERVAL_S,
        heartbeat_path: Path = HEARTBEAT_FILE,
        daemon_cmd: list = None,
        telegram_sender=None,
        send_telegram_enabled: bool = True,
        now_fn=None,
        spawn_fn=None,
        kill_fn=None,
    ):
        self.startup_timeout_s = startup_timeout_s
        self.stale_heartbeat_s = stale_heartbeat_s
        self.restart_sleep_s = restart_sleep_s
        self.max_restarts_per_hour = max_restarts_per_hour
        self.check_interval_s = check_interval_s
        self.heartbeat_path = Path(heartbeat_path)
        self.daemon_cmd = daemon_cmd or DAEMON_CMD
        self.send_telegram = telegram_sender or _send_telegram_default
        self.telegram_enabled = send_telegram_enabled
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.spawn_fn = spawn_fn or self._spawn_daemon
        self.kill_fn = kill_fn or self._kill_process_group

        # State
        self.proc = None           # subprocess.Popen
        self.daemon_start_utc = None
        self.restart_times = deque()
        self.last_recovered_alert_for = None  # pra dedup recovery
        self.in_critical_state = False        # pra não spammar
        self.restart_count = 0
        self._stopped = False

    # ─── Process management ──────────────────────────────────────────
    def _spawn_daemon(self) -> subprocess.Popen:
        """Inicia daemon como processo filho com process group próprio.

        os.setsid() cria nova sessão e process group, garantindo que
        kill no grupo inteiro alcance Playwright/Chromium órfãos.
        """
        return subprocess.Popen(
            self.daemon_cmd,
            cwd=str(BASE_DIR),
            preexec_fn=os.setsid,   # POSIX: cria novo process group
            stdout=sys.stdout,
            stderr=sys.stderr,
        )

    def _kill_process_group(self, proc: subprocess.Popen) -> str:
        """Mata o process group inteiro do daemon.

        SIGTERM → espera 10s → SIGKILL se ainda vivo.
        Retorna string descrevendo o que foi feito.
        """
        if proc is None or proc.poll() is not None:
            return "already_dead"

        pgid = None
        try:
            pgid = os.getpgid(proc.pid)
        except (ProcessLookupError, OSError):
            return "process_gone"

        # SIGTERM no grupo
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return "process_gone"
        except OSError as e:
            return f"sigterm_error:{e}"

        # Espera até 10s
        for _ in range(20):
            if proc.poll() is not None:
                return "sigterm_ok"
            time.sleep(0.5)

        # SIGKILL no grupo
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return "sigkill_required"

    # ─── Telegram helpers ────────────────────────────────────────────
    # v2.5: Telegram técnico DESLIGADO por default. Telegram é exclusivo da
    # Regra 3.1.2.0. Alertas de supervisor ficam em logs/codigo31_supervisor.log.
    # Pra reativar TG técnico em debug: export TECHNICAL_TELEGRAM_ENABLED=1.
    def _alert_critical(self, reason: str, last_scan_at: str):
        if not self.telegram_enabled:
            return
        try:
            from src.operational_config import supervisor_telegram_enabled
            if not supervisor_telegram_enabled():
                _log("telegram_critical_suppressed",
                      reason=reason, policy="technical_telegram_disabled")
                return
        except ImportError:
            return  # fail-closed se módulo ausente — não vaza TG técnico
        msg = (
            "🔴 ALERTA — SUPERVISOR CÓDIGO 3:1\n"
            "O daemon travou e foi reiniciado automaticamente.\n"
            f"Motivo: {reason}\n"
            f"Último heartbeat: {last_scan_at}\n"
            f"Restart nº: {self.restart_count}\n"
            "Comando: NENHUMA AÇÃO — supervisor já reiniciou."
        )
        ok = self.send_telegram(msg)
        _log("telegram_critical_sent", sent=ok, reason=reason)

    def _alert_recovered(self, last_scan_at: str):
        if not self.telegram_enabled:
            return
        try:
            from src.operational_config import supervisor_telegram_enabled
            if not supervisor_telegram_enabled():
                _log("telegram_recovered_suppressed",
                      policy="technical_telegram_disabled")
                return
        except ImportError:
            return  # fail-closed
        # Dedup: só envia recovery UMA vez por travamento
        if self.last_recovered_alert_for == self.restart_count:
            return
        msg = (
            "🟢 CÓDIGO 3:1 RECUPERADO\n"
            "O daemon voltou a atualizar heartbeat.\n"
            f"Último scan: {last_scan_at}"
        )
        ok = self.send_telegram(msg)
        self.last_recovered_alert_for = self.restart_count
        _log("telegram_recovered_sent", sent=ok)

    # ─── Ciclo único de verificação ──────────────────────────────────
    def check_once(self) -> dict:
        """Uma rodada de verificação. Retorna dict de status."""
        now = self.now_fn()

        # Se nunca iniciou ou processo morreu sozinho → start
        if self.proc is None or self.proc.poll() is not None:
            self._do_restart(now, reason="initial_start" if self.proc is None else "process_died")
            return {"action": "started", "now": now.isoformat()}

        # Avalia estado
        kill, reason = evaluate_supervisor_state(
            now_utc=now,
            daemon_start_utc=self.daemon_start_utc,
            heartbeat_path=self.heartbeat_path,
            startup_timeout_s=self.startup_timeout_s,
            stale_heartbeat_s=self.stale_heartbeat_s,
        )

        if not kill:
            # Saudável — se estava em estado crítico, mandar recovery
            if self.in_critical_state and reason == "healthy":
                last_scan_at = self._read_last_scan_at()
                self._alert_recovered(last_scan_at)
                self.in_critical_state = False
            return {"action": "ok", "reason": reason, "now": now.isoformat()}

        # Travado — verifica rate limit antes de matar
        if is_rate_limited(self.restart_times, now, self.max_restarts_per_hour):
            _log("rate_limit_hit", reason=reason,
                 restarts_last_hour=len(self.restart_times))
            return {"action": "rate_limited", "reason": reason}

        self._do_restart(now, reason=reason)
        return {"action": "restarted", "reason": reason, "now": now.isoformat()}

    def _do_restart(self, now: datetime, reason: str):
        # Pega heartbeat ANTES de matar (pra mensagem)
        last_scan_at = self._read_last_scan_at()

        # Mata o atual se existe
        if self.proc and self.proc.poll() is None:
            kill_result = self.kill_fn(self.proc)
            _log("killed_daemon", pid=self.proc.pid, reason=reason, result=kill_result)
            self.in_critical_state = True
            self.restart_count += 1

            # Alerta crítico
            self._alert_critical(reason, last_scan_at or "nunca escrito")

            # Sleep entre restarts
            time.sleep(self.restart_sleep_s)
        else:
            self.restart_count += 1

        # Sobe novo daemon
        self.proc = self.spawn_fn()
        self.daemon_start_utc = now
        self.restart_times.append(now)
        _log("started_daemon", pid=self.proc.pid,
             restart_count=self.restart_count, reason=reason)

    def _read_last_scan_at(self) -> Optional[str]:
        try:
            return json.loads(self.heartbeat_path.read_text()).get("last_scan_at")
        except Exception:
            return None

    def stop(self):
        self._stopped = True
        if self.proc and self.proc.poll() is None:
            _log("supervisor_stopping", pid=self.proc.pid)
            self.kill_fn(self.proc)

    # ─── Loop principal ──────────────────────────────────────────────
    def run_forever(self):
        _log("supervisor_started",
             startup_timeout_s=self.startup_timeout_s,
             stale_heartbeat_s=self.stale_heartbeat_s,
             max_restarts_per_hour=self.max_restarts_per_hour)

        def _shutdown_handler(signum, frame):
            _log("supervisor_signal", sig=signum)
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown_handler)
        signal.signal(signal.SIGTERM, _shutdown_handler)

        try:
            while not self._stopped:
                status = self.check_once()
                time.sleep(self.check_interval_s)
        finally:
            self.stop()


# ─── CLI ───────────────────────────────────────────────────────────────
def main():
    _load_env()
    p = argparse.ArgumentParser(
        description="Supervisor externo do CÓDIGO 3:1 (anti-travamento Playwright)"
    )
    p.add_argument("--startup-timeout", type=int, default=DEFAULT_STARTUP_TIMEOUT_S,
                   help=f"Segundos até primeiro heartbeat (default: {DEFAULT_STARTUP_TIMEOUT_S})")
    p.add_argument("--stale-heartbeat", type=int, default=DEFAULT_STALE_HEARTBEAT_S,
                   help=f"Segundos sem atualizar = travado (default: {DEFAULT_STALE_HEARTBEAT_S})")
    p.add_argument("--restart-sleep", type=int, default=DEFAULT_RESTART_SLEEP_S,
                   help=f"Segundos entre kill e novo start (default: {DEFAULT_RESTART_SLEEP_S})")
    p.add_argument("--max-restarts-per-hour", type=int, default=DEFAULT_MAX_RESTARTS_PER_HOUR,
                   help=f"Máximo restarts por hora (default: {DEFAULT_MAX_RESTARTS_PER_HOUR})")
    p.add_argument("--check-interval", type=int, default=DEFAULT_CHECK_INTERVAL_S,
                   help=f"Segundos entre checagens (default: {DEFAULT_CHECK_INTERVAL_S})")
    p.add_argument("--no-telegram", action="store_true",
                   help="Não enviar Telegram (debug)")
    p.add_argument("--once", action="store_true",
                   help="Uma checagem só e sai (CI/testes)")
    args = p.parse_args()

    sup = Codigo31Supervisor(
        startup_timeout_s=args.startup_timeout,
        stale_heartbeat_s=args.stale_heartbeat,
        restart_sleep_s=args.restart_sleep,
        max_restarts_per_hour=args.max_restarts_per_hour,
        check_interval_s=args.check_interval,
        send_telegram_enabled=not args.no_telegram,
    )

    print(f"  Supervisor do CÓDIGO 3:1 iniciando.")
    print(f"  Startup timeout:  {args.startup_timeout}s ({args.startup_timeout/60:.1f}min)")
    print(f"  Stale heartbeat:  {args.stale_heartbeat}s ({args.stale_heartbeat/60:.1f}min)")
    print(f"  Max restarts/h:   {args.max_restarts_per_hour}")
    print(f"  Telegram:         {'ATIVO' if not args.no_telegram else 'DESATIVADO'}")
    print(f"  Heartbeat:        {HEARTBEAT_FILE}")
    print(f"  Log:              {SUPERVISOR_LOG}")
    print(f"  Parar:            Ctrl+C")
    print()

    if args.once:
        status = sup.check_once()
        print(json.dumps(status, indent=2, default=str))
        sup.stop()
        return 0

    sup.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
