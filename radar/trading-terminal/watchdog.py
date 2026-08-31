"""
watchdog.py — guarda-costas silencioso do O Código 3:1.

Conforme dossiê v1.1 Seção 13.

Princípio: se o terminal está funcionando, SILÊNCIO.
           Se travar (heartbeat > 10 min sem atualizar), Telegram crítico.

Uso:
  python3 watchdog.py                         # apenas alerta crítico
  python3 watchdog.py --summary-hours 3       # resumo OK a cada 3h também
  python3 watchdog.py --once                  # uma checagem só (testes/cron)
  python3 watchdog.py --check-interval 60     # checa a cada 60s (default 300)
  python3 watchdog.py --alert-threshold 5     # alerta se heartbeat > 5min (default 10)
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"
HEARTBEAT_FILE = LOG_DIR / "heartbeat.json"
WATCHDOG_STATE_FILE = LOG_DIR / "watchdog_state.json"


# ─── Carregar .env (mesmo padrão do live_daemon) ─────────────────────
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
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


# ─── Telegram envio direto (sem dependência de telegram_client) ──────
def send_telegram(message: str, bot_token: Optional[str] = None,
                  chat_id: Optional[str] = None) -> bool:
    """Envia mensagem via HTTP direto à API do Telegram. Sem deps externas."""
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": message,
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False
    except Exception:
        return False


# ─── State persistence (anti-spam) ──────────────────────────────────
def _load_state() -> dict:
    if not WATCHDOG_STATE_FILE.exists():
        return {
            "critical_alert_sent": False,
            "critical_alert_at": None,
            "last_seen_scan_at": None,
            "last_summary_at": None,
            "summary_window_scan_count": 0,
            "summary_window_telegram_total": 0,
        }
    try:
        return json.loads(WATCHDOG_STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {
            "critical_alert_sent": False,
            "critical_alert_at": None,
            "last_seen_scan_at": None,
            "last_summary_at": None,
            "summary_window_scan_count": 0,
            "summary_window_telegram_total": 0,
        }


def _save_state(state: dict) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    with open(WATCHDOG_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


# ─── Watchdog principal ──────────────────────────────────────────────
class Watchdog:
    """Lê heartbeat.json e decide se há alerta a enviar.

    Não envia "estou vivo" por padrão. Apenas crítico quando heartbeat trava.
    Resumo OK só sai se --summary-hours N for passado.
    """

    def __init__(self, *,
                 alert_threshold_minutes: int = 10,
                 check_interval_seconds: int = 300,
                 summary_hours: Optional[int] = None,
                 heartbeat_path: Optional[Path] = None,
                 state_path: Optional[Path] = None,
                 telegram_sender=None,
                 now_fn=None):
        self.alert_threshold = timedelta(minutes=alert_threshold_minutes)
        self.check_interval = max(5, int(check_interval_seconds))
        self.summary_hours = summary_hours
        self.heartbeat_path = Path(heartbeat_path) if heartbeat_path else HEARTBEAT_FILE
        self.state_path = Path(state_path) if state_path else WATCHDOG_STATE_FILE
        self.telegram_sender = telegram_sender or send_telegram
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    # ─── Persistence (delegate para o módulo, mas pode usar path custom)
    def _load_state(self) -> dict:
        if not self.state_path.exists():
            return {
                "critical_alert_sent": False,
                "critical_alert_at": None,
                "last_seen_scan_at": None,
                "last_summary_at": None,
                "summary_window_scan_count": 0,
                "summary_window_telegram_total": 0,
            }
        try:
            return json.loads(self.state_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {
                "critical_alert_sent": False,
                "critical_alert_at": None,
                "last_seen_scan_at": None,
                "last_summary_at": None,
                "summary_window_scan_count": 0,
                "summary_window_telegram_total": 0,
            }

    def _save_state(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    # ─── Mensagens
    def _build_critical_message(self, heartbeat: dict, minutes_since: int) -> str:
        last_scan_at = heartbeat.get("last_scan_at", "?")
        games_scanned = heartbeat.get("games_scanned", "?")
        return (
            "🔴 ALERTA — O CÓDIGO 3:1\n"
            "O terminal pode ter parado ou travado.\n"
            "\n"
            f"Último scan: {last_scan_at}\n"
            f"Tempo sem heartbeat: {minutes_since} min\n"
            f"Jogos escaneados no último ciclo: {games_scanned}\n"
            "\n"
            "Comando: VERIFICAR TERMINAL."
        )

    def _build_summary_message(self, heartbeat: dict, hours: int,
                                scan_count: int, telegram_total: int) -> str:
        last_scan_at = heartbeat.get("last_scan_at", "?")
        mode = heartbeat.get("mode", "?")
        return (
            "🟢 STATUS — O CÓDIGO 3:1\n"
            "Terminal operando normalmente.\n"
            "\n"
            f"Último scan: {last_scan_at}\n"
            f"Modo: {mode}\n"
            f"Scans nas últimas {hours}h: {scan_count}\n"
            f"Alertas enviados nas últimas {hours}h: {telegram_total}"
        )

    # ─── Checagem (lógica isolada — testável)
    def check(self) -> dict:
        """Executa UMA checagem. Retorna dict com o que aconteceu.

        Returns:
            {
                "status": "ok" | "critical" | "no_heartbeat" | "recovered" | "summary",
                "sent_critical": bool,
                "sent_summary": bool,
                "minutes_since": int | None,
            }
        """
        result = {
            "status": "ok",
            "sent_critical": False,
            "sent_summary": False,
            "minutes_since": None,
        }
        state = self._load_state()
        now = self.now_fn()

        # ─── Caso 1: heartbeat não existe ───────────────────────
        if not self.heartbeat_path.exists():
            result["status"] = "no_heartbeat"
            # Se for a primeira execução do watchdog, não sabemos se o daemon
            # ainda nem começou. Não envia alerta — espera próxima checagem.
            return result

        try:
            heartbeat = json.loads(self.heartbeat_path.read_text())
        except (json.JSONDecodeError, OSError):
            result["status"] = "no_heartbeat"
            return result

        last_scan_at = _parse_iso(heartbeat.get("last_scan_at"))
        if last_scan_at is None:
            result["status"] = "no_heartbeat"
            return result

        delta = now - last_scan_at
        minutes_since = max(0, int(delta.total_seconds() // 60))
        result["minutes_since"] = minutes_since

        # ─── Recuperação: heartbeat voltou a atualizar
        if state.get("critical_alert_sent") and delta < self.alert_threshold:
            # Terminal voltou — reseta o flag de alerta crítico
            state["critical_alert_sent"] = False
            state["critical_alert_at"] = None
            result["status"] = "recovered"

        # ─── Atualiza last_seen e contadores acumulados pra summary
        last_seen = state.get("last_seen_scan_at")
        if last_seen != heartbeat.get("last_scan_at"):
            # Novo scan desde a última checagem
            state["last_seen_scan_at"] = heartbeat.get("last_scan_at")
            state["summary_window_scan_count"] = int(state.get("summary_window_scan_count", 0)) + 1
            state["summary_window_telegram_total"] = (
                int(state.get("summary_window_telegram_total", 0))
                + int(heartbeat.get("telegram_sent_last_cycle", 0))
            )

        # ─── Crítico: heartbeat atrasado
        if delta >= self.alert_threshold:
            if not state.get("critical_alert_sent"):
                msg = self._build_critical_message(heartbeat, minutes_since)
                if self.telegram_sender(msg):
                    state["critical_alert_sent"] = True
                    state["critical_alert_at"] = now.isoformat()
                    result["sent_critical"] = True
                    result["status"] = "critical"
            else:
                # Anti-spam: já alertou, não reenvia
                result["status"] = "critical"
            self._save_state(state)
            return result

        # ─── Summary OK (opcional, só com --summary-hours)
        if self.summary_hours and self.summary_hours > 0:
            last_summary = _parse_iso(state.get("last_summary_at"))
            summary_due = (
                last_summary is None
                or (now - last_summary) >= timedelta(hours=self.summary_hours)
            )
            if summary_due:
                msg = self._build_summary_message(
                    heartbeat,
                    self.summary_hours,
                    int(state.get("summary_window_scan_count", 0)),
                    int(state.get("summary_window_telegram_total", 0)),
                )
                if self.telegram_sender(msg):
                    state["last_summary_at"] = now.isoformat()
                    state["summary_window_scan_count"] = 0
                    state["summary_window_telegram_total"] = 0
                    result["sent_summary"] = True
                    result["status"] = "summary"

        self._save_state(state)
        return result

    def run_forever(self):
        """Loop infinito — verifica heartbeat a cada check_interval segundos."""
        print(f"  Watchdog do O CÓDIGO 3:1 iniciado.")
        print(f"  Heartbeat: {self.heartbeat_path}")
        print(f"  Check interval: {self.check_interval}s")
        print(f"  Alert threshold: {int(self.alert_threshold.total_seconds() // 60)} min")
        if self.summary_hours:
            print(f"  Summary OK: a cada {self.summary_hours}h")
        else:
            print(f"  Summary OK: desativado (use --summary-hours N pra habilitar)")
        print(f"  Parar: Ctrl+C")
        print()
        while True:
            try:
                result = self.check()
                ts = datetime.now().strftime("%H:%M:%S")
                if result["status"] == "critical" and result["sent_critical"]:
                    print(f"  [{ts}] 🔴 ALERTA CRÍTICO enviado — {result['minutes_since']} min sem heartbeat")
                elif result["status"] == "critical":
                    print(f"  [{ts}] 🔴 ainda crítico ({result['minutes_since']}min) — anti-spam ativo")
                elif result["status"] == "recovered":
                    print(f"  [{ts}] 🟢 terminal recuperou")
                elif result["status"] == "summary" and result["sent_summary"]:
                    print(f"  [{ts}] 🟢 resumo OK enviado")
                elif result["status"] == "no_heartbeat":
                    print(f"  [{ts}] ⏳ aguardando primeiro heartbeat do daemon")
                else:
                    # OK silencioso
                    pass
                time.sleep(self.check_interval)
            except KeyboardInterrupt:
                print("\n  Watchdog finalizado.")
                return


# ─── CLI ─────────────────────────────────────────────────────────────
def main():
    _load_env()
    parser = argparse.ArgumentParser(
        description="Watchdog silencioso do O Código 3:1 (dossiê v1.1 Seção 13)."
    )
    parser.add_argument("--alert-threshold", type=int, default=15,
                        help="Minutos sem heartbeat pra disparar crítico (default: 15). "
                             "Self-watchdog do daemon mata em 8min e restart leva ~10s, "
                             "então 15min dá margem segura contra falso positivo.")
    parser.add_argument("--check-interval", type=int, default=300,
                        help="Segundos entre checagens (default: 300 = 5 min)")
    parser.add_argument("--summary-hours", type=int, default=None,
                        help="Se passado, envia resumo OK a cada N horas. "
                             "Sem essa flag, watchdog é silencioso em estado saudável.")
    parser.add_argument("--once", action="store_true",
                        help="Roda uma checagem só e sai (testes/cron).")
    parser.add_argument("--heartbeat-path", default=None,
                        help="Override pro caminho do heartbeat.json (testes).")
    parser.add_argument("--state-path", default=None,
                        help="Override pro caminho do watchdog_state.json (testes).")
    args = parser.parse_args()

    w = Watchdog(
        alert_threshold_minutes=args.alert_threshold,
        check_interval_seconds=args.check_interval,
        summary_hours=args.summary_hours,
        heartbeat_path=Path(args.heartbeat_path) if args.heartbeat_path else None,
        state_path=Path(args.state_path) if args.state_path else None,
    )

    if args.once:
        result = w.check()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    w.run_forever()


if __name__ == "__main__":
    main()
