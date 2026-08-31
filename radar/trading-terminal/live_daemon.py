"""
Live Daemon — Etapa 4B do Trading Terminal V1.2

Loop automático:
  1. Descobre jogos ao vivo no Flashscore (ou recebe URLs fixas)
  2. Extrai stats de cada jogo via Playwright
  3. Roda run_scan() do Motor V1.2
  4. Salva log JSONL + estado JSON
  5. Envia Telegram com tag [SIMULAÇÃO]
  6. Repete a cada N segundos

Rodar:
  python3 live_daemon.py                          # auto-discover, sem Telegram
  python3 live_daemon.py --send-telegram           # auto-discover + Telegram
  python3 live_daemon.py --urls "url1,url2"        # URLs fixas
  python3 live_daemon.py --urls-file jogos.txt     # URLs de arquivo
  python3 live_daemon.py --interval 180            # a cada 3 min

Parar: Ctrl+C (shutdown limpo após ciclo atual)

SEM LIVE real. SEM execução de aposta. SEM odd/preço/EV.
mode: simulation. Tag: [SIMULAÇÃO].
"""
import os
import sys
import json
import signal
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

# ─── Carregar .env (formato: export VAR="val" ou VAR="val") ──────────
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Remove "export " prefix se existir
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)

from src.models import MatchState
from src.decision_engine import run_scan, load_config
from src.telegram_client import TelegramClient
from src.flashscore_adapter import FlashscoreReader

# Modo watchlist (opcional, ativado via --use-watchlist)
from src.catalog import Catalog
from src.watchlist import build_watchlist
from src.discovery import discover_live_games

# Código 3:1 — A Matriz das Chances Claras (agente simples de alerta)
from src import codigo_3_1

# Regra 3.1.2.0 Turbo — DRY-RUN/AUDIT continua appendando em
# logs/triple_debt_audit.jsonl para calibração.
from src.triple_debt_filter import (
    validate_triple_debt_filter as _triple_debt_validate,
    audit_log as _triple_debt_audit_log,
)
# Regra 3.1.2.0 Turbo — ENFORCEMENT ON. evaluate_turbo() decide se o
# candidato pode ir pro Telegram. Falha fechada (erro → bloqueia).
# Banco append-only de near misses + sidecar de approved.
from src.turbo_enforcement import (
    evaluate_turbo as _turbo_evaluate,
    build_near_miss_record as _turbo_build_near_miss,
    build_approved_record as _turbo_build_approved,
    near_miss_log as _turbo_near_miss_log,
    approved_signal_log as _turbo_approved_log,
    FINAL_SENT as _TURBO_FINAL_SENT,
    FINAL_RADAR_WATCH as _TURBO_FINAL_WATCH,
)
# v3.1 — radar interno para WATCH (não vai pro Telegram)
from src.turbo_routes import (
    build_radar_record as _turbo_build_radar,
    radar_log as _turbo_radar_log,
)
# Filtro operacional ANTES da Turbo. Bloqueia jogos inelegíveis (min 90,
# sem stats, reservas, etc.) pra NÃO poluir o near_misses e NÃO chamar
# Turbo desnecessariamente. NÃO mexe em TRINCA/DT/Telegram.
from src import operational_eligibility_filter as _op_filter

import time

# ─── Paths ──────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"
STATE_FILE = LOG_DIR / "live_daemon_state.json"
LOG_FILE = LOG_DIR / "live_daemon_decisions.jsonl"
CATALOG_FILE = LOG_DIR / "live_daemon_catalog.json"
HEARTBEAT_FILE = LOG_DIR / "heartbeat.json"   # Dossiê v1.1 Seção 13.1
# v2.8 — heartbeat tick mid-cycle. Tocado durante o scan loop (a cada N
# jogos / N segundos). Watchdog lê esse arquivo PRIMEIRO. Mais leve que
# heartbeat completo, evita que o watchdog mate o daemon durante scan longo.
LIVE_TICK_FILE = LOG_DIR / "live_tick.json"

# v2.8 — rate-limit do warning "AO VIVO". Mutate-friendly dict permite update
# em closures sem `global`.
_ao_vivo_warning_state = {"last_state_was_missing": False}

SEPARATOR = "=" * 72

# ─── Shutdown limpo ────────────────────────────────────────────────────

_PARAR = False

def _shutdown(signum, frame):
    global _PARAR
    print("\n\n  [!] Ctrl+C — finalizando após o ciclo atual...")
    _PARAR = True


# ─── Self-watchdog (anti-travamento Playwright) ─────────────────────────
# Thread daemon que checa a idade do heartbeat.json a cada 60s. Se o ciclo
# travar (heartbeat > 8min sem atualizar), o processo se mata com os._exit(99).
# O start_daemon.sh (loop while) reinicia o daemon limpo em ~10s.
# Isso resolve travamentos do Playwright que ignoram timeouts internos.
#
# Importante: o self-watchdog SÓ olha pra heartbeats escritos APÓS o daemon
# subir (ignora heartbeat antigo de um daemon anterior travado). E tem warmup
# de 5min — não mata antes do primeiro ciclo terminar.
SELF_WATCHDOG_MAX_AGE_MINUTES = 15   # v2.10 (R4) bumped de 8 → 15min.
                                       # Sleep entre ciclos + ciclos longos
                                       # somam até 12min facilmente. Tick a
                                       # cada 15s no sleep + cycle_end +
                                       # scan cobrem isso, mas margem dá
                                       # defesa em profundidade.
SELF_WATCHDOG_WARMUP_SECONDS = 300  # 5 min de graça pra subir


def _touch_live_tick(*, pid: int = None, source: str = "scan",
                       path: Path = None) -> None:
    """Toque leve no LIVE_TICK_FILE — chamado durante o scan loop pra dizer
    "estou vivo processando". Watchdog usa isso pra não matar o daemon
    durante scans longos. Falha silenciosa — nunca derruba o daemon."""
    try:
        p = path or LIVE_TICK_FILE
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pid": int(pid if pid is not None else os.getpid()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": source,
        }
        # Write + replace atomic (não perder tick por race condition)
        tmp = p.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(payload, f)
        os.replace(tmp, p)
    except Exception:
        pass


def _self_watchdog_decision(process_start_utc, now_utc, heartbeat_path,
                              warmup_seconds=SELF_WATCHDOG_WARMUP_SECONDS,
                              max_age_minutes=SELF_WATCHDOG_MAX_AGE_MINUTES,
                              live_tick_path=None, current_pid=None):
    """Função pura: decide se daemon deve se matar. Retorna (kill, motivo).

    v2.8 — Prioriza LIVE_TICK_FILE (atualizado mid-cycle):
      • Se LIVE_TICK fresco do PID atual → NÃO mata (mesmo se heartbeat antigo)
      • Falha de tick → cai no heartbeat (comportamento legacy)

    Regras (em ordem):
      1. Antes de warmup → NÃO mata
      2. LIVE_TICK existe + PID confere + fresco → NÃO mata
      3. LIVE_TICK existe + PID outro → continua avaliação por heartbeat
      4. Heartbeat não existe → MATA
      5. Heartbeat de daemon anterior → MATA
      6. Heartbeat > max_age → MATA
      7. Caso contrário → NÃO mata
    """
    elapsed = (now_utc - process_start_utc).total_seconds()
    if elapsed < warmup_seconds:
        return False, f"warmup ({elapsed:.0f}s)"

    # v2.8 — LIVE_TICK tem precedência
    if live_tick_path is None:
        live_tick_path = LIVE_TICK_FILE
    if current_pid is None:
        current_pid = os.getpid()
    try:
        if live_tick_path.exists():
            tick = json.loads(live_tick_path.read_text())
            tick_pid = int(tick.get("pid", -1))
            tick_ts = tick.get("ts", "")
            if tick_pid == int(current_pid) and tick_ts:
                tick_at = datetime.fromisoformat(tick_ts.replace("Z","+00:00"))
                tick_age_min = (now_utc - tick_at).total_seconds() / 60
                if tick_age_min <= max_age_minutes:
                    return False, f"OK (tick {tick_age_min:.1f}min, pid {tick_pid})"
                # Tick velho do PID certo → MATA mesmo
                return True, (f"tick {tick_age_min:.1f}min do PID {tick_pid} "
                              f"(limite {max_age_minutes}min)")
            # PID diferente → tick é de daemon anterior; cai no heartbeat
    except Exception:
        pass  # tick ilegível, cai no heartbeat

    if not heartbeat_path.exists():
        return True, f"sem heartbeat após {elapsed/60:.0f}min de execução"
    try:
        hb = json.loads(heartbeat_path.read_text())
    except Exception as e:
        return True, f"heartbeat ilegível: {e}"
    ts = hb.get("last_scan_at", "")
    if not ts:
        return True, "heartbeat sem timestamp"
    last = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if last < process_start_utc:
        return True, f"heartbeat ainda do daemon anterior após {elapsed/60:.0f}min"
    age_min = (now_utc - last).total_seconds() / 60
    if age_min > max_age_minutes:
        return True, f"heartbeat {age_min:.1f}min (limite {max_age_minutes}min)"
    return False, f"OK ({age_min:.1f}min)"


def _self_watchdog_loop(process_start_utc):
    import time as _t
    while True:
        _t.sleep(60)  # checa a cada 1 min
        try:
            now = datetime.now(timezone.utc)
            kill, motivo = _self_watchdog_decision(
                process_start_utc, now, HEARTBEAT_FILE)
            if kill:
                print(f"\n  💀 SELF-WATCHDOG: {motivo} — "
                      f"matando processo pra forçar restart limpo.")
                sys.stdout.flush()
                os._exit(99)
        except Exception:
            pass  # nunca deixar o self-watchdog crashar o daemon

def _start_self_watchdog():
    import threading
    process_start_utc = datetime.now(timezone.utc)
    # v2.8 — toque inicial pra watchdog ver tick fresco já no startup
    _touch_live_tick(source="startup")
    t = threading.Thread(target=_self_watchdog_loop, args=(process_start_utc,),
                         daemon=True, name="self-watchdog")
    t.start()

signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


# ─── State persistence ─────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(state: dict):
    LOG_DIR.mkdir(exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ─── MatchState builder (com state injection) ──────────────────────────

def inject_state(ms: MatchState, state: dict) -> MatchState:
    """Injeta estado anterior no MatchState para delta detection e position tracking."""
    match_id = ms.match_id
    if match_id not in state:
        return ms

    prev = state[match_id]

    # Delta detection
    ms.prev_home_bc = prev.get("home_bc", -1)
    ms.prev_away_bc = prev.get("away_bc", -1)

    # Anti-spam
    ms.last_signal_action = prev.get("last_signal_action", "")
    ms.last_signal_minute = prev.get("last_signal_minute", 0)

    # CC timing — restaurar minutos do último BC conhecido (evita "999 min" bug).
    # Daemon hoje detecta nova CC via delta (home_bc > prev_home_bc) e atualiza
    # esses minutos no update_state. Se nunca houve delta, fica 0 (utils retorna 999).
    ms.minute_of_last_home_bc = prev.get("minute_of_last_home_bc", 0)
    ms.minute_of_last_away_bc = prev.get("minute_of_last_away_bc", 0)
    ms.minute_of_last_match_bc = prev.get("minute_of_last_match_bc", 0)

    # Anti-reentry: total_bc no último EXIT/LOCK
    ms.total_bc_at_exit = prev.get("total_bc_at_exit", 0)

    # Position state
    if prev.get("position_type"):
        ms.position_type = prev["position_type"]
        ms.position_team = prev.get("position_team")
        ms.entry_minute = prev.get("entry_minute", 0)
        ms.entry_signal_type = prev.get("entry_signal_type", "")
        ms.entry_tier = prev.get("entry_tier", "")
        ms.team_bc_at_entry = prev.get("team_bc_at_entry", 0)
        ms.opponent_bc_at_entry = prev.get("opponent_bc_at_entry", 0)
        ms.team_xgot_at_entry = prev.get("team_xgot_at_entry", 0.0)
        ms.opponent_xgot_at_entry = prev.get("opponent_xgot_at_entry", 0.0)
        ms.target_over_line = prev.get("target_over_line", 0.0)
        ms.state = prev.get("state", "IDLE")

    # Cooldown
    if prev.get("state") == "COOLDOWN":
        ms.state = "COOLDOWN"
        ms.cooldown_until_minute = prev.get("cooldown_until_minute", 0)

    return ms


def update_state(state: dict, ms: MatchState, decision):
    """Atualiza estado após scan."""
    match_id = ms.match_id
    prev = state.get(match_id, {})

    # ─── CC TIMING: detectar nova CC e atualizar minute_of_last_*_bc ──
    # Necessário pra que minutes_since_last_match_bc seja calculado corretamente
    # em utils.compute_derived (caso contrário retorna 999 = UNKNOWN_LAST_BC).
    prev_home_bc_val = prev.get("home_bc", -1)
    prev_away_bc_val = prev.get("away_bc", -1)

    # Inicialização defensiva — preserva valores existentes
    minute_home_bc = prev.get("minute_of_last_home_bc", 0)
    minute_away_bc = prev.get("minute_of_last_away_bc", 0)
    minute_match_bc = prev.get("minute_of_last_match_bc", 0)

    # Detectar incremento de CC do home
    if prev_home_bc_val >= 0 and ms.home_bc > prev_home_bc_val:
        minute_home_bc = ms.minute
        minute_match_bc = ms.minute
    # Bootstrap: primeira vez vendo o jogo COM ms.home_bc > 0 (sem prev)
    elif prev_home_bc_val < 0 and ms.home_bc > 0:
        minute_home_bc = ms.minute
        minute_match_bc = ms.minute

    if prev_away_bc_val >= 0 and ms.away_bc > prev_away_bc_val:
        minute_away_bc = ms.minute
        minute_match_bc = ms.minute
    elif prev_away_bc_val < 0 and ms.away_bc > 0:
        minute_away_bc = ms.minute
        minute_match_bc = ms.minute

    prev["minute_of_last_home_bc"] = minute_home_bc
    prev["minute_of_last_away_bc"] = minute_away_bc
    prev["minute_of_last_match_bc"] = minute_match_bc

    prev["home"] = ms.home
    prev["away"] = ms.away
    prev["last_minute"] = ms.minute
    prev["last_score"] = f"{ms.home_score}-{ms.away_score}"
    prev["last_cc"] = f"{ms.home_bc}x{ms.away_bc}"
    prev["last_update"] = datetime.now(timezone.utc).isoformat()
    prev["home_bc"] = ms.home_bc
    prev["away_bc"] = ms.away_bc
    prev["home_xgot"] = ms.home_xgot
    prev["away_xgot"] = ms.away_xgot

    action = decision.recommended_action
    if action.startswith("ENTER_") or action in ("EXIT_BACK", "EXIT_OVER", "LOCK_PROFIT"):
        prev["last_signal_action"] = action
        prev["last_signal_minute"] = ms.minute

    if action.startswith("ENTER_BACK_") and action != "SIGNAL_MAINTAINED":
        from src.utils import compute_derived
        d = compute_derived(ms)
        prev["position_type"] = "BACK"
        prev["position_team"] = d.dominant_team
        prev["entry_minute"] = ms.minute
        prev["entry_signal_type"] = action
        prev["entry_tier"] = decision.confidence_tier
        prev["team_bc_at_entry"] = d.dominant_bc
        prev["opponent_bc_at_entry"] = d.opponent_bc
        prev["team_xgot_at_entry"] = d.dominant_xgot
        prev["opponent_xgot_at_entry"] = d.opponent_xgot
        prev["target_over_line"] = 0.0
        prev["state"] = "POSITION_BACK"
        # Reset anti-reentry lock — nova entrada permitida
        prev["total_bc_at_exit"] = 0

    elif action.startswith("ENTER_OVER_") and action != "SIGNAL_MAINTAINED":
        from src.utils import compute_derived
        d = compute_derived(ms)
        prev["position_type"] = "OVER"
        prev["position_team"] = d.dominant_team
        prev["entry_minute"] = ms.minute
        prev["entry_signal_type"] = action
        prev["entry_tier"] = decision.confidence_tier
        prev["team_bc_at_entry"] = d.dominant_bc
        prev["opponent_bc_at_entry"] = d.opponent_bc
        prev["team_xgot_at_entry"] = d.dominant_xgot
        prev["opponent_xgot_at_entry"] = d.opponent_xgot
        prev["target_over_line"] = decision.target_over_line
        prev["state"] = "POSITION_OVER"
        # Reset anti-reentry lock — nova entrada permitida
        prev["total_bc_at_exit"] = 0
        # Bootstrap defensivo: se este é o 1º scan E o jogo já tem CC,
        # marcar o minuto atual como "última CC vista" pra evitar bug 999.
        if minute_match_bc == 0 and (ms.home_bc + ms.away_bc) > 0:
            prev["minute_of_last_match_bc"] = ms.minute

    elif action in ("EXIT_BACK", "EXIT_OVER", "LOCK_PROFIT"):
        prev["position_type"] = None
        prev["position_team"] = None
        prev["state"] = "COOLDOWN"
        # Cooldown estendido (10 min) conforme requisito anti-reentry
        cooldown_min = 10
        prev["cooldown_until_minute"] = ms.minute + cooldown_min
        # Anti-reentry: salvar total_bc no momento do exit. Bloqueia nova
        # entrada Over enquanto total atual <= total_bc_at_exit (sem nova CC).
        if action in ("EXIT_OVER", "LOCK_PROFIT"):
            prev["total_bc_at_exit"] = ms.home_bc + ms.away_bc

    state[match_id] = prev


# ─── Log ────────────────────────────────────────────────────────────────

def save_log(ms: MatchState, decision, derived, tg_debug: dict = None):
    LOG_DIR.mkdir(exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rule_version": "V1.2",
        "mode": "live_daemon",
        "match_id": ms.match_id,
        "home": ms.home,
        "away": ms.away,
        "minute": ms.minute,
        "score": f"{ms.home_score}-{ms.away_score}",
        "cc": f"{ms.home_bc}x{ms.away_bc}",
        "xgot": f"{ms.home_xgot:.2f}x{ms.away_xgot:.2f}",
        "game_profile": decision.game_profile,
        "recommended_action": decision.recommended_action,
        "market_target": decision.market_target,
        "confidence_tier": decision.confidence_tier,
        "operator_instruction": decision.operator_instruction,
        "message_severity": decision.message_severity,
        "blocked_reason": decision.blocked_reason,
        "signal_valid_until": decision.signal_valid_until,
    }
    # Debug Telegram filter
    if tg_debug:
        entry.update(tg_debug)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ─── Display ────────────────────────────────────────────────────────────

def _ts():
    return datetime.now().strftime("%H:%M:%S")

def _sev_dot(sev):
    """Dot colorido por severidade (como radar13)."""
    dots = {
        "INFO": "\033[34m⚫\033[0m",      # azul
        "WATCH": "\033[33m⚫\033[0m",      # amarelo
        "ACTION": "\033[32m⚫\033[0m",     # verde
        "URGENT": "\033[31m⚫\033[0m",     # vermelho
        "BLOCKED": "\033[90m⚫\033[0m",    # cinza
        "EXPIRED": "\033[90m⚫\033[0m",    # cinza
    }
    return dots.get(sev, "⚫")

def _half_label(minute):
    if minute <= 0:
        return "Pre"
    elif minute <= 45:
        return "1st Half"
    elif minute <= 90:
        return "2nd Half"
    else:
        return "Extra"

def _action_color(action):
    """Colore a ação no terminal."""
    if action.startswith("ENTER_"):
        return f"\033[1;32m{action}\033[0m"  # verde bold
    elif action in ("EXIT_BACK", "EXIT_OVER", "LOCK_PROFIT"):
        return f"\033[1;31m{action}\033[0m"  # vermelho bold
    elif action.startswith("HOLD_"):
        return f"\033[36m{action}\033[0m"    # ciano
    elif action in ("REDUCE_BACK", "REDUCE_OVER", "YELLOW_ALERT_BACK", "YELLOW_ALERT_OVER"):
        return f"\033[33m{action}\033[0m"    # amarelo
    elif action == "MANUAL_REVIEW":
        return f"\033[1;33m{action}\033[0m"  # amarelo bold
    elif action == "BLOCKED":
        return f"\033[90m{action}\033[0m"    # cinza
    return action


# ─── DRY-RUN: TRINCA (Regra 3.1.2.0 Turbo) ──────────────────────────────
# Roda a nova regra-mãe em paralelo, gera audit log, NÃO bloqueia Telegram.
# Falha silenciosa: se a TRINCA crashar, daemon continua exatamente como
# antes. Enforcement = OFF até flag explícita ser ativada (futuro).

def _all_raw_metrics_missing(ms) -> bool:
    """True quando o MatchState veio mas TODOS os campos _raw são None
    (página carregou mas o DOM não tinha stats). Usado pelo daemon pra
    marcar mark_no_stats e ativar cooldown — evita gastar slot todo ciclo
    em ligas sem cobertura de Flashscore."""
    keys = ("home_xg_raw", "away_xg_raw",
            "home_xgot_raw", "away_xgot_raw",
            "home_bc_raw", "away_bc_raw")
    # Se o MatchState ainda não tem o atributo _raw (versão muito antiga),
    # NÃO declara missing — comportamento legacy.
    for k in keys:
        if not hasattr(ms, k):
            return False
    return all(getattr(ms, k, "MISS") is None for k in keys)


def _fmt_metric(ms, attr_raw, attr_legacy, fmt=".2f"):
    """Display helper: 'N/A' quando _raw é explicitamente None (dado
    ausente do feed); valor formatado quando real (inclusive 0.00 real)."""
    raw = getattr(ms, attr_raw, "_MISSING_")
    if raw == "_MISSING_":
        # MatchState sem campo _raw (test/legacy) → cai pra legacy
        return f"{getattr(ms, attr_legacy, 0):{fmt}}"
    if raw is None:
        return "N/A"
    return f"{raw:{fmt}}"


def _fmt_int(ms, attr_raw, attr_legacy):
    raw = getattr(ms, attr_raw, "_MISSING_")
    if raw == "_MISSING_":
        return str(getattr(ms, attr_legacy, 0))
    if raw is None:
        return "N/A"
    return str(raw)


def _ms_to_dict(ms) -> dict:
    """MatchState dataclass → dict raso (usado por TRINCA, DT e OP filter).
    Propaga campos _raw (None = ausente) pra TRINCA detectar bloqueio
    por dado ausente. Também propaga league_name e status_raw pro OP."""
    d = {
        "match_id":  getattr(ms, "match_id", ""),
        "home":      getattr(ms, "home", ""),
        "away":      getattr(ms, "away", ""),
        "minute":    getattr(ms, "minute", 0),
        "home_bc":   getattr(ms, "home_bc", 0),
        "away_bc":   getattr(ms, "away_bc", 0),
        "home_xg":   getattr(ms, "home_xg", 0.0),
        "away_xg":   getattr(ms, "away_xg", 0.0),
        "home_xgot": getattr(ms, "home_xgot", 0.0),
        "away_xgot": getattr(ms, "away_xgot", 0.0),
        "home_score": getattr(ms, "home_score", 0),
        "away_score": getattr(ms, "away_score", 0),
        "home_sot":  getattr(ms, "home_sot", 0),
        "away_sot":  getattr(ms, "away_sot", 0),
        "home_shots": getattr(ms, "home_shots", 0),
        "away_shots": getattr(ms, "away_shots", 0),
        "status_raw":  getattr(ms, "status_raw", "") or "",
        "league_name": getattr(ms, "league_name", "") or "",
    }
    # _raw — só inclui se o atributo existir e for None (ausente);
    # ou se for valor real (não None).
    for k in ("home_xgot_raw","away_xgot_raw",
              "home_xg_raw","away_xg_raw",
              "home_bc_raw","away_bc_raw",
              "home_sot_raw","away_sot_raw"):
        if hasattr(ms, k):
            d[k] = getattr(ms, k)
    return d


def _decision_to_dict(decision) -> dict:
    return {
        "message_severity":   getattr(decision, "message_severity", ""),
        "recommended_action": getattr(decision, "recommended_action", ""),
        "market_target":      getattr(decision, "market_target", ""),
    }


def _triple_debt_dry_run_audit(ms, decision) -> None:
    """Audit paralelo da TRINCA — appenda em logs/triple_debt_audit.jsonl.
    Não muta ms/decision, não envia Telegram, não levanta exceção."""
    try:
        msd = _ms_to_dict(ms)
        # TRINCA usa home_cc/away_cc/home_goals/away_goals
        match_state = {
            **msd,
            "home_team": msd["home"], "away_team": msd["away"],
            "home_cc": msd["home_bc"], "away_cc": msd["away_bc"],
            "home_goals": msd["home_score"], "away_goals": msd["away_score"],
            "score": f"{msd['home_score']}-{msd['away_score']}",
        }
        result = _triple_debt_validate(match_state)
        _triple_debt_audit_log(
            match_state,
            getattr(decision, "message_severity", "") or "",
            getattr(decision, "recommended_action", "") or "",
            result,
        )
    except Exception:
        pass


def _operational_filter_or_skip(ms, decision, *, catalog=None):
    """Filtro operacional ANTES da Turbo. Retorna (eligible:bool, reason:str).

    Se eligible=False:
      - Daemon NÃO chama Turbo (não polui near_misses)
      - Daemon NÃO envia Telegram
      - Loga em logs/operational_excluded.jsonl
      - Aplica action (mark_no_stats / cooldown_30 / mark_finished)

    Falha silenciosa: erro inesperado → considera elegível (não derruba
    daemon nem bloqueia jogos por bug do filtro).
    """
    try:
        msd = _ms_to_dict(ms)
        dd  = _decision_to_dict(decision)
        mid = msd.get("match_id") or ""

        # Cooldown ativo? Pula direto, sem reavaliar nem logar de novo
        if mid and _op_filter.is_in_cooldown(mid):
            return False, "OP_COOLDOWN_ACTIVE"

        streak = _op_filter.get_missing_xgot_streak(mid)
        result = _op_filter.evaluate_operational_eligibility(
            msd, dd, missing_xgot_streak=streak)

        if result["eligible"]:
            return True, "OP_ELIGIBLE"

        # Não elegível — apply action + log
        action = result.get("action") or ""
        if action == "cooldown_30":
            _op_filter.add_cooldown(mid, minutes=30)
        elif action == "mark_no_stats" and catalog is not None:
            try: catalog.mark_no_stats(mid)
            except Exception: pass
        elif action == "mark_finished" and catalog is not None:
            try: catalog.mark_finished_or_not_live(mid, "OP_FINISHED_MIN_90",
                                                     ttl_hours=1)
            except Exception: pass

        try: _op_filter.log_exclusion(result)
        except Exception: pass

        return False, f"OP_BLOCKED_{(result.get('reason') or 'unknown').upper()}"
    except Exception:
        # Filtro nunca derruba daemon — em caso de erro, deixa Turbo decidir.
        return True, "OP_ELIGIBLE_FALLBACK"


def _turbo_enforce_or_block(ms, decision):
    """ENFORCEMENT: roda TRINCA + DT, devolve (allowed:bool, reason:str).

    Sempre appenda em logs/turbo_near_misses.jsonl quando bloquear.
    Sempre appenda em logs/turbo_approved_signals.jsonl quando aprovar.
    Falha fechada: erro inesperado → bloqueia + reason="TURBO_INTERNAL_ERROR".
    """
    try:
        msd = _ms_to_dict(ms)
        dd  = _decision_to_dict(decision)
        result = _turbo_evaluate(msd, dd, match_history=None)
        if result["final_decision"] == _TURBO_FINAL_SENT:
            try:
                rec = _turbo_build_approved(msd, dd, result)
                _turbo_approved_log(rec)
            except Exception:
                pass
            # Reset streak: Turbo aprovou → match não está em "missing_xgot"
            try: _op_filter.record_turbo_result(
                getattr(ms, "match_id", "") or "", "TURBO_APPROVED")
            except Exception: pass
            return (True, "TURBO_APPROVED")

        # v3.1 — WATCH vai pro RADAR INTERNO. NÃO chama Telegram, NÃO conta
        # como bloqueio (é apenas observação). Sem registrar em near_misses.
        if result["final_decision"] == _TURBO_FINAL_WATCH:
            try:
                routes_result = result.get("routes_result") or {}
                rec = _turbo_build_radar(msd, dd, routes_result)
                _turbo_radar_log(rec)
            except Exception:
                pass
            return (False, "TURBO_RADAR_WATCH")
        # Bloqueado — log near miss
        try:
            rec = _turbo_build_near_miss(msd, dd, result)
            _turbo_near_miss_log(rec)
        except Exception:
            pass
        reason_map = {
            "blocked_triple":             "TURBO_BLOCKED_TRIPLE",
            "blocked_dominant_trailing":  "TURBO_BLOCKED_DOMINANT_TRAILING",
            "blocked_error":              "TURBO_BLOCKED_ERROR",
            "blocked_missing_data":       "TURBO_BLOCKED_MISSING_DATA",
            "blocked_no_tier":            "TURBO_BLOCKED_NO_TIER",   # v3.1
        }
        reason = reason_map.get(result["final_decision"], "TURBO_BLOCKED")
        # Detalha o tipo de dado ausente (xgot/xg/cc)
        if result["final_decision"] == "blocked_missing_data":
            tr = result.get("triple_debt_result") or {}
            br = (tr.get("block_reason") or "")
            if br == "triple_debt_missing_xgot": reason = "TURBO_BLOCKED_MISSING_XGOT"
            elif br == "triple_debt_missing_xg": reason = "TURBO_BLOCKED_MISSING_XG"
            elif br == "triple_debt_missing_cc": reason = "TURBO_BLOCKED_MISSING_CC"
        # Registra streak no OP filter (próximo ciclo o OP usa pra decidir
        # se este match_id já está repetido demais → cooldown 30 min).
        try: _op_filter.record_turbo_result(
            getattr(ms, "match_id", "") or "", reason)
        except Exception: pass
        return (False, reason)
    except Exception as e:
        # Erro catastrófico no próprio wrapper → bloqueia (fail-closed)
        try:
            _turbo_near_miss_log({
                "timestamp": "",  # preenchido pelo evaluator quando OK
                "match_id":  getattr(ms, "match_id", ""),
                "home_team": getattr(ms, "home", ""),
                "away_team": getattr(ms, "away", ""),
                "minute":    getattr(ms, "minute", 0),
                "final_decision": "blocked_error",
                "telegram_sent":  False,
                "error":  f"{type(e).__name__}: {str(e)[:200]}",
                "near_miss_type": "wrapper_internal_error",
            })
        except Exception:
            pass
        return (False, "TURBO_INTERNAL_ERROR")


# ─── Ciclo principal ───────────────────────────────────────────────────

def run_cycle(reader: FlashscoreReader, urls: list, cfg: dict,
              tg: TelegramClient, state: dict) -> dict:
    """Roda um ciclo completo de scan em todos os jogos."""
    stats = {"scanned": 0, "signals": 0, "telegram_sent": 0, "errors": 0, "no_stats": 0}
    cycle_start = time.time()

    for i, url in enumerate(urls):
        if _PARAR:
            break

        # Extrair
        ms = reader.read_match(url)
        if ms is None:
            stats["no_stats"] += 1
            # Mostrar que tentou (extrair nome do URL)
            parts = url.split("/jogo/")[-1].split("/") if "/jogo/" in url else []
            name = parts[-1] if len(parts) >= 2 else url.split("/")[-1]
            name = name.split("-")[0] if name else "?"
            print(f"  \033[90m⚫ {name}... sem stats\033[0m")
            sys.stdout.flush()
            continue

        stats["scanned"] += 1

        # Injetar estado anterior
        ms = inject_state(ms, state)

        # Rodar motor
        decision, derived = run_scan(ms, cfg)
        action = decision.recommended_action
        sev = decision.message_severity

        # ─── Display em tempo real (cada jogo aparece imediatamente) ──
        dot = _sev_dot(sev)
        half = _half_label(ms.minute)
        profile = decision.game_profile or ""

        print(f"  {dot} {ms.home} {ms.home_score}-{ms.away_score} {ms.away} | "
              f"{half} min {ms.minute} | {profile}")
        # Display: N/A quando dado ausente no feed (raw=None);
        # valor formatado quando presente (inclusive 0.00 real).
        print(f"    {ms.home[:3].upper()}: "
              f"xG={_fmt_metric(ms, 'home_xg_raw', 'home_xg')} "
              f"xGOT={_fmt_metric(ms, 'home_xgot_raw', 'home_xgot')} "
              f"CC={_fmt_int(ms, 'home_bc_raw', 'home_bc')}")
        print(f"    {ms.away[:3].upper()}: "
              f"xG={_fmt_metric(ms, 'away_xg_raw', 'away_xg')} "
              f"xGOT={_fmt_metric(ms, 'away_xgot_raw', 'away_xgot')} "
              f"CC={_fmt_int(ms, 'away_bc_raw', 'away_bc')}")

        if action != "NO_ACTION":
            colored = _action_color(action)
            line = f"    \033[1m→ {colored}\033[0m"
            if decision.market_target:
                line += f" — {decision.market_target}"
            if decision.confidence_tier:
                line += f" (Tier {decision.confidence_tier})"
            if decision.operator_instruction:
                line += f" | {decision.operator_instruction}"
            print(line)

        # ─── DRY-RUN: TRINCA (Regra 3.1.2.0 Turbo) ─────────────────
        # Audit paralelo da nova regra-mãe. NÃO bloqueia Telegram.
        # Só audita candidatos reais (action != NO_ACTION).
        if action != "NO_ACTION":
            _triple_debt_dry_run_audit(ms, decision)

        # Telegram debug info
        tg_debug = {}
        if tg:
            stable_key = tg._stable_key(ms)
            blocked_reason = decision.blocked_reason or ""
            spam_key = f"{stable_key}|{action}|{blocked_reason}"
            anti_spam_entry = tg._last_signal.get(spam_key)
            tg_debug = {
                "telegram_stable_key": stable_key,
                "telegram_anti_spam_key": spam_key,
                "telegram_last_sent_at": anti_spam_entry[0] if isinstance(anti_spam_entry, list) else "",
                "telegram_should_send": tg.should_send(decision, ms),
            }

        # ─── Update state (sempre, independente de Telegram) ──────────
        update_state(state, ms, decision)

        # ─── PROTEÇÃO DUPLA — MANUAL_REVIEW: log only, NUNCA Telegram ──
        # Camada 1 (daemon): short-circuit absoluto antes de tocar em tg.
        # Camada 2 (client): src/telegram_client.send_decision() também
        # retorna SendResult(False, "MANUAL_REVIEW_LOG_ONLY") se chegar lá.
        telegram_sent = False
        telegram_filter_reason = ""

        if action == "MANUAL_REVIEW":
            telegram_sent = False
            telegram_filter_reason = "MANUAL_REVIEW_LOG_ONLY"
            print(f"    \033[90m⏭  Telegram filtrado: MANUAL_REVIEW_LOG_ONLY (log apenas)\033[0m")
        elif tg and tg.is_ready():
            # ─── ELEGIBILIDADE OPERACIONAL (ANTES da Turbo) ──────────
            # Bloqueia jogos inelegíveis (min 90 + N/A, reservas,
            # repeated missing_xgot, etc.) sem chamar Turbo.
            # Não polui turbo_near_misses.
            if action != "NO_ACTION":
                op_ok, op_reason = _operational_filter_or_skip(ms, decision)
            else:
                op_ok, op_reason = True, "OP_SKIPPED_NO_ACTION"
            if not op_ok:
                telegram_sent = False
                telegram_filter_reason = op_reason
                turbo_allowed = False
                turbo_reason = op_reason
                print(f"    \033[90m⏭  Excluído operacionalmente: {op_reason}\033[0m")
            else:
                # ─── ENFORCEMENT TURBO ────────────────────────────────
                # TRINCA + DOMINANT_TRAILING_PROTECTION. Falha fechada.
                if action != "NO_ACTION":
                    turbo_allowed, turbo_reason = _turbo_enforce_or_block(ms, decision)
                else:
                    turbo_allowed, turbo_reason = True, "TURBO_SKIPPED_NO_ACTION"
                if not turbo_allowed:
                    telegram_sent = False
                    telegram_filter_reason = turbo_reason
                    print(f"    \033[91m🛑 Telegram BLOQUEADO Turbo: {turbo_reason}\033[0m")
                else:
                    # send_decision já encapsula stale + should_send + anti-spam.
                    result = tg.send_decision(decision, ms, derived)
                    telegram_sent = bool(result.sent)
                    telegram_filter_reason = result.reason
                    if telegram_sent:
                        stats["telegram_sent"] += 1
                        print(f"    \033[32m✅ Telegram enviado\033[0m")
                    else:
                        print(f"    \033[90m⏭  Telegram filtrado: {result.reason}\033[0m")
        elif tg and not tg.is_ready():
            telegram_filter_reason = "NOT_READY"
        else:
            telegram_filter_reason = "TELEGRAM_DISABLED"

        # Log (com auditoria de Telegram embutida)
        tg_debug["telegram_sent"] = telegram_sent
        tg_debug["telegram_filter_reason"] = telegram_filter_reason
        save_log(ms, decision, derived, tg_debug)

        if action not in ("NO_ACTION", "SIGNAL_MAINTAINED", "COOLDOWN", "BLOCKED"):
            stats["signals"] += 1

        # Flush para garantir que aparece no terminal imediatamente
        sys.stdout.flush()

    # Salvar estado
    save_state(state)

    # ─── Resumo do ciclo ──────────────────────────────────────────────
    cycle_time = time.time() - cycle_start
    elapsed = f"{cycle_time:.1f}s"
    interval = 120  # default, será sobrescrito pelo caller

    print(f"\n  \033[36mMonitorando: {stats['scanned']} jogos\033[0m | "
          f"Sem stats: {stats['no_stats']} | "
          f"Sinais: {stats['signals']} | "
          f"Telegram: {stats['telegram_sent']}")
    print(f"  ⏱  Ciclo levou {elapsed}")

    return stats


# ─── Modo WATCHLIST (--use-watchlist) ──────────────────────────────────
# Novo scheduler: discovery loop + scan loop com watchlist priorizada.
# `run_cycle()` acima fica INTOCADO byte-a-byte (modo antigo).
# Todo o pipeline crítico — run_scan, manual_review_guard, telegram filters,
# state injection — é compartilhado entre os dois modos via as mesmas funções.

def run_cycle_watchlist(reader: FlashscoreReader, mid_urls: list, cfg: dict,
                        tg: TelegramClient, state: dict, catalog: Catalog,
                        read_match_timeout_ms: int = 12000,
                        stale_ttl_minutes: int = 15) -> dict:
    """
    Ciclo de scan no modo watchlist. Recebe lista de (match_id, url).

    Pipeline IDÊNTICO ao run_cycle(): read_match → inject_state → run_scan →
    proteção dupla MANUAL_REVIEW → tg.send_decision → save_log.
    Diferenças: passa timeout_ms ao read_match, e atualiza Catalog pós-scan.
    """
    stats = {"scanned": 0, "signals": 0, "telegram_sent": 0,
             "errors": 0, "no_stats": 0}
    cycle_start = time.time()

    for mid, url in mid_urls:
        if _PARAR:
            break

        ms = reader.read_match(url, timeout_ms=read_match_timeout_ms)
        if ms is None:
            stats["no_stats"] += 1
            catalog.mark_no_stats(mid)
            name = mid.replace("FS_", "")[:12]
            print(f"  \033[90m⚫ {name}... sem stats\033[0m")
            sys.stdout.flush()
            continue

        stats["scanned"] += 1

        ms = inject_state(ms, state)
        decision, derived = run_scan(ms, cfg)
        action = decision.recommended_action
        sev = decision.message_severity

        # Display em tempo real
        dot = _sev_dot(sev)
        half = _half_label(ms.minute)
        profile = decision.game_profile or ""
        print(f"  {dot} {ms.home} {ms.home_score}-{ms.away_score} {ms.away} | "
              f"{half} min {ms.minute} | {profile}")
        # Display: N/A quando dado ausente no feed (raw=None);
        # valor formatado quando presente (inclusive 0.00 real).
        print(f"    {ms.home[:3].upper()}: "
              f"xG={_fmt_metric(ms, 'home_xg_raw', 'home_xg')} "
              f"xGOT={_fmt_metric(ms, 'home_xgot_raw', 'home_xgot')} "
              f"CC={_fmt_int(ms, 'home_bc_raw', 'home_bc')}")
        print(f"    {ms.away[:3].upper()}: "
              f"xG={_fmt_metric(ms, 'away_xg_raw', 'away_xg')} "
              f"xGOT={_fmt_metric(ms, 'away_xgot_raw', 'away_xgot')} "
              f"CC={_fmt_int(ms, 'away_bc_raw', 'away_bc')}")

        if action != "NO_ACTION":
            colored = _action_color(action)
            line = f"    \033[1m→ {colored}\033[0m"
            if decision.market_target:
                line += f" — {decision.market_target}"
            if decision.confidence_tier:
                line += f" (Tier {decision.confidence_tier})"
            if decision.operator_instruction:
                line += f" | {decision.operator_instruction}"
            print(line)

        # ─── DRY-RUN: TRINCA (Regra 3.1.2.0 Turbo) ─────────────────
        # Audit paralelo (modo watchlist). NÃO bloqueia Telegram.
        if action != "NO_ACTION":
            _triple_debt_dry_run_audit(ms, decision)

        # Telegram debug info (idêntico ao run_cycle)
        tg_debug = {}
        if tg:
            stable_key = tg._stable_key(ms)
            blocked_reason = decision.blocked_reason or ""
            spam_key = f"{stable_key}|{action}|{blocked_reason}"
            anti_spam_entry = tg._last_signal.get(spam_key)
            tg_debug = {
                "telegram_stable_key": stable_key,
                "telegram_anti_spam_key": spam_key,
                "telegram_last_sent_at": anti_spam_entry[0] if isinstance(anti_spam_entry, list) else "",
                "telegram_should_send": tg.should_send(decision, ms),
            }

        update_state(state, ms, decision)

        # PROTEÇÃO DUPLA — MANUAL_REVIEW (idêntica ao run_cycle)
        telegram_sent = False
        telegram_filter_reason = ""

        if action == "MANUAL_REVIEW":
            telegram_filter_reason = "MANUAL_REVIEW_LOG_ONLY"
            print(f"    \033[90m⏭  Telegram filtrado: MANUAL_REVIEW_LOG_ONLY (log apenas)\033[0m")
        elif tg and tg.is_ready():
            # ─── ELEGIBILIDADE OPERACIONAL (ANTES da Turbo) ──────────
            if action != "NO_ACTION":
                op_ok, op_reason = _operational_filter_or_skip(
                    ms, decision, catalog=catalog)
            else:
                op_ok, op_reason = True, "OP_SKIPPED_NO_ACTION"
            if not op_ok:
                telegram_sent = False
                telegram_filter_reason = op_reason
                turbo_allowed = False
                turbo_reason = op_reason
                print(f"    \033[90m⏭  Excluído operacionalmente: {op_reason}\033[0m")
            else:
                # ─── ENFORCEMENT TURBO (watchlist) ────────────────────
                if action != "NO_ACTION":
                    turbo_allowed, turbo_reason = _turbo_enforce_or_block(ms, decision)
                else:
                    turbo_allowed, turbo_reason = True, "TURBO_SKIPPED_NO_ACTION"
                if not turbo_allowed:
                    telegram_sent = False
                    telegram_filter_reason = turbo_reason
                    print(f"    \033[91m🛑 Telegram BLOQUEADO Turbo: {turbo_reason}\033[0m")
                else:
                    result = tg.send_decision(decision, ms, derived)
                    telegram_sent = bool(result.sent)
                    telegram_filter_reason = result.reason
                    if telegram_sent:
                        stats["telegram_sent"] += 1
                        print(f"    \033[32m✅ Telegram enviado\033[0m")
                    else:
                        print(f"    \033[90m⏭  Telegram filtrado: {result.reason}\033[0m")
        elif tg and not tg.is_ready():
            telegram_filter_reason = "NOT_READY"
        else:
            telegram_filter_reason = "TELEGRAM_DISABLED"

        # ─── Catalog updates pós-scan ───────────────────────────────
        bc_sum = (ms.home_bc or 0) + (ms.away_bc or 0)
        catalog.mark_scanned(mid, minute=ms.minute,
                             score=f"{ms.home_score}-{ms.away_score}",
                             bc_sum=bc_sum)
        if telegram_filter_reason in ("STALE_MATCH", "NO_DATA_EVOLUTION"):
            catalog.mark_stale(mid, stale_ttl_minutes)
        if action.startswith("ENTER_"):
            catalog.mark_signal(mid, action, ms.minute)
            catalog.set_position_open(mid, True)
        elif action in ("EXIT_BACK", "EXIT_OVER", "LOCK_PROFIT"):
            catalog.mark_signal(mid, action, ms.minute)
            catalog.set_position_open(mid, False)

        tg_debug["telegram_sent"] = telegram_sent
        tg_debug["telegram_filter_reason"] = telegram_filter_reason
        save_log(ms, decision, derived, tg_debug)

        if action not in ("NO_ACTION", "SIGNAL_MAINTAINED", "COOLDOWN", "BLOCKED"):
            stats["signals"] += 1

        sys.stdout.flush()

    save_state(state)
    cycle_time = time.time() - cycle_start
    elapsed = f"{cycle_time:.1f}s"
    print(f"\n  \033[36mMonitorando: {stats['scanned']} jogos\033[0m | "
          f"Sem stats: {stats['no_stats']} | "
          f"Sinais: {stats['signals']} | "
          f"Telegram: {stats['telegram_sent']}")
    print(f"  ⏱  Ciclo levou {elapsed}")

    return stats


def _reconcile_catalog_with_state(catalog: Catalog, state: dict) -> None:
    """Sincroniza flags `has_open_position` e last_signal_* a partir do state.json.

    Garante que mesmo se o usuário tinha posição aberta antes do daemon reiniciar
    no modo watchlist, o jogo entra como Tier 0.
    """
    for mid, mst in state.items():
        if catalog.get(mid) is None:
            continue
        catalog.set_position_open(mid, bool(mst.get("position_type")))
        if mst.get("last_signal_action"):
            catalog.mark_signal(mid,
                                str(mst.get("last_signal_action") or ""),
                                int(mst.get("last_signal_minute") or 0))


def run_watchlist_loop(reader: FlashscoreReader, args, cfg: dict,
                       tg: TelegramClient, state: dict) -> None:
    """Loop principal do modo --use-watchlist.

    Alterna entre discovery (a cada discovery_interval) e scan (a cada scan_interval).
    Sleep corrige cadência: max(15, scan_interval - elapsed).
    """
    cycle_count = 0
    catalog = Catalog(CATALOG_FILE)
    catalog.load()

    # Força discovery no primeiro ciclo
    last_discovery_time = 0.0
    last_discovery_total = 0   # último total_live_games_discovered conhecido
    last_discovered_live_ids = set()  # match_ids vistos como live no último discovery (v2.4 — coverage guard)

    while not _PARAR:
        cycle_count += 1
        loop_start = time.time()

        # ─── Discovery (se chegou a hora) ──────────────────────────
        now_mono = time.monotonic()
        if (now_mono - last_discovery_time) >= args.discovery_interval or last_discovery_time == 0.0:
            print(f"\n{'─' * 72}")
            print(f"  \033[1m🔭 DISCOVERY\033[0m — {_ts()} — Buscando jogos ao vivo...")
            sys.stdout.flush()
            disc = discover_live_games(
                reader._context,
                args.base_url,
                cookie_accept_fn=reader._accept_cookies,
                timeout_ms=15000,
            )
            if disc.get("error"):
                print(f"  \033[33m⚠️  Erro na discovery: {disc['error']}\033[0m")
            # v2.8 — rate-limit do warning AO VIVO. Discovery tem fallback
            # funcional. Printa no 1º ciclo OU a cada 10 ciclos OU quando
            # o flag flipa (ao_vivo voltou a ser encontrado).
            if not disc.get("ao_vivo_found"):
                should_warn = (
                    cycle_count <= 1
                    or cycle_count % 10 == 0
                    or not _ao_vivo_warning_state["last_state_was_missing"]
                )
                if should_warn:
                    print(f"  \033[33m⚠️  Botão 'AO VIVO' não encontrado "
                          f"(discovery usa fallback funcional)\033[0m")
                _ao_vivo_warning_state["last_state_was_missing"] = True
            else:
                _ao_vivo_warning_state["last_state_was_missing"] = False
            # Log explícito quando o walker DOM de liga falhou
            if disc.get("dom_detection_failed"):
                print(f"  \033[33m⚠️  highlighted league DOM detection failed; "
                      f"usando fallback de league-name/slug\033[0m")

            # ─── DOM LEAGUE META (diagnóstico do walker direto) ─────
            ls = disc.get("league_stats") or {}
            if ls:
                print(f"\n  \033[36m📊 DOM LEAGUE META:\033[0m")
                print(f"     total_links:                           {ls.get('total_links', 0)}")
                print(f"     links_com_event_match_parent:          {ls.get('links_com_event_match_parent', 0)}")
                print(f"     links_com_sportName_parent:            {ls.get('links_com_sportName_parent', 0)}")
                print(f"     links_com_previous_headerLeague_wrapper: {ls.get('links_com_previous_headerLeague_wrapper', 0)}")
                print(f"     links_com_league_name_extraida:        {ls.get('links_com_league_name_extraida', 0)}")
                print(f"     links_com_country_extraida:            {ls.get('links_com_country_extraida', 0)}")
                print(f"     links_com_highlighted_true:            {ls.get('links_com_highlighted_true', 0)}")
            lf = disc.get("league_failures") or {}
            if lf:
                lfs = disc.get("league_failure_sample") or {}
                print(f"  \033[33m   Falhas do walker (sample):\033[0m")
                for ftype, count in sorted(lf.items(), key=lambda x: -x[1]):
                    sample = lfs.get(ftype, "")
                    print(f"     - {ftype}: {count} (ex: {sample[-80:] if sample else '?'})")

            league_meta_map = disc.get("league_meta", {}) or {}
            new_count = 0
            current_live_ids = set()
            for mid, url in disc.get("games", []):
                if catalog.get(mid) is None:
                    new_count += 1
                # Passa metadados de liga (vazio se DOM walker não capturou)
                catalog.upsert_discovered(mid, url,
                                           league_meta=league_meta_map.get(mid))
                current_live_ids.add(mid)
            catalog.save()
            last_discovery_time = now_mono
            last_discovered_live_ids = current_live_ids   # v2.4 — coverage guard

            total = disc.get("total_found", 0)
            last_discovery_total = total
            print(f"  🔍 {total} jogos descobertos → catálogo agora com "
                  f"{catalog.size()} jogos (+{new_count} novos)")

            # ─── AUDITORIA: LIGAS DETECTADAS NO FLASHSCORE ─────────
            audit = catalog.leagues_audit()
            if audit["non_premium"]:
                print(f"\n  \033[90m📋 LIGAS NÃO PREMIUM ({len(audit['non_premium'])}):\033[0m")
                for L in audit["non_premium"][:6]:
                    print(f"     - {L['league_name']} | {L['country'] or '?'} | jogos={L['count']}")
                if len(audit["non_premium"]) > 6:
                    print(f"     ... (+{len(audit['non_premium']) - 6} omitidas)")
            if audit["unknown_league_count"] > 0:
                print(f"  \033[90m   {audit['unknown_league_count']} jogo(s) sem liga "
                      f"identificada (DOM walker não retornou header)\033[0m")

            # ─── Faxina do catálogo (anti-saturação Tier 3) ──────────
            # Remove jogos não vistos no discovery há > 30min E sem posição
            # aberta. Evita que o Tier 3 round-robin tenha centenas de
            # candidatos antigos competindo com jogos novos importantes.
            prune_stats = catalog.prune_stale_entries(
                not_seen_ttl_minutes=30,
                finished_ttl_hours=12,
            )
            if prune_stats["removed"] > 0:
                print(f"  🧹 Faxina: removidos {prune_stats['removed']} jogos "
                      f"(não vistos há >30min ou finalizados há >12h) "
                      f"→ catálogo enxuto com {prune_stats['kept']} jogos")
                catalog.save()

        # ─── Reconciliar catálogo com state.json ──────────────────
        _reconcile_catalog_with_state(catalog, state)

        # ─── Construir watchlist ──────────────────────────────────
        cycle_started_at = datetime.now(timezone.utc)
        max_entry = cfg.get("engine", {}).get("max_entry_minute", 83)
        anti_spam = cfg.get("engine", {}).get("signal_repeat_cooldown_minutes", 5)

        watchlist = build_watchlist(
            catalog,
            max_size=args.max_watchlist,
            tier3_reserved=args.tier3_reserved,
            entry_min_minute=20,
            entry_max_minute=max_entry,
            anti_spam_minutes=anti_spam,
        )

        # Construir (mid, url) pra passar pro scan + contar premium (Tier 0.5)
        mid_urls = []
        premium_in_watchlist = 0
        for mid in watchlist:
            entry = catalog.get(mid)
            if entry:
                mid_urls.append((mid, entry["url"]))
                if entry.get("is_premium"):
                    premium_in_watchlist += 1

        # ─── RELATÓRIO DE COBERTURA do ciclo ─────────────────────
        # Classifica TODOS os jogos do catálogo por motivo de inclusão/exclusão
        # da watchlist. Garantia operacional: nenhum jogo descartado sem motivo.
        coverage = _compute_coverage(catalog, watchlist, now=cycle_started_at)
        if (coverage["total"] - coverage["in_watchlist"]) > 0:
            excluded = coverage["total"] - coverage["in_watchlist"]
            print(f"  \033[90m📋 Cobertura: {coverage['total']} catalogados | "
                  f"{coverage['in_watchlist']} na watchlist | "
                  f"{excluded} excluídos: "
                  f"{coverage['excluded_duplicate']} duplicate, "
                  f"{coverage['excluded_no_stats']} sem_stats, "
                  f"{coverage['excluded_finished']} finished, "
                  f"{coverage['excluded_stale']} stale, "
                  f"{coverage['excluded_tier3_overflow']} tier3_overflow, "
                  f"{coverage['excluded_other_overflow']} other_overflow\033[0m")

        print(f"\n{'─' * 72}")
        print(f"  \033[1mSCAN #{cycle_count}\033[0m — {_ts()} — "
              f"Watchlist: {len(watchlist)} jogos "
              f"(catálogo: {catalog.size()})")
        # Tier 0.5 — informa quantos premium ao vivo estão na watchlist
        if premium_in_watchlist > 0:
            print(f"  \033[35m🏆 Premium ao vivo na watchlist: {premium_in_watchlist}\033[0m")

        # ─── SEÇÃO PREMIUM HIERÁRQUICA (A / B / C / PASSIVA) ────
        wl_set = set(watchlist)
        prem = catalog.premium_audit_by_level(wl_set)
        if prem["A"]:
            print(f"\n  \033[33m🏆 PREMIUM A — PRIORIDADE MÁXIMA\033[0m")
            for L in prem["A"]:
                print(f"     - {L['league']} | {L['country']} | "
                      f"live={L['live']} | watchlist={L['in_wl']} | "
                      f"passiva={L['passive']} | sem_stats={L['no_stats']}")
        if prem["B"]:
            print(f"  \033[36m🥈 PREMIUM B — COBERTURA SECUNDÁRIA\033[0m")
            for L in prem["B"][:8]:
                print(f"     - {L['league']} | {L['country']} | "
                      f"live={L['live']} | watchlist={L['in_wl']} | "
                      f"passiva={L['passive']} | sem_stats={L['no_stats']}")
            if len(prem["B"]) > 8:
                print(f"     ... (+{len(prem['B']) - 8} ligas omitidas)")
        if prem["C"]:
            print(f"  \033[90m🧩 PREMIUM C — FALLBACK POR TIME/SLUG\033[0m")
            for c in prem["C"][:6]:
                wl_flag = "watchlist" if c["in_wl"] else f"passiva ({c['passive_reason']})"
                print(f"     - {c['match_id']} | min={c['minute']} {c['score']} | {wl_flag}")
            if len(prem["C"]) > 6:
                print(f"     ... (+{len(prem['C']) - 6} jogos omitidos)")
        if prem["passive_entries"]:
            print(f"  \033[35m📋 COBERTURA PREMIUM PASSIVA ({len(prem['passive_entries'])})\033[0m")
            for p in prem["passive_entries"][:8]:
                print(f"     - [{p['level']}] {p['mid']} | {p['league_name']} | "
                      f"min={p['minute']} {p['score']} | motivo={p['passive_reason']}")
            if len(prem["passive_entries"]) > 8:
                print(f"     ... (+{len(prem['passive_entries']) - 8} omitidos)")

        print(SEPARATOR)
        sys.stdout.flush()

        # ─── Rodar scan ───────────────────────────────────────────
        # Branch entre os dois modos:
        #   codigo_3_1: agente simples Código 3:1 (default)
        #   motor_v12:  pipeline V1.2 antigo (rollback)
        cycle_stats = {"scanned": 0, "no_stats": 0, "alerts": 0,
                       "telegram_sent": 0, "errors": 0,
                       "cycle_time_seconds": 0.0}
        if mid_urls and not _PARAR:
            if args.mode == "codigo_3_1":
                cycle_stats = run_cycle_codigo_3_1(reader, mid_urls, tg, state, catalog,
                                                   read_match_timeout_ms=args.read_match_timeout_ms)
            else:  # motor_v12
                run_cycle_watchlist(reader, mid_urls, cfg, tg, state, catalog,
                                    read_match_timeout_ms=args.read_match_timeout_ms,
                                    stale_ttl_minutes=args.stale_ttl_min)
        elif not _PARAR:
            print(f"  \033[33m⚠️  Watchlist vazia neste ciclo\033[0m")

        catalog.save()

        # ─── COVERAGE GUARD (v2.4) ─────────────────────────────────
        # Audita: discovery viu como live, mas catálogo bloqueou indevidamente?
        # Recupera jogos cancerizados por motivos fracos (INVALID/AMBIGUOUS
        # _MINUTE_STATUS) E faz cap em backoff de premium A. Saída inclui
        # eventos pra display, persistência JSONL e Telegram crítico.
        coverage_report = None
        if args.mode == "codigo_3_1" and last_discovered_live_ids:
            try:
                from src import coverage_guard as _cg
                coverage_report = _cg.run_coverage_guard(
                    catalog=catalog,
                    discovered_live_ids=last_discovered_live_ids,
                    watchlist_ids=set(watchlist),
                    now=datetime.now(timezone.utc),
                )
                # Persiste eventos no JSONL
                if coverage_report.events:
                    _cg.append_to_jsonl(
                        Path("logs/live_coverage_guard.jsonl"),
                        coverage_report,
                    )
                # Salva catálogo de novo se o guard fez mutações
                if coverage_report.recovered_match_ids or \
                        coverage_report.stats.get("premium_a_backoff_capped", 0) > 0:
                    catalog.save()
                # Display do sumário
                print()
                print(_cg.format_terminal_summary(coverage_report))
                # Erros críticos
                from src.coverage_guard import (
                    SEV_CRITICAL, SEV_ERROR,
                    COVERAGE_AUTO_RECOVERED_LIVE_GAME,
                    COVERAGE_ERROR_PREMIUM_A_NOT_SCANNED_FAST,
                )
                for ev in coverage_report.events:
                    if ev.severity in (SEV_CRITICAL, SEV_ERROR):
                        print()
                        print(_cg.format_critical_event(ev))
                # Telegram crítico — POR PADRÃO DESLIGADO (v2.5).
                # Telegram é exclusivo de sinais da Regra 3.1.2.0. Coverage
                # Guard fica em terminal + logs + heartbeat. Pra ativar TG
                # técnico em debug: export TECHNICAL_TELEGRAM_ENABLED=1.
                from src.operational_config import coverage_guard_telegram_enabled
                if (coverage_guard_telegram_enabled()
                        and tg and tg.is_ready()
                        and coverage_report.telegram_critical):
                    for tg_item in coverage_report.telegram_critical:
                        msg = _cg.format_telegram_message(tg_item)
                        try:
                            tg.send_text(msg)
                        except Exception:
                            pass  # não derruba o ciclo se TG falhar
                sys.stdout.flush()
            except Exception as e:
                print(f"  \033[33m⚠️  Coverage Guard falhou: {e}\033[0m")

        # ─── Heartbeat (modo codigo_3_1 apenas) ──────────────────
        if args.mode == "codigo_3_1":
            # games_with_cc_available do catálogo: jogos que algum dia carregaram
            # stats (ever_loaded_stats=True). games_without_cc_available: o resto.
            all_games = catalog.all()
            cc_available_total = sum(1 for g in all_games if g.get("ever_loaded_stats"))
            cc_unavailable_total = len(all_games) - cc_available_total
            # games_skipped_this_cycle: jogos no catálogo com CC que NÃO foram
            # escaneados neste ciclo (estouraram a watchlist).
            scanned_now = int(cycle_stats.get("scanned", 0))
            skipped_this_cycle = max(0, cc_available_total - scanned_now)
            # Tier 0.5: contar premium efetivamente escaneados neste ciclo
            # (entries com last_scanned_at posterior ao início do ciclo).
            premium_scanned_now = 0
            for g in all_games:
                if not g.get("is_premium"):
                    continue
                ls = g.get("last_scanned_at") or ""
                if not ls:
                    continue
                try:
                    ts = datetime.fromisoformat(ls)
                    if ts >= cycle_started_at:
                        premium_scanned_now += 1
                except (ValueError, TypeError):
                    pass
            try:
                save_heartbeat(
                    scan_number=cycle_count,
                    last_scan_at=datetime.now(timezone.utc).isoformat(),
                    last_scan_duration_seconds=cycle_stats.get("cycle_time_seconds", 0.0),
                    total_live_games_discovered=last_discovery_total,
                    games_discovered=last_discovery_total,
                    games_with_cc_available=cc_available_total,
                    games_without_cc_available=cc_unavailable_total,
                    games_finished_or_not_live=int(cycle_stats.get("not_live", 0)),
                    games_excluded_finished_or_not_live=catalog.count_finished_or_not_live(),
                    games_scanned=scanned_now,
                    games_scanned_this_cycle=scanned_now,
                    games_skipped_this_cycle=skipped_this_cycle,
                    telegram_ready=bool(tg and tg.is_ready()),
                    telegram_sent_last_cycle=int(cycle_stats.get("telegram_sent", 0)),
                    errors_last_cycle=int(cycle_stats.get("errors", 0)),
                    target_scan_interval_seconds=int(args.scan_interval),
                    no_stats_backoff_count=catalog.count_in_backoff(),
                    games_skipped_by_no_stats_backoff=int(
                        cycle_stats.get("skipped_by_backoff", 0)
                    ),
                    premium_live_games_in_watchlist=premium_in_watchlist,
                    premium_live_games_scanned_this_cycle=premium_scanned_now,
                    coverage=coverage,
                    coverage_guard=(coverage_report.stats if coverage_report
                                     else {}),
                )
            except Exception as e:
                print(f"  \033[33m⚠️  Heartbeat falhou: {e}\033[0m")
            # v2.9 — tick final do ciclo (mesmo se heartbeat falhar acima,
            # tick é leve e atômico — daemon não é morto pelo watchdog).
            _touch_live_tick(source="cycle_end")

        if args.once:
            break

        # ─── Sleep com cadência corrigida ─────────────────────────
        if not _PARAR:
            elapsed = time.time() - loop_start
            remaining = max(15, int(args.scan_interval - elapsed))
            print(f"\n  ⏳ Dormindo {remaining}s (elapsed={elapsed:.1f}s, "
                  f"target={args.scan_interval}s)... (Ctrl+C para parar)")
            # v2.9 — toca tick ANTES de dormir e a cada 15s DURANTE o
            # sleep, pra watchdog não matar daemon vivo entre ciclos.
            _touch_live_tick(source="sleep_start")
            for _i in range(remaining):
                if _PARAR:
                    break
                time.sleep(1)
                if (_i + 1) % 15 == 0:
                    _touch_live_tick(source="sleep")


# ─── Modo CÓDIGO 3:1 (agente simples — Matriz das Chances Claras) ─────
# Pipeline minimalista: read_match → codigo_3_1.evaluate_codigo_3_1 → Telegram.
# NÃO chama decision_engine, run_scan, post_position, telegram_client.send_decision.
# Regras V1.2 ficam inertes (preservadas em código pra rollback via --mode motor_v12).
# Dossiê: docs/current/Codigo_3_1_Matriz_das_Chances_Claras.md

# ─── Filtro de elegibilidade: jogo realmente ao vivo? ─────────────────
# Dossiê v1.1 ajuste: a discovery do Flashscore às vezes traz jogos
# recém-finalizados/agendados/suspensos. Aqui filtramos antes do scan
# operacional do Código 3:1. Não substitui a regra — apenas evita gastar
# slot com jogo morto.
import re as _re_filter

_NOT_LIVE_FINISHED = [
    "TERMINADO", "ENCERRADO", "FINALIZADO",
    "FINISHED",
    "AET", "APÓS PROR", "APOS PROR", "APÓS PRORROGAÇÃO",
    "APÓS PEN", "APOS PEN", "APÓS PÊN", "APOS PÊN",
    "AFTER PEN", "PENALTIES", "PÊNALTIS", "PENALTIS", "PEN.",
]
_NOT_LIVE_SCHEDULED = [
    "AGUARDANDO", "AGUARDA", "SCHEDULED", "NOT STARTED", "À INICIAR",
    "A INICIAR", "PROGRAMADO",
]
_NOT_LIVE_SUSPENDED = [
    "POSTPONED", "ADIADO",
    "CANCELLED", "CANCELED", "CANCELADO",
    "SUSPENDED", "SUSPENSO",
    "ABANDONED", "ABANDONADO",
    "WALKOVER", "W.O.",
    "INTERRUPTED", "INTERROMPIDO",
]
# "FT" precisa boundary porque "1ST"/"FIRST HALF" contém "ST"
_FT_RE = _re_filter.compile(r"\bFT\b|\bFULL[\s\-]?TIME\b")


def is_live_match(ms: MatchState) -> tuple:
    """Retorna (is_live: bool, reason: str).

    Indicadores prioritários no status_raw textual (fonte de verdade do Flashscore).
    Fallback minute-based só quando status_raw está vazio.

    reasons quando não-live:
      NOT_LIVE_STATUS           — scheduled, suspended, postponed, cancelled, abandoned
      FINISHED_MATCH            — TERMINADO/FT/FINISHED/AET/PEN
      INVALID_MINUTE_STATUS     — minuto inválido COM evidência (>130 ou
                                   status textual presente mas não reconhecido).
                                   Caller marca finished_or_not_live (TTL 12h).
      AMBIGUOUS_MINUTE_STATUS   — status_raw vazio E minute<=0. Leitura
                                   ambígua — o jogo pode estar em kickoff
                                   (DOM ainda preenchendo minute/status).
                                   Caller deve NÃO marcar finished_or_not_live;
                                   em vez disso usar mark_no_stats (backoff
                                   curto) para retry no próximo ciclo.
    """
    status_upper = (getattr(ms, "status_raw", "") or "").upper().strip()
    minute = int(getattr(ms, "minute", 0) or 0)

    # ─── Cheque 1: status indica finalizado
    if any(ind in status_upper for ind in _NOT_LIVE_FINISHED):
        return False, "FINISHED_MATCH"
    if _FT_RE.search(status_upper):
        return False, "FINISHED_MATCH"

    # ─── Cheque 2: status indica suspended/cancelado/postponed
    if any(ind in status_upper for ind in _NOT_LIVE_SUSPENDED):
        return False, "NOT_LIVE_STATUS"

    # ─── Cheque 3: status indica scheduled/agendado
    if any(ind in status_upper for ind in _NOT_LIVE_SCHEDULED):
        return False, "NOT_LIVE_STATUS"

    # ─── Cheque 4: minuto inválido — DISTINGUIR ambíguo vs definido (v2.3)
    # Bug histórico: jogos recém-iniciados (kickoff em curso) eram lidos com
    # status_raw="" e minute=0 antes do DOM completar, e o sistema marcava
    # finished_or_not_live por 12h. Agora: status_raw vazio + minute<=0 =
    # AMBÍGUO (caller faz backoff curto, não bloqueio longo).
    if minute <= 0:
        if not status_upper:
            return False, "AMBIGUOUS_MINUTE_STATUS"
        return False, "INVALID_MINUTE_STATUS"

    # ─── Cheque 5: minuto absurdo (>130) — defesa
    if minute > 130:
        return False, "INVALID_MINUTE_STATUS"

    # ─── Cheque 6 (v2.8): minuto >= 95 sem indicador de extra time → likely
    # finished. Cup matches podem ir até 120, então preservamos quando o
    # status indica "extra time", "prorrogação", "pênaltis", etc.
    if minute >= 95:
        EXTRA_LONG = ("EXTRA", "PROR", "PRORROGA",
                      "OVERTIME", "PEN", "PÊN", "PENAL")
        is_extra = any(m in status_upper for m in EXTRA_LONG)
        # Word-boundary check para "ET" e "OT" (não bater "BET", "POT" etc)
        if not is_extra:
            words = set(_re_filter.split(r"[^A-ZÀ-Ú]+", status_upper))
            is_extra = bool(words & {"ET", "OT"})
        if not is_extra:
            return False, "MINUTE_OVER_95_LIKELY_FINISHED"

    # Senão: live (1st half, 2nd half, half time, injury time, etc.)
    return True, ""


def save_heartbeat(*, scan_number: int, last_scan_at: str,
                    last_scan_duration_seconds: float,
                    total_live_games_discovered: int,
                    games_discovered: int,
                    games_with_cc_available: int,
                    games_without_cc_available: int,
                    games_scanned: int,
                    games_scanned_this_cycle: int,
                    games_skipped_this_cycle: int,
                    telegram_ready: bool,
                    telegram_sent_last_cycle: int,
                    errors_last_cycle: int,
                    games_finished_or_not_live: int = 0,
                    target_scan_interval_seconds: int = 120,
                    no_stats_backoff_count: int = 0,
                    games_skipped_by_no_stats_backoff: int = 0,
                    games_excluded_finished_or_not_live: int = 0,
                    premium_live_games_in_watchlist: int = 0,
                    premium_live_games_scanned_this_cycle: int = 0,
                    coverage: Optional[dict] = None,
                    coverage_guard: Optional[dict] = None,
                    mode: str = "codigo_3_1") -> None:
    """Persiste heartbeat conforme dossiê v1.1 Seção 13.1.

    O daemon NUNCA envia Telegram dizendo 'estou vivo'. Apenas escreve aqui.
    O watchdog.py lê esse arquivo e decide se há problema.

    games_finished_or_not_live: jogos descartados pelo filtro is_live_match
    (FT/FINISHED/AET/SUSPENDED/POSTPONED/CANCELLED/SCHEDULED). Adicionado
    no ajuste cirúrgico pós-v1.1.
    """
    LOG_DIR.mkdir(exist_ok=True)
    duration = round(float(last_scan_duration_seconds), 2)
    target = int(target_scan_interval_seconds)
    delay = max(0, int(duration - target))
    payload = {
        "status": "alive",
        "terminal_name": "O Código 3:1",
        "mode": mode,
        "last_scan_at": last_scan_at,
        "last_scan_duration_seconds": duration,
        "actual_cycle_duration_seconds": duration,    # alias do user
        "target_scan_interval_seconds": target,
        "cycle_over_target": duration > target,
        "scan_delay_seconds": delay,
        "scan_number": int(scan_number),
        "total_live_games_discovered": int(total_live_games_discovered),
        "games_discovered": int(games_discovered),
        "games_with_cc_available": int(games_with_cc_available),
        "games_without_cc_available": int(games_without_cc_available),
        "games_finished_or_not_live": int(games_finished_or_not_live),
        "games_scanned": int(games_scanned),
        "games_scanned_this_cycle": int(games_scanned_this_cycle),
        "games_skipped_this_cycle": int(games_skipped_this_cycle),
        "no_stats_backoff_count": int(no_stats_backoff_count),
        "games_skipped_by_no_stats_backoff": int(games_skipped_by_no_stats_backoff),
        "games_excluded_finished_or_not_live": int(games_excluded_finished_or_not_live),
        "premium_live_games_in_watchlist": int(premium_live_games_in_watchlist),
        "premium_live_games_scanned_this_cycle": int(premium_live_games_scanned_this_cycle),
        "coverage": dict(coverage) if isinstance(coverage, dict) else {},
        # v2.4 — Coverage Guard
        "coverage_guard": dict(coverage_guard) if isinstance(coverage_guard, dict) else {},
        "coverage_live_discovered": int((coverage_guard or {}).get("live_discovered", 0)),
        "coverage_scanned_this_cycle": int((coverage_guard or {}).get("scanned_this_cycle", 0)),
        "coverage_errors": int((coverage_guard or {}).get("coverage_errors", 0)),
        "coverage_recovered_live_games": int((coverage_guard or {}).get("recovered_live_games", 0)),
        "coverage_premium_a_missing": int((coverage_guard or {}).get("premium_a_recovered", 0)),
        "coverage_last_error": "",   # preenchido pelo daemon caso queira propagar texto
        "telegram_ready": bool(telegram_ready),
        "telegram_sent_last_cycle": int(telegram_sent_last_cycle),
        "errors_last_cycle": int(errors_last_cycle),
    }
    with open(HEARTBEAT_FILE, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _save_codigo_3_1_log(ms: MatchState, decision: dict):
    """Log JSONL do modo codigo_3_1 com todos os campos da spec."""
    LOG_DIR.mkdir(exist_ok=True)
    fields = (decision or {}).get("telegram_message_fields", {}) or {}
    home_bc = int(ms.home_bc or 0)
    away_bc = int(ms.away_bc or 0)
    home_score = int(ms.home_score or 0)
    away_score = int(ms.away_score or 0)
    total_cc = home_bc + away_bc
    total_goals = home_score + away_score
    cc_rate = (ms.minute / total_cc) if total_cc > 0 else 999.0
    expected_goals_by_cc = total_cc // 3
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "codigo_3_1",
        "match_id": ms.match_id,
        "home": ms.home,
        "away": ms.away,
        "minute": ms.minute,
        "score": f"{home_score}-{away_score}",
        "home_bc": home_bc,
        "away_bc": away_bc,
        "total_cc": total_cc,
        "total_goals": total_goals,
        "cc_rate": round(cc_rate, 2),
        "expected_goals_by_cc": expected_goals_by_cc,
        "alert_type": (decision or {}).get("alert_type"),
        "bucket": int((decision or {}).get("bucket", 0) or 0),
        "should_alert": bool((decision or {}).get("should_alert", False)),
        "telegram_sent": bool((decision or {}).get("_sent", False)),
        "filter_reason": (decision or {}).get("reason", "") if not (decision or {}).get("should_alert") else "",
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_cycle_codigo_3_1(reader: FlashscoreReader, mid_urls: list,
                          tg: TelegramClient, state: dict, catalog: Catalog,
                          read_match_timeout_ms: int = 18000) -> dict:
    """Ciclo de scan no modo CÓDIGO 3:1.

    Para cada (match_id, url):
      1. read_match (mesmo extrator do modo V1.2)
      2. codigo_3_1.evaluate_codigo_3_1(ms, previous_alert_state)
      3. Se should_alert → envia Telegram direto + atualiza state (anti-spam)
      4. Log JSONL completo (todos os campos da spec)

    Retorna stats com chaves: scanned, alerts, telegram_sent, errors, no_stats,
    cycle_time_seconds. games_with_cc_available = scanned (ms != None).
    games_without_cc_available = no_stats (read_match retornou None).
    """
    stats = {"scanned": 0, "alerts": 0, "telegram_sent": 0,
             "errors": 0, "no_stats": 0, "not_live": 0,
             "skipped_by_backoff": 0}
    cycle_start = time.time()

    # ─── Timeout adaptativo (ajuste cirúrgico de cadência) ────
    # Jogos que já provaram não ter stats (no_stats_count >= 1) recebem
    # timeout REDUZIDO no próximo read_match — basta confirmar rapidamente
    # se voltou a ter stats ou não. Default 18s só pra jogos novos / com stats.
    SHORT_TIMEOUT_MS = 6000     # 6s pra jogos no_stats conhecidos
    NORMAL_TIMEOUT_MS = read_match_timeout_ms  # 18s default

    # v2.8 — Toque ANTES do loop pra watchdog ver tick fresco
    _touch_live_tick(source="cycle_start")
    _games_since_tick = 0
    # R5 — Resumo agrupado de excluídos (printado UMA vez no fim do ciclo,
    # em vez de N×20 prints poluindo terminal). Categoriza por reason.
    _cycle_excludeds: dict = {}

    for mid, url in mid_urls:
        if _PARAR:
            break

        # v2.8 — Tick ANTES E DEPOIS da leitura. Toque a cada 3 jogos pra
        # watchdog não matar daemon durante scan longo.
        _games_since_tick += 1
        if _games_since_tick >= 3:
            _touch_live_tick(source="scan")
            _games_since_tick = 0

        # Backoff ativo? Catalog.is_no_stats_active garante que jogos em
        # backoff não vêm pela watchlist (filtrado em build_watchlist), mas
        # contamos aqui por segurança caso a watchlist mude no futuro.
        if catalog.is_no_stats_active(mid):
            stats["skipped_by_backoff"] += 1
            _cycle_excludeds.setdefault("backoff_no_stats", []).append(mid)
            continue

        # R2 — Pre-read eligibility: detecta reserve/youth ANTES de abrir
        # Flashscore. Economiza leitura cara em jogos que seriam bloqueados
        # de qualquer forma após o read_match.
        try:
            cat_entry = catalog.get(mid) or {}
            pre = _op_filter.pre_read_eligibility(cat_entry)
            if not pre["eligible"]:
                _cycle_excludeds.setdefault(
                    f"pre_read_{pre['reason']}", []).append(mid)
                _op_filter.add_cooldown(mid, minutes=60)  # 1h pra reserva
                try:
                    _op_filter.log_exclusion({
                        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                        "match_id": mid, "reason": pre["reason"],
                        "detected_in": pre.get("detected_in"),
                        "source": pre.get("source"),
                        "action": "pre_read_skip",
                    })
                except Exception: pass
                continue
        except Exception:
            pass  # pre-read filter nunca derruba ciclo

        # Timeout reduzido se o jogo já não-teve stats antes
        timeout_ms = (SHORT_TIMEOUT_MS if catalog.should_use_short_timeout(mid)
                      else NORMAL_TIMEOUT_MS)

        ms = reader.read_match(url, timeout_ms=timeout_ms)
        if ms is None:
            stats["no_stats"] += 1
            catalog.mark_no_stats(mid)
            name = mid.replace("FS_", "")[:12]
            print(f"  \033[90m⚫ {name}... sem stats\033[0m")
            sys.stdout.flush()
            continue

        # v2.8 — ms veio mas TODOS os _raw são None (página carregou mas
        # zero stats no DOM — comum em ligas sem cobertura). Marca como
        # sem_stats pra entrar em cooldown e não consumir slot todo ciclo.
        if _all_raw_metrics_missing(ms):
            stats["no_stats"] += 1
            catalog.mark_no_stats(mid)
            name = (ms.home or mid.replace("FS_", ""))[:14]
            print(f"  \033[90m⚫ {name}... stats vazias (todos _raw=None)\033[0m")
            sys.stdout.flush()
            continue

        # ─── FILTRO DE ELEGIBILIDADE: jogo realmente ao vivo? ─────
        # Antes do scan operacional, descartar finalizados/agendados/suspensos.
        live, not_live_reason = is_live_match(ms)

        # ✨ v4.4 — FORÇAR PDF do bloco FINAL antes de descartar
        # Bug: ciclo de 2min podia pular do min 88 pro min 92+ sem processar
        # bloco 90. Agora: ao detectar transição pra finished, se ainda não
        # enviou o bloco 90, força envio com dados atuais.
        if not live and not_live_reason in (
            "FINISHED_MATCH", "MINUTE_OVER_95_LIKELY_FINISHED"
        ):
            try:
                # ✨ v4.7 — Recarrega do disco pra ver state atualizado pelo
                # bloco normal (anti-dup entre bloco normal + FINAL forçado)
                _bs_state_f = globals().get("_bs_state") or {}
                _BSF_check = Path(__file__).parent / "logs" / "block_sent_state.json"
                if _BSF_check.exists():
                    try:
                        with open(_BSF_check) as _fp_chk:
                            _bs_state_f = json.load(_fp_chk)
                    except Exception:
                        pass
                _block_sent_f = _bs_state_f.get("block_sent", {}) if _bs_state_f else {}
                _last_block_f = _block_sent_f.get(mid, 0)
                if _last_block_f < 90:
                    # Constrói _ms_dict com os dados do snapshot final
                    _ms_dict_f = {
                        "match_id": mid, "home": ms.home, "away": ms.away,
                        "minute": max(90, ms.minute or 90),
                        "home_score": ms.home_score, "away_score": ms.away_score,
                        "home_cc": ms.home_bc, "away_cc": ms.away_bc,
                        "home_xg": ms.home_xg, "away_xg": ms.away_xg,
                        "home_xgot": ms.home_xgot, "away_xgot": ms.away_xgot,
                        "home_xa": getattr(ms, "home_xa", 0.0),
                        "away_xa": getattr(ms, "away_xa", 0.0),
                        "home_shots": ms.home_shots, "away_shots": ms.away_shots,
                        "home_sot": ms.home_sot, "away_sot": ms.away_sot,
                        "all_stats": getattr(ms, "all_stats", {}) or {},
                    }
                    # Salva snapshot final no timeline
                    _tl.append_snapshot(_ms_dict_f)
                    _timeline_f = _tl.load_timeline(mid)
                    # Bloco 75-90 (último bloco)
                    _block_ms_f = _tl.compute_block_delta(_timeline_f, 75, 90)
                    _block_ms_f["match_id"] = mid
                    _block_ms_f["home"] = ms.home
                    _block_ms_f["away"] = ms.away
                    _ctx_f = _rd.extract_context(_block_ms_f.get("all_stats", {}))
                    _score_f = _sc.evaluate(_block_ms_f)
                    _scenario_f = _rd.detect_scenario(_score_f, _ctx_f, _block_ms_f)
                    _narr_f = _rd.coach_narrative(_block_ms_f, _ctx_f, _scenario_f, _score_f)
                    # Tendência + mercados
                    _ctx_acc_f = _rd.extract_context(_ms_dict_f.get("all_stats", {}))
                    _sc_acc_f = _rd.detect_scenario(_sc.evaluate(_ms_dict_f), _ctx_acc_f, _ms_dict_f)
                    from src import trend_engine as _trend_f
                    from src import match_probability as _prob_f
                    from src import match_pdf as _pdf_f
                    _trend_d_f = _trend_f.detect_trend(
                        _ms_dict_f, _ctx_acc_f, _sc_acc_f,
                        block_data=_block_ms_f)
                    _league_f = ""
                    try:
                        _cat_e_f = catalog.get_entry(mid) or {}
                        _league_f = _cat_e_f.get("league_name", "") or ""
                    except Exception:
                        pass
                    _markets_f = _prob_f.compute_all_markets(
                        _ms_dict_f, _sc_acc_f, league_name=_league_f)
                    _pdf_path_f = _pdf_f.build_block_report_pdf(
                        _block_ms_f, _score_f, _scenario_f, _ctx_f, 90,
                        _narr_f, score_history=[],
                        derivatives={}, trend=_trend_d_f, markets=_markets_f)
                    if tg and tg.is_ready():
                        _caption_f = (
                            f"⚽ {ms.home} {ms.home_score}-{ms.away_score} "
                            f"{ms.away} · FINAL · min {ms.minute}"
                        )
                        _ok_f = tg.send_document(_pdf_path_f, caption=_caption_f)
                        if _ok_f:
                            stats["telegram_sent"] += 1
                            _block_sent_f[mid] = 90
                            # Persiste
                            try:
                                _BSF = Path(__file__).parent / "logs" / "block_sent_state.json"
                                _BSF.parent.mkdir(parents=True, exist_ok=True)
                                with open(_BSF, "w") as _fp:
                                    json.dump(_bs_state_f, _fp, ensure_ascii=False)
                            except Exception:
                                pass
                            print(f"     \033[35m📊 FINAL bloco 90 PDF → TG (forçado)\033[0m")

                # ✨ v4.5 — RELATÓRIO EXECUTIVO COMPLETO de fim de jogo
                # Sempre que detectar finished, gera o exec_report e envia
                _exec_state = globals().setdefault("_exec_report_sent", {})
                _ESF = Path(__file__).parent / "logs" / "exec_report_state.json"
                if not _exec_state and _ESF.exists():
                    try:
                        with open(_ESF) as _fp:
                            _exec_state.update(json.load(_fp))
                    except Exception:
                        pass
                if mid not in _exec_state:
                    try:
                        from src.match_final_report_pdf import build_final_report_pdf
                        _exec_timeline = _tl.load_timeline(mid, max_snapshots=200)
                        if _exec_timeline:
                            for _s in _exec_timeline:
                                _s.setdefault("match_id", mid)
                            _league_exec = ""
                            try:
                                _ce = catalog.get_entry(mid) or {}
                                _league_exec = _ce.get("league_name", "") or ""
                            except Exception:
                                pass
                            _exec_pdf = build_final_report_pdf(
                                _exec_timeline, league_name=_league_exec)
                            if tg and tg.is_ready():
                                _h_n = ms.home; _a_n = ms.away
                                _h_g = ms.home_score; _a_g = ms.away_score
                                _cap_exec = (
                                    f"📋 RELATÓRIO EXECUTIVO · "
                                    f"{_h_n} {_h_g}-{_a_g} {_a_n} · "
                                    f"Análise completa"
                                )
                                _ok_exec = tg.send_document(_exec_pdf, caption=_cap_exec)
                                if _ok_exec:
                                    _exec_state[mid] = True
                                    try:
                                        _ESF.parent.mkdir(parents=True, exist_ok=True)
                                        with open(_ESF, "w") as _fp:
                                            json.dump(_exec_state, _fp)
                                    except Exception:
                                        pass
                                    stats["telegram_sent"] += 1
                                    print(f"     \033[36m📋 RELATÓRIO EXEC → TG\033[0m")
                    except Exception as _e_exec:
                        print(f"     \033[33m⚠️  Exec report falhou: {_e_exec}\033[0m")
                        import traceback as _te
                        print(_te.format_exc()[:400])
            except Exception as _e_f:
                print(f"     \033[33m⚠️  PDF final forçado falhou: {_e_f}\033[0m")
                import traceback as _tb_f
                print(_tb_f.format_exc()[:500])

        if not live:
            stats["not_live"] += 1
            short = (ms.home or "?")[:18]
            short2 = (ms.away or "?")[:18]
            print(f"  \033[90m⚫ {short} x {short2} | min {ms.minute} | "
                  f"status='{ms.status_raw[:30]}' → {not_live_reason}\033[0m")
            # AMBÍGUO: status_raw vazio + minute<=0. NÃO marcar finished_or_not_live
            # (TTL 12h sequestra jogos em kickoff). Tratar como leitura sem stats,
            # backoff curto via mark_no_stats. Retry nos próximos ciclos.
            # — v2.3 (bug Nacional × Coquimbo).
            if not_live_reason == "AMBIGUOUS_MINUTE_STATUS":
                stats["no_stats"] = stats.get("no_stats", 0) + 1
                catalog.mark_no_stats(mid)
            elif not_live_reason == "MINUTE_OVER_95_LIKELY_FINISHED":
                # v2.8 — TTL curto (1h) porque o status pode mudar pra
                # FINISHED ou pra "EXTRA TIME" rapidamente. Não sequestra.
                catalog.mark_finished_or_not_live(mid, not_live_reason,
                                                    ttl_hours=1)
            else:
                # MARCAR no catálogo com TTL longo (12h) — evita reescaneamento
                # do mesmo finalizado/suspenso/postponed em cada ciclo.
                catalog.mark_finished_or_not_live(mid, not_live_reason,
                                                    ttl_hours=12)
                # v2.7 — Banco estruturado: finalizar sinais deste match
                # apenas quando o status é FINISHED_MATCH (placar do scan
                # provavelmente é o final). Outros motivos (suspenso, etc.)
                # NÃO finalizam — ficam sem result_finalized.
                if not_live_reason == "FINISHED_MATCH":
                    try:
                        from src import signals_persistence as _sp
                        _sp.finalize_signals_for_match(
                            mid, final_home_score=ms.home_score,
                            final_away_score=ms.away_score,
                            final_minute=ms.minute,
                            reason=not_live_reason,
                            persist_path=Path("logs/rule_3_1_2_signals.jsonl"),
                        )
                    except Exception:
                        pass
            # Log JSONL: registra descarte (para auditoria)
            _save_codigo_3_1_log(ms, {
                "alert_type": None,
                "should_alert": False,
                "reason": not_live_reason,
                "bucket": 0,
                "telegram_message_fields": {},
                "_sent": False,
            })
            sys.stdout.flush()
            continue

        stats["scanned"] += 1

        # v3.2 — TURBO QUÁDRUPLA + LEITURA TÁTICA
        # ATENÇÃO: gate temporariamente LIBERADO pra TODOS os jogos
        # (data FIFA, poucos jogos disponíveis). Filtros operacionais
        # (reservas, U17-U23, finalizados) continuam ativos antes.
        # Pra voltar ao Premium A+B: trocar True por
        #   _cat_entry.get("premium_level", "NONE") in ("A", "B")
        _cat_entry = catalog.get(mid) or {}
        _premium_level = _cat_entry.get("premium_level", "NONE")
        _is_premium_a_or_b = True   # ← liberado hoje. Voltar pra A+B depois.
        if _is_premium_a_or_b:
            try:
                from src import match_timeline as _tl
                from src import turbo_score as _sc
                from src import match_reader as _rd
                _ms_dict = {
                    "match_id": mid, "home": ms.home, "away": ms.away,
                    "minute": ms.minute,
                    "home_score": ms.home_score, "away_score": ms.away_score,
                    "home_cc": ms.home_bc, "away_cc": ms.away_bc,
                    "home_xg": ms.home_xg, "away_xg": ms.away_xg,
                    "home_xgot": ms.home_xgot, "away_xgot": ms.away_xgot,
                    "home_xa": getattr(ms, "home_xa", 0.0),
                    "away_xa": getattr(ms, "away_xa", 0.0),
                    "home_shots": ms.home_shots, "away_shots": ms.away_shots,
                    "home_sot": ms.home_sot, "away_sot": ms.away_sot,
                    "all_stats": getattr(ms, "all_stats", {}) or {},
                }
                _tl.append_snapshot(_ms_dict)
                _score_result = _sc.evaluate(_ms_dict)
                _ctx = _rd.extract_context(_ms_dict["all_stats"])
                _scenario = _rd.detect_scenario(_score_result, _ctx, _ms_dict)
                _timeline = _tl.load_timeline(mid)
                _deriv = _tl.compute_derivatives(_timeline,
                                                  current_minute=ms.minute)

                # ✨ v4.2 — ROTA PRESSÃO VENDÁVEL (BACK alta + LAY baixa)
                # Roda em PARALELO à Quádrupla. Avalia se há trade de
                # entrada com odd ainda alta (time empatado ou atrás de 1
                # gol, mas pressionando muito). Anti-spam de 10min por mid.
                try:
                    from src import pressao_vendavel as _pv
                    from src import match_pdf as _pdf_pv
                    _pv_result = _pv.evaluate(_ms_dict, _ctx, _scenario)
                    if _pv_result.get("qualified"):
                        # Anti-spam: não envia 2x em < 10 min
                        from datetime import datetime as _dt, timezone as _tz
                        _pv_state = globals().setdefault("_pv_alert_state", {})
                        _PV_STATE_FILE = Path(__file__).parent / "logs" / "pv_alert_state.json"
                        # Carrega state se primeira vez
                        if not _pv_state and _PV_STATE_FILE.exists():
                            try:
                                with open(_PV_STATE_FILE) as _f:
                                    _pv_state.update(json.load(_f))
                            except Exception:
                                pass
                        _now = _dt.now(_tz.utc)
                        _last_ts = _pv_state.get(mid)
                        _send_pv = True
                        if _last_ts:
                            try:
                                _last_dt = _dt.fromisoformat(_last_ts)
                                _elapsed_min = (_now - _last_dt).total_seconds() / 60.0
                                if _elapsed_min < 10:
                                    _send_pv = False
                            except Exception:
                                pass
                        if _send_pv and tg and tg.is_ready():
                            _pv_pdf = _pdf_pv.build_pressao_vendavel_pdf(
                                _ms_dict, _pv_result, _ctx)
                            _team = _pv_result["team"]
                            _prob_d = _pv_result.get("probability", {})
                            _min_odd = _prob_d.get("min_recommended_odd", "?")
                            _prob_pct = _prob_d.get("prob_target", "?")
                            _h_g = _ms_dict.get("home_score", 0)
                            _a_g = _ms_dict.get("away_score", 0)
                            _h_n = _ms_dict.get("home", "?")
                            _a_n = _ms_dict.get("away", "?")
                            # ✨ v4.8 — Caption chamativa pra ENTRADA destacar
                            # visualmente das mensagens de bloco (informativas).
                            # Hierarquia: gatilho → ação → match → dados → guard-rail.
                            # ⚡ = gatilho/ação (não 🚨 que sinaliza perigo).
                            # "SINAL DE ENTRADA" = linguagem nativa de trader.
                            # 51' = convenção esportiva universal.
                            _caption = (
                                f"⚡ SINAL DE ENTRADA ⚡\n"
                                f"\n"
                                f"🎯 BACK {_team}\n"
                                f"⚽ {_h_n} {_h_g}-{_a_g} {_a_n}\n"
                                f"⏱ {ms.minute}' · 📊 {_prob_pct}% · "
                                f"💰 odd mín {_min_odd}\n"
                                f"\n"
                                f"⚠️ Só entrar se odd ≥ {_min_odd}"
                            )
                            _ok_pv = tg.send_document(_pv_pdf, caption=_caption)
                            if _ok_pv:
                                _pv_state[mid] = _now.isoformat()
                                try:
                                    _PV_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                                    with open(_PV_STATE_FILE, "w") as _f:
                                        json.dump(_pv_state, _f)
                                except Exception:
                                    pass
                                stats["telegram_sent"] += 1
                                print(f"     \033[32m🎯 BACK {_team} (entrada) → TG\033[0m")
                except Exception as _e_pv:
                    print(f"     \033[33m⚠️  Pressão Vendável falhou: {_e_pv}\033[0m")
                    import traceback as _tb_pv
                    print(_tb_pv.format_exc()[:400])
                _report_md = _rd.build_tactical_report_md(
                    _ms_dict, _score_result, _scenario, _ctx, _deriv)
                _rd.append_tactical_report(mid, _report_md)
                # v3.5 — Narrativa via TELEGRAM ao fim de bloco
                # Modo PADRÃO: só envia min 30 e 60
                # Modo INTENSIVO: envia em todos (15/30/45/60/75/90)
                _current_block = _rd._what_block(ms.minute)
                if _current_block > 0:
                    # v3.8 — Persistir block_sent em disco pra sobreviver
                    # a restart do daemon (corrige PDF duplicado)
                    _BLOCK_STATE_FILE = Path(__file__).parent / "logs" / "block_sent_state.json"
                    # ✨ v4.5 — Marca quando enviou bloco FINAL pra disparar
                    # relatório executivo automaticamente
                    def _load_bs():
                        try:
                            if _BLOCK_STATE_FILE.exists():
                                with open(_BLOCK_STATE_FILE) as _f:
                                    return json.load(_f)
                        except Exception:
                            pass
                        return {"block_sent": {}, "score_history": {}}
                    def _save_bs(_st):
                        try:
                            _BLOCK_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                            with open(_BLOCK_STATE_FILE, "w") as _f:
                                json.dump(_st, _f, ensure_ascii=False)
                        except Exception:
                            pass
                    _bs_state = globals().setdefault("_bs_state", _load_bs())
                    _block_sent = _bs_state["block_sent"]
                    _score_history = _bs_state["score_history"]
                    _last_block = _block_sent.get(mid, 0)
                    # Atualiza histórico de score do match
                    _score_history.setdefault(mid, []).append(_score_result.get("score", 0.0))
                    if len(_score_history[mid]) > 10:
                        _score_history[mid] = _score_history[mid][-10:]
                    if _current_block > _last_block:
                        _intensive, _i_reason = _rd.is_intensive_mode(
                            _score_result, _scenario, _score_history[mid])
                        if _rd.should_send_block_report(_current_block, _intensive):
                            # ✨ v4.7 — Anti-dup RIGOROSO: persiste ANTES do envio
                            # com chave (mid, block) atômica. Evita race entre
                            # ciclos sucessivos e duplo envio (bloco normal +
                            # PDF FINAL forçado v4.4 disparando simultaneamente).
                            _block_sent[mid] = _current_block
                            _save_bs(_bs_state)  # ← LOCK pessimista: persiste antes
                            if tg and tg.is_ready():
                                try:
                                    # v4.1 — Calcula dados DO BLOCO (delta)
                                    # em vez de usar acumulados
                                    _block_start = max(0, _current_block - 15)
                                    _block_ms = _tl.compute_block_delta(
                                        _timeline, _block_start, _current_block)
                                    # Para bloco 1, "início" é zero — block_ms = acumulado
                                    # Para bloco 45 (HT), capture 0-45 ao invés de 30-45:
                                    # HT é resumo do 1º tempo inteiro
                                    if _current_block == 45:
                                        _block_ms = _tl.compute_block_delta(
                                            _timeline, 0, 45)

                                    # Reusa nome/match_id/all_stats do _ms_dict
                                    _block_ms.setdefault("match_id", mid)
                                    _block_ms.setdefault("home", _ms_dict.get("home",""))
                                    _block_ms.setdefault("away", _ms_dict.get("away",""))

                                    # Cenário e narrativa usam DADOS DO BLOCO
                                    _ctx_block = _rd.extract_context(
                                        _block_ms.get("all_stats", {}))
                                    _score_block = _sc.evaluate(_block_ms)
                                    _scenario_block = _rd.detect_scenario(
                                        _score_block, _ctx_block, _block_ms)

                                    from src import match_pdf as _pdf
                                    from src import trend_engine as _trend
                                    from src import match_probability as _prob
                                    _narr_dict = _rd.coach_narrative(
                                        _block_ms, _ctx_block, _scenario_block,
                                        _score_block)
                                    # v4.3 — Tendência + mercados + validação
                                    # Passa block_data pra detectar reação do perdedor
                                    _trend_d = _trend.detect_trend(
                                        _ms_dict, _ctx, _scenario,
                                        score_history=_score_history[mid],
                                        block_data=_block_ms)
                                    # Liga do jogo (pra calibração de competição)
                                    _league = ""
                                    try:
                                        _cat_entry = catalog.get_entry(mid) or {}
                                        _league = _cat_entry.get("league_name", "") or ""
                                    except Exception:
                                        pass
                                    _markets_d = _prob.compute_all_markets(
                                        _ms_dict, _scenario, league_name=_league)
                                    # Validação: bloco atual vs bloco anterior
                                    _validation_d = None
                                    if _block_start > 0:
                                        _prev_block = _tl.compute_block_delta(
                                            _timeline,
                                            max(0, _block_start - 15),
                                            _block_start)
                                        _validation_d = _trend.validate_trend_against_blocks(
                                            _trend_d, _block_ms, _prev_block)
                                    _pdf_path = _pdf.build_block_report_pdf(
                                        _block_ms, _score_block, _scenario_block,
                                        _ctx_block, _current_block, _narr_dict,
                                        score_history=_score_history[mid],
                                        derivatives=_deriv,
                                        trend=_trend_d,
                                        markets=_markets_d,
                                        validation=_validation_d)
                                    # Caption curta — sem markdown
                                    _h = _ms_dict.get("home","?"); _a = _ms_dict.get("away","?")
                                    _hg = _ms_dict.get("home_score",0)
                                    _ag = _ms_dict.get("away_score",0)
                                    _bloc_lbl = {15:"Bloco 1", 30:"Bloco 2",
                                                  45:"HT (1º tempo)", 60:"Bloco 4",
                                                  75:"Bloco 5", 90:"Final"}.get(
                                                    _current_block, f"Min {_current_block}")
                                    _caption = f"⚽ {_h} {_hg}-{_ag} {_a} · {_bloc_lbl} · min {ms.minute}"
                                    _ok = tg.send_document(_pdf_path, caption=_caption)
                                    if _ok:
                                        stats["telegram_sent"] += 1
                                        _mode_str = "🔥INTENSIVO" if _intensive else "📊padrão"
                                        print(f"     \033[35m{_mode_str} bloco {_current_block} PDF → TG\033[0m")
                                        # v3.8 — persiste state após envio bem-sucedido
                                        _save_bs(_bs_state)
                                except Exception as _e:
                                    print(f"     \033[33m⚠️  Relatório PDF falhou: {_e}\033[0m")
                                    import traceback as _tb
                                    print(_tb.format_exc()[:600])
                        else:
                            # Bloco fechado mas modo padrão não manda nesse bloco
                            _block_sent[mid] = _current_block
                            _save_bs(_bs_state)
                # Telegram só se cruzou tier FORTE/PREMIUM
                if _score_result["passed_filters"] and _score_result["tier"]:
                    _telegram_text = _rd.build_telegram_text(
                        _ms_dict, _score_result, _scenario, _ctx, _deriv)
                    _tier = _score_result["tier"]
                    if _tier in ("FORTE", "PREMIUM"):
                        if tg and tg.is_ready():
                            try:
                                _ok = tg.send_text(_telegram_text)
                                if _ok:
                                    stats["telegram_sent"] += 1
                                    print(f"     \033[32m🚀 v3.2 {_tier} score={_score_result['score']:.1f} → TG\033[0m")
                            except Exception as _e:
                                print(f"     \033[33m⚠️  TG falhou: {_e}\033[0m")
                    else:
                        print(f"     \033[36m📡 v3.2 WATCH score={_score_result['score']:.1f} → radar\033[0m")
            except Exception as _e:
                print(f"     \033[33m⚠️  v3.2 falhou: {type(_e).__name__}: {_e}\033[0m")

        # ─── Display em tempo real (Regra 3.1.2.0) ───────────────
        half = _half_label(ms.minute)
        total_cc = (ms.home_bc or 0) + (ms.away_bc or 0)
        cc_rate = (ms.minute / total_cc) if total_cc > 0 else 999.0
        expected_by_cc = total_cc // 3
        total_goals = (ms.home_score or 0) + (ms.away_score or 0)
        placar_abaixo = total_goals < expected_by_cc and expected_by_cc > 0

        print(f"  ⚽ {ms.home} {ms.home_score}-{ms.away_score} {ms.away} | {half} min {ms.minute}")
        print(f"     CC: {ms.home_bc}x{ms.away_bc} | Total={total_cc} | Rate={cc_rate:.1f}")
        print(f"     Gols reais: {total_goals} | Esperado por CC: {expected_by_cc}")
        print(f"     Placar abaixo da produção: {'SIM' if placar_abaixo else 'NÃO'}")
        sys.stdout.flush()

        # ─── Avalia Regra 3.1.2.0 ─────────────────────────────────
        state_entry = state.get(mid, {})
        previous_alert_state = codigo_3_1.get_previous_alert_state(state_entry)
        decision = codigo_3_1.evaluate_codigo_3_1(ms, previous_alert_state)

        telegram_sent = False
        if decision.get("should_alert"):
            stats["alerts"] += 1
            status = codigo_3_1.format_terminal_status(decision)
            print(f"     Status 3.1.2: {status}")
            # v2.8 — Política Telegram unificada COM dedup pelo banco limpo:
            #   - WATCH/FORTE/PREMIUM/BILATERAL podem enviar TG
            #   - Dedup por (match_id, alert_type, bucket): só envia na
            #     PRIMEIRA ocorrência. Repetições no mesmo bucket entram
            #     em terminal/log mas não em TG.
            #   - Quando o tipo evolui (WATCH→FORTE) ou o bucket muda, a
            #     chave é nova → envia TG normalmente.
            # WATCH continua sem consumir bucket operacional da regra.
            already_recorded = False
            signals_path = Path("logs/rule_3_1_2_signals.jsonl")
            try:
                from src import signals_persistence as _sp
                already_recorded = _sp.has_signal(
                    mid, decision.get("alert_type") or "",
                    int(decision.get("bucket", 0) or 0), signals_path,
                )
            except Exception:
                already_recorded = False   # fail-open: se banco falhar, envia

            is_watch = codigo_3_1.is_watch_only(decision.get("alert_type"))
            tg_tag = "RADAR" if is_watch else f"bucket={decision['bucket']}"

            if already_recorded:
                print(f"     \033[90m📡 dedup ({tg_tag}) — já notificado neste bucket, apenas terminal/log\033[0m")
            elif tg and tg.is_ready():
                telegram_sent = codigo_3_1.send_alert(tg, decision)
                if telegram_sent:
                    stats["telegram_sent"] += 1
                    print(f"     \033[32m✅ Telegram enviado ({tg_tag})\033[0m")
                else:
                    print(f"     \033[33m⚠️  Telegram falhou\033[0m")
            else:
                print(f"     \033[90m⏭  Telegram não pronto — alerta apenas no log\033[0m")
            decision["_sent"] = telegram_sent
            if mid not in state:
                state[mid] = {}
            codigo_3_1.update_state_after_alert(state[mid], decision)
            catalog.mark_signal(mid,
                                 f"CODIGO_3_1_{(decision['alert_type'] or 'NONE').upper()}",
                                 ms.minute)
            # v2.7+v2.8 — Banco estruturado dedup: persiste 1 linha por
            # (match, type, bucket). NÃO grava se já existe (mantém dedup
            # consistente entre TG e log).
            if not already_recorded:
                try:
                    from src import signals_persistence as _sp
                    cat_entry = catalog.get(mid) or {}
                    signal_rec = _sp.build_signal_record(
                        match_id=mid, url=cat_entry.get("url", ""),
                        home=ms.home, away=ms.away,
                        alert_type=decision.get("alert_type") or "",
                        bucket=int(decision.get("bucket", 0) or 0),
                        minute_at_alert=ms.minute,
                        status_raw=getattr(ms, "status_raw", "") or "",
                        home_score=ms.home_score, away_score=ms.away_score,
                        home_bc=ms.home_bc, away_bc=ms.away_bc,
                        total_cc=(ms.home_bc or 0) + (ms.away_bc or 0),
                        cc_rate=(ms.minute / max(1, (ms.home_bc or 0) + (ms.away_bc or 0))) if ((ms.home_bc or 0) + (ms.away_bc or 0)) > 0 else 999.0,
                        expected_goals_by_cc=((ms.home_bc or 0) + (ms.away_bc or 0)) // 3,
                        home_xgot=getattr(ms, "home_xgot", 0.0) or 0.0,
                        away_xgot=getattr(ms, "away_xgot", 0.0) or 0.0,
                        league_name=cat_entry.get("premium_league_name", ""),
                        country=cat_entry.get("premium_country", ""),
                        premium_level=cat_entry.get("premium_level", "NONE"),
                        premium_reason=cat_entry.get("premium_reason", ""),
                        telegram_sent=telegram_sent,
                    )
                    _sp.record_signal(signal_rec, signals_path)
                except Exception as _e:
                    print(f"     \033[90m⚠️  signals_persistence: {_e}\033[0m")
        else:
            reason = decision.get("reason", "")
            print(f"     \033[90mStatus 3.1.2: sem alerta ({reason})\033[0m")

        # ─── State: persistir CC atualizado pra próximo ciclo ─────
        if mid not in state:
            state[mid] = {}
        state[mid]["home"] = ms.home
        state[mid]["away"] = ms.away
        state[mid]["last_minute"] = ms.minute
        state[mid]["last_score"] = f"{ms.home_score}-{ms.away_score}"
        state[mid]["last_cc"] = f"{ms.home_bc}x{ms.away_bc}"
        state[mid]["last_update"] = datetime.now(timezone.utc).isoformat()
        state[mid]["home_bc"] = ms.home_bc
        state[mid]["away_bc"] = ms.away_bc
        state[mid]["home_xgot"] = ms.home_xgot
        state[mid]["away_xgot"] = ms.away_xgot

        # Catalog: marca como scanned
        bc_sum = (ms.home_bc or 0) + (ms.away_bc or 0)
        catalog.mark_scanned(mid, minute=ms.minute,
                             score=f"{ms.home_score}-{ms.away_score}",
                             bc_sum=bc_sum)

        # v2.7 — Atualiza observações posteriores em sinais já gravados
        try:
            from src import signals_persistence as _sp
            _sp.update_signal_observations(
                mid, current_minute=ms.minute,
                current_home_score=ms.home_score,
                current_away_score=ms.away_score,
                persist_path=Path("logs/rule_3_1_2_signals.jsonl"),
            )
        except Exception:
            pass  # auxiliar — silencioso

        # Log JSONL completo
        _save_codigo_3_1_log(ms, decision)
        sys.stdout.flush()

    save_state(state)
    cycle_time = time.time() - cycle_start
    stats["cycle_time_seconds"] = cycle_time
    elapsed = f"{cycle_time:.1f}s"
    # Resumo dossiê v1.1 + ajuste de cadência pós-v1.1:
    #   Descobertos | Ao vivo reais | Finalizados/fora | Sem stats | Alertas | Telegram
    total_in_cycle = (stats["scanned"] + stats["no_stats"]
                       + stats["not_live"] + stats["skipped_by_backoff"])
    print(f"\n  \033[36mDescobertos no ciclo: {total_in_cycle}\033[0m | "
          f"\033[32mAo vivo reais: {stats['scanned']}\033[0m | "
          f"\033[90mFinalizados/fora: {stats['not_live']}\033[0m | "
          f"\033[90mSem stats: {stats['no_stats']}\033[0m | "
          f"Alertas: {stats['alerts']} | "
          f"Telegram: {stats['telegram_sent']}")
    # Cadência (ajuste pós-v1.1)
    target_int = int(catalog.persist_path and 120 or 120)  # fallback fixo
    # nota: o valor real do alvo é injetado pelo caller via save_heartbeat
    target = 120
    delay = max(0, cycle_time - target)
    cadence_color = "\033[32m" if cycle_time <= target else "\033[33m"
    print(f"  {cadence_color}⏱  Alvo: {target}s | Real: {cycle_time:.1f}s "
          f"| Atraso: {delay:.1f}s\033[0m")
    if stats["skipped_by_backoff"]:
        print(f"  \033[90m   Backoff sem stats: {stats['skipped_by_backoff']} pulados\033[0m")
    # Finalizados removidos da watchlist (via marcação no catálogo)
    excluded_finished = catalog.count_finished_or_not_live()
    if excluded_finished:
        print(f"  \033[90m   Finalizados removidos da watchlist: {excluded_finished}\033[0m")
    # R5 — Resumo agrupado das exclusões deste ciclo (terminal limpo)
    if _cycle_excludeds:
        total_excl = sum(len(v) for v in _cycle_excludeds.values())
        print(f"  \033[90m   Excluídos no ciclo: {total_excl} jogos\033[0m")
        for reason, mids in sorted(_cycle_excludeds.items(),
                                      key=lambda kv: -len(kv[1])):
            sample = ", ".join(m[:14] for m in mids[:3])
            extra = f", +{len(mids)-3}" if len(mids) > 3 else ""
            print(f"  \033[90m     • {reason}: {len(mids)} ({sample}{extra})\033[0m")

    return stats


# ─── Cobertura por ciclo ──────────────────────────────────────────────

def _compute_coverage(catalog, watchlist: list, now=None) -> dict:
    """Conta por que cada jogo do catálogo entrou ou não entrou na watchlist.

    Garantia operacional: TODO jogo do catálogo recebe um motivo classificado.
    A soma dos contadores == total do catálogo.

    Returns:
        dict com chaves:
            total, in_watchlist, premium_in_watchlist,
            excluded_finished, excluded_no_stats, excluded_stale,
            included_tier0, included_tier05, included_tier1, included_tier2,
            included_tier3, excluded_tier3_overflow, excluded_other_overflow
    """
    from datetime import datetime, timezone
    if now is None:
        now = datetime.now(timezone.utc)

    wl_set = set(watchlist)
    cov = {
        "total": 0, "in_watchlist": len(wl_set),
        "premium_in_watchlist": 0,
        "excluded_duplicate": 0,
        "excluded_finished": 0, "excluded_no_stats": 0, "excluded_stale": 0,
        "included_tier0": 0, "included_tier05": 0,
        "included_tier1": 0, "included_tier2": 0, "included_tier3": 0,
        "excluded_tier3_overflow": 0, "excluded_other_overflow": 0,
    }

    for g in catalog.all():
        cov["total"] += 1
        mid = g.get("match_id")
        in_wl = mid in wl_set

        # Exclusões raiz (todos os tiers)
        if g.get("excluded_duplicate"):
            cov["excluded_duplicate"] += 1
            continue
        if catalog.is_finished_or_not_live_active(mid, now):
            cov["excluded_finished"] += 1
            continue
        if catalog.is_no_stats_active(mid, now):
            cov["excluded_no_stats"] += 1
            continue
        if catalog.is_stale_active(mid, now):
            cov["excluded_stale"] += 1
            continue

        is_prem = bool(g.get("is_premium"))
        m = g.get("last_minute")
        bc = int(g.get("last_bc_sum") or 0)
        in_window = (m is not None and 20 <= m <= 83)
        in_premium_window = (m is None or 0 <= m <= 90)

        # Classificação por tier
        if g.get("has_open_position"):
            if in_wl: cov["included_tier0"] += 1
            else: cov["excluded_other_overflow"] += 1
        elif is_prem and in_premium_window:
            if in_wl:
                cov["included_tier05"] += 1
                cov["premium_in_watchlist"] += 1
            else:
                cov["excluded_other_overflow"] += 1
        elif in_window and bc > 0:
            if in_wl: cov["included_tier1"] += 1
            else: cov["excluded_other_overflow"] += 1
        elif in_window and bc == 0 and g.get("ever_loaded_stats"):
            if in_wl: cov["included_tier2"] += 1
            else: cov["excluded_other_overflow"] += 1
        else:
            if in_wl: cov["included_tier3"] += 1
            else: cov["excluded_tier3_overflow"] += 1

    return cov


# ─── Debug: --find-game ───────────────────────────────────────────────

def _run_find_game(aliases: list) -> int:
    """Localiza jogo no catálogo persistido e mostra por que está/não na watchlist.

    Roda offline (não usa Playwright, não escaneia, não envia Telegram).
    Imprime relatório AUDITORIA DE COBERTURA com veredito binário.
    """
    from datetime import datetime, timezone
    from src.catalog import Catalog
    from src.watchlist import build_watchlist

    print()
    print("=" * 78)
    title = " AUDITORIA DE COBERTURA — " + " × ".join(a.upper() for a in aliases)
    print(title)
    print("=" * 78)

    # Carrega catálogo persistido
    cat = Catalog(persist_path=CATALOG_FILE)
    cat.load()
    now = datetime.now(timezone.utc)
    print(f"  Catálogo: {cat.size()} entries  |  Now (UTC): {now.isoformat()[:19]}Z")

    # Busca por aliases (substring case-insensitive em url + match_id)
    lowered = [a.strip().lower() for a in aliases if a.strip()]
    hits = []
    for entry in cat.all():
        url = (entry.get("url") or "").lower()
        mid = (entry.get("match_id") or "").lower()
        blob = mid + " " + url
        # exige TODOS os aliases presentes (interseção: jogo Time1 vs Time2)
        if all(a in blob for a in lowered):
            hits.append(entry)

    # Se nenhum match com TODOS, tenta UM por vez (modo permissivo)
    matched_all = bool(hits)
    if not hits:
        for entry in cat.all():
            url = (entry.get("url") or "").lower()
            mid = (entry.get("match_id") or "").lower()
            blob = mid + " " + url
            if any(a in blob for a in lowered):
                hits.append(entry)

    if not hits:
        print()
        print("  VEREDITO: NÃO DESCOBERTO PELA FONTE")
        print(f"  Nenhum entry no catálogo bate com {aliases}.")
        print("  Possíveis causas:")
        print("    a) Discovery do Flashscore não retornou esse jogo neste ciclo")
        print("    b) Jogo ainda não começou (pré-jogo) ou já terminou")
        print("    c) Foi removido pela faxina (last_seen_at > 30min)")
        print("    d) Nome no Flashscore usa slug diferente (tentar outros aliases)")
        print("=" * 78)
        print()
        return 0

    if not matched_all:
        print(f"\n  ⚠️  Busca permissiva: encontrou {len(hits)} entries com pelo menos UM alias.")
        print(f"      Para jogo específico use TODOS os aliases dos dois times.\n")

    # Constrói watchlist atual e checa quem entrou
    wl = build_watchlist(cat, now=now)
    wl_set = set(wl)

    # Reordena: canônicos primeiro, depois duplicados
    hits.sort(key=lambda e: (1 if e.get("excluded_duplicate") else 0))

    # Agrupa por fingerprint pra mostrar bloco DUPLICATES coerente
    from src.catalog import _match_fingerprint
    by_fp = {}
    for e in hits:
        fp = _match_fingerprint(e.get("url", ""))
        by_fp.setdefault(fp, []).append(e)

    for entry in hits:
        mid = entry.get("match_id")
        in_wl = mid in wl_set
        url = entry.get("url", "")
        print()
        print("-" * 78)
        print(f"  ENTRY: {mid}")
        print(f"  url: {url}")
        print(f"  is_premium:            {entry.get('is_premium')}")
        print(f"  premium_level:         {entry.get('premium_level','NONE')}")
        print(f"  premium_reason:        {entry.get('premium_reason','')}")
        print(f"  premium_league_name:   {entry.get('premium_league_name','')}")
        print(f"  premium_country:       {entry.get('premium_country','')}")
        meta = entry.get("league_meta_raw") or {}
        print(f"  highlighted_league_detected: "
              f"{entry.get('premium_reason') == 'flashscore_highlighted_league'}")
        print(f"  league_header_classes: {meta.get('css_classes', [])}")
        print(f"  league_header_text:    {meta.get('header_text', '')}")
        if meta.get("failure_type"):
            print(f"  walker_failure:        {meta.get('failure_type')}")
        print(f"  first_seen_at:         {entry.get('first_seen_at')}")
        print(f"  last_seen_at:          {entry.get('last_seen_at')}")
        print(f"  last_scanned_at:       {entry.get('last_scanned_at')}")
        if entry.get("last_scanned_at"):
            try:
                ls = datetime.fromisoformat(entry["last_scanned_at"])
                age_s = (now - ls).total_seconds()
                print(f"  age último scan:       {age_s:.0f}s ({age_s/60:.1f} min)")
            except (ValueError, TypeError):
                pass
        print(f"  last_minute:           {entry.get('last_minute')}")
        print(f"  last_score:            {entry.get('last_score')}")
        print(f"  last_bc_sum:           {entry.get('last_bc_sum')}")
        print(f"  ever_loaded_stats:     {entry.get('ever_loaded_stats')}")
        print(f"  no_stats_count:        {entry.get('no_stats_count')}")
        print(f"  no_stats_until:        {entry.get('no_stats_until')}")
        print(f"  finished_or_not_live:  {entry.get('finished_or_not_live')}")
        print(f"  not_live_reason:       {entry.get('not_live_reason')}")
        print(f"  has_open_position:     {entry.get('has_open_position')}")
        print(f"  excluded_duplicate:    {entry.get('excluded_duplicate', False)}")
        print(f"  duplicate_of:          {entry.get('duplicate_of', '')}")
        print()

        # Classifica veredito
        is_prem = bool(entry.get("is_premium"))
        if entry.get("excluded_duplicate"):
            verdict = (f"DUPLICADO de {entry.get('duplicate_of')} — "
                       "não entra na watchlist, não consome slot")
        elif cat.is_finished_or_not_live_active(mid, now):
            verdict = "ENCONTRADO MAS FILTRADO (finished_or_not_live ativo)"
        elif cat.is_no_stats_active(mid, now):
            if is_prem:
                # Premium em backoff: cobertura passiva (visível, mas sem scan
                # neste ciclo até o TTL de no_stats expirar)
                verdict = ("COBERTURA PASSIVA — PREMIUM SEM STATS TEMPORÁRIO "
                           f"(no_stats_until={entry.get('no_stats_until','')})")
            else:
                verdict = "ENCONTRADO MAS SEM STATS (no_stats_backoff ativo)"
        elif cat.is_stale_active(mid, now):
            verdict = "ENCONTRADO MAS FILTRADO (stale ativo)"
        elif in_wl:
            verdict = "ENCONTRADO E MONITORADO (na watchlist atual)"
        else:
            # No catálogo, sem filtro ativo, mas fora da watchlist → Tier 3 overflow
            m = entry.get("last_minute")
            bc = int(entry.get("last_bc_sum") or 0)
            in_window = m is not None and 20 <= m <= 83
            if entry.get("is_premium"):
                # Premium fora da watchlist por cap — cobertura passiva (visível,
                # mas sem scan neste ciclo). Aparece na seção COBERTURA PREMIUM.
                reason = entry.get("premium_reason", "")
                verdict = (f"COBERTURA PASSIVA — PREMIUM OVERFLOW "
                           f"(liga={entry.get('premium_league_name','?')} "
                           f"reason={reason})")
            elif in_window and bc > 0:
                verdict = "ENCONTRADO MAS FILTRADO (Tier 1 overflow)"
            elif in_window and bc == 0 and entry.get("ever_loaded_stats"):
                verdict = "ENCONTRADO MAS FILTRADO (Tier 2 overflow)"
            else:
                # NÃO premium + fora da janela → Tier 3, slots disputados
                verdict = ("ENCONTRADO MAS FILTRADO (Tier 3 overflow — não premium "
                           "+ min<20 OU sem BC; concorre por slots reservados)")
        print(f"  VEREDITO: {verdict}")
        print(f"  Na watchlist atual? {'SIM' if in_wl else 'NÃO'}")

    # ─── Seção DUPLICATES (por fingerprint) ──────────────────────
    has_dups = any(fp and len(entries) > 1 for fp, entries in by_fp.items())
    if has_dups:
        print()
        print("=" * 78)
        print(" DUPLICATES (mesmo jogo, entries múltiplos)")
        print("=" * 78)
        for fp, entries in by_fp.items():
            if not fp or len(entries) <= 1:
                continue
            canon = next((e for e in entries if not e.get("excluded_duplicate")), entries[0])
            dups = [e for e in entries if e.get("excluded_duplicate")]
            canon_id = canon["match_id"]
            print(f"\n  Fingerprint:        {fp}")
            print(f"  canonical_id:       {canon_id}")
            print(f"  duplicate_ids:      {[d['match_id'] for d in dups]}")
            from src.catalog import _is_mid_based
            reason_parts = []
            if _is_mid_based(canon_id): reason_parts.append("mid-based (A)")
            reason_parts.append(f"last_seen_at={canon.get('last_seen_at','')[:19]}")
            if canon.get("ever_loaded_stats"): reason_parts.append("stats_loaded")
            print(f"  motivo do canônico: {' > '.join(reason_parts)}")
            print(f"  na watchlist agora: "
                  f"{'canônico ('+canon_id+')' if canon_id in wl_set else 'NENHUM'}")
            should_be = canon_id  # o que deveria estar
            print(f"  deveria estar:      {should_be}")

    print("=" * 78)
    print()
    return 0


# ─── Debug: --debug-dom-game (Playwright real) ────────────────────────

_JS_DEBUG_DUMP_DOM = """
(aliases) => {
  // Localiza link do jogo que contém TODOS os aliases na href (case-insensitive)
  const links = document.querySelectorAll('a[href*="/jogo/"]');
  let target = null;
  const lowered = aliases.map(a => a.toLowerCase());
  for (const a of links) {
    const hrefLow = a.href.toLowerCase();
    if (lowered.every(kw => hrefLow.indexOf(kw) !== -1)) { target = a; break; }
  }
  if (!target) {
    // Tenta com pelo menos UM alias (modo permissivo)
    const hits = [];
    for (const a of links) {
      const hrefLow = a.href.toLowerCase();
      if (lowered.some(kw => hrefLow.indexOf(kw) !== -1)) hits.push(a.href);
    }
    return {found: false, total_links: links.length,
            permissive_hits: hits.slice(0, 10)};
  }

  // 15 ancestrais
  const ancestors = [];
  let node = target;
  for (let i = 0; i < 15 && node; i++) {
    const cs = window.getComputedStyle ? window.getComputedStyle(node) : null;
    ancestors.push({
      depth: i,
      tag: node.tagName,
      classes: (typeof node.className === 'string' ? node.className : '').slice(0, 200),
      id: node.id || '',
      text_preview: (node.innerText || node.textContent || '').slice(0, 150).replace(/\\s+/g, ' ').trim(),
      bg: cs ? cs.backgroundColor : '',
      color: cs ? cs.color : '',
    });
    node = node.parentElement;
  }

  // Cadeia de irmãos: pra cada nível ancestral, prev/next siblings
  const siblingChain = [];
  let n = target;
  for (let depth = 0; depth < 6 && n && n.parentElement; depth++) {
    const prev = [];
    let s = n.previousElementSibling;
    while (s && prev.length < 4) {
      prev.push({
        tag: s.tagName,
        classes: (typeof s.className === 'string' ? s.className : '').slice(0, 120),
        text: (s.innerText || s.textContent || '').slice(0, 120).replace(/\\s+/g, ' ').trim(),
      });
      s = s.previousElementSibling;
    }
    const next = [];
    let nx = n.nextElementSibling;
    while (nx && next.length < 2) {
      next.push({
        tag: nx.tagName,
        classes: (typeof nx.className === 'string' ? nx.className : '').slice(0, 120),
        text: (nx.innerText || nx.textContent || '').slice(0, 120).replace(/\\s+/g, ' ').trim(),
      });
      nx = nx.nextElementSibling;
    }
    if (prev.length || next.length) {
      siblingChain.push({depth: depth, parent_tag: n.parentElement.tagName,
                         parent_classes: (typeof n.parentElement.className === 'string'
                                          ? n.parentElement.className : '').slice(0, 100),
                         prev: prev, next: next});
    }
    n = n.parentElement;
  }

  // Busca global por candidatos a "header de liga"
  const candidates = [];
  const SELECTORS = [
    'header', '[class*="Header" i]', '[class*="title" i]',
    '[class*="league" i]', '[class*="country" i]', '[class*="tournament" i]',
    '[class*="competition" i]', '[class*="favorite" i]', '[class*="highlight" i]',
    '[class*="top" i]', '[class*="event__header" i]', '[class*="wcl-header" i]',
  ];
  const seenEls = new Set();
  for (const sel of SELECTORS) {
    let els;
    try { els = document.querySelectorAll(sel); } catch (e) { continue; }
    for (const el of els) {
      if (seenEls.has(el)) continue;
      const txt = (el.innerText || el.textContent || '').slice(0, 160).replace(/\\s+/g, ' ').trim();
      // Filtra: precisa parecer header de liga (país: liga, ou nome conhecido)
      if (/^([A-ZÁÊÇÕ]+):/.test(txt) ||
          /brasileir|premier league|la liga|laliga|bundesliga|serie [ab]|ligue 1|libertadores|sul-americana|sudamericana|champions|europa league|conference|mls|copa do brasil|liga pro|eredivisie|primeira liga/i.test(txt)) {
        seenEls.add(el);
        const cs = window.getComputedStyle ? window.getComputedStyle(el) : null;
        candidates.push({
          selector_hit: sel,
          tag: el.tagName,
          classes: (typeof el.className === 'string' ? el.className : '').slice(0, 160),
          text: txt,
          bg: cs ? cs.backgroundColor : '',
        });
        if (candidates.length >= 20) break;
      }
    }
    if (candidates.length >= 20) break;
  }

  return {
    found: true,
    href: target.href,
    total_links: links.length,
    ancestors: ancestors,
    sibling_chain: siblingChain,
    league_candidates: candidates,
  };
}
"""


def _run_debug_dom_game(aliases: list, base_url: str) -> int:
    """Abre Flashscore real via Playwright e dumpa DOM do jogo localizado.

    Diferente do --find-game (offline, lê catálogo), este modo:
    - Inicia Playwright (headless)
    - Navega pro base_url, clica AO VIVO, expande ligas
    - Localiza o <a href="/jogo/"> que contém TODOS os aliases
    - Dumpa 15 ancestrais com classes + innerText + bg-color
    - Dumpa irmãos prev/next em cada nível
    - Lista candidatos globais a "header de liga"
    """
    from src.flashscore_adapter import FlashscoreReader
    from src.discovery import _JS_CLICK_AO_VIVO, _JS_EXPAND_LEAGUES

    print()
    print("=" * 78)
    print(" DEBUG DOM — Flashscore real (Playwright)")
    print("=" * 78)
    print(f"  Aliases: {aliases}")
    print(f"  base_url: {base_url}")

    try:
        with FlashscoreReader(headless=True) as reader:
            page = reader._context.new_page()
            try:
                print(f"\n  → goto {base_url}")
                page.goto(base_url, wait_until="load", timeout=20000)
                try: reader._accept_cookies(page)
                except Exception: pass
                # Clica AO VIVO
                try:
                    page.wait_for_selector('.filters__tab', timeout=15000, state="attached")
                    page.wait_for_timeout(500)
                    clicked = page.evaluate(_JS_CLICK_AO_VIVO)
                    print(f"  → AO VIVO clicado: {clicked}")
                    if clicked:
                        page.wait_for_timeout(2500)
                except Exception as e:
                    print(f"  → erro ao clicar AO VIVO: {e}")
                # Expande
                try:
                    page.evaluate(_JS_EXPAND_LEAGUES)
                    page.wait_for_timeout(1500)
                except Exception:
                    pass

                # Dump
                print(f"  → executando dump DOM...")
                result = page.evaluate(_JS_DEBUG_DUMP_DOM, aliases)

                if not result.get("found"):
                    print(f"\n  ❌ Link NÃO encontrado contendo TODOS os aliases.")
                    print(f"     Total de links /jogo/ na página: {result.get('total_links', 0)}")
                    perm = result.get("permissive_hits", [])
                    if perm:
                        print(f"     Hits permissivos (ao menos 1 alias) — primeiros {len(perm)}:")
                        for h in perm:
                            print(f"       {h[:100]}")
                    return 0

                print(f"\n  ✅ Link encontrado: {result['href']}")
                print(f"     Total de links na página: {result['total_links']}")

                print(f"\n  ─── 15 ANCESTRAIS ───────────────────────────────────────")
                for a in result["ancestors"]:
                    print(f"    [{a['depth']:2}] <{a['tag']}> id='{a['id']}'")
                    cl = a["classes"]
                    if cl: print(f"          classes: {cl[:150]}")
                    txt = a["text_preview"]
                    if txt: print(f"          text:    {txt[:140]}")
                    bg = a.get("bg", "")
                    if bg and bg not in ("rgba(0, 0, 0, 0)", "rgb(255, 255, 255)", "transparent"):
                        print(f"          bg:      {bg}")

                print(f"\n  ─── CADEIA DE IRMÃOS (prev/next por nível) ────────────")
                for s in result["sibling_chain"]:
                    print(f"    nível {s['depth']} — parent <{s['parent_tag']}> classes='{s['parent_classes']}'")
                    for p in s["prev"]:
                        print(f"      ⬆ prev <{p['tag']}> classes='{p['classes']}'")
                        if p.get("text"): print(f"            text: {p['text']}")
                    for nx in s["next"]:
                        print(f"      ⬇ next <{nx['tag']}> classes='{nx['classes']}'")
                        if nx.get("text"): print(f"            text: {nx['text']}")

                print(f"\n  ─── CANDIDATOS GLOBAIS A HEADER DE LIGA ───────────────")
                if not result["league_candidates"]:
                    print(f"    (nenhum elemento bateu padrões 'brasileir|liga|premier|champions|...')")
                for c in result["league_candidates"]:
                    print(f"    via '{c['selector_hit']}' <{c['tag']}>")
                    print(f"      classes: {c['classes']}")
                    print(f"      text:    {c['text']}")
                    if c.get("bg") and c["bg"] not in ("rgba(0, 0, 0, 0)", "rgb(255, 255, 255)", "transparent"):
                        print(f"      bg:      {c['bg']}")
                print()
                print("  → COPIE ESTE OUTPUT INTEIRO e mande pro Claude pra ele")
                print("     ajustar os seletores em src/discovery.py.")
                print("=" * 78)
            finally:
                try: page.close()
                except Exception: pass
    except Exception as e:
        print(f"\n  ❌ Erro: {e}")
        return 1
    return 0


def _run_debug_league_walker(aliases: list, base_url: str) -> int:
    """Roda o MESMO walker do discovery contra Flashscore real.
    Mostra: resultado do walker pro jogo buscado + stats globais + falhas.
    """
    from src.flashscore_adapter import FlashscoreReader
    from src.discovery import (_JS_CLICK_AO_VIVO, _JS_EXPAND_LEAGUES,
                                _JS_EXTRACT_LEAGUE_META)

    print()
    print("=" * 78)
    print(" DEBUG LEAGUE WALKER — Flashscore real (Playwright)")
    print("=" * 78)
    print(f"  Aliases: {aliases}")

    try:
        with FlashscoreReader(headless=True) as reader:
            page = reader._context.new_page()
            try:
                print(f"\n  → goto {base_url}")
                page.goto(base_url, wait_until="load", timeout=20000)
                try: reader._accept_cookies(page)
                except Exception: pass
                try:
                    page.wait_for_selector('.filters__tab', timeout=15000, state="attached")
                    page.wait_for_timeout(500)
                    if page.evaluate(_JS_CLICK_AO_VIVO):
                        page.wait_for_timeout(2500)
                except Exception:
                    pass
                try:
                    page.evaluate(_JS_EXPAND_LEAGUES)
                    page.wait_for_timeout(1500)
                except Exception:
                    pass

                print(f"  → executando walker idêntico ao discovery...")
                walker_out = page.evaluate(_JS_EXTRACT_LEAGUE_META) or {}

                results = walker_out.get("result", {})
                stats = walker_out.get("stats", {})
                fails = walker_out.get("failures", {})
                fail_sample = walker_out.get("failure_sample", {})

                print(f"\n  ─── STATS GLOBAIS DO WALKER ───────────────────────────")
                for k, v in stats.items():
                    print(f"    {k:42}: {v}")

                if fails:
                    print(f"\n  ─── FALHAS POR TIPO ──────────────────────────────────")
                    for ftype, count in sorted(fails.items(), key=lambda x: -x[1]):
                        sample = fail_sample.get(ftype, "")
                        print(f"    {ftype:42}: {count}")
                        if sample: print(f"      ex: {sample[-90:]}")

                # Procura match pros aliases
                lowered = [a.lower() for a in aliases]
                matched_hrefs = []
                for href in results.keys():
                    h = href.lower()
                    if all(a in h for a in lowered):
                        matched_hrefs.append(href)
                if not matched_hrefs:
                    print(f"\n  ❌ NENHUM link do walker bate TODOS os aliases.")
                    print(f"     Total de links processados pelo walker: {len(results)}")
                    print(f"     Tentando match permissivo (qualquer alias):")
                    for href in results.keys():
                        h = href.lower()
                        if any(a in h for a in lowered):
                            print(f"       {href[-100:]}")
                            matched_hrefs.append(href)
                            if len(matched_hrefs) >= 5: break

                for href in matched_hrefs[:3]:
                    meta = results.get(href, {})
                    print(f"\n  ─── MATCH: {href[-90:]} ─────────────────────")
                    print(f"    header_found:        {meta.get('header_found')}")
                    print(f"    league_name:         {meta.get('league_name','')}")
                    print(f"    country:             {meta.get('country','')}")
                    print(f"    star_detected:       {meta.get('star_detected')}")
                    print(f"    yellow_bg_detected:  {meta.get('yellow_bg_detected')}")
                    print(f"    header_text:         {meta.get('header_text','')[:120]}")
                    css = meta.get("css_classes", [])
                    star_classes = [c for c in css
                                    if any(s in c.lower()
                                           for s in ['star', 'pinned', 'highlight'])]
                    print(f"    css_classes (TOTAL): {len(css)}")
                    if star_classes:
                        print(f"    star_classes:        {star_classes}")
                    print(f"    css_classes (amostra): {css[:8]}")

                print()
                print("=" * 78)
            finally:
                try: page.close()
                except Exception: pass
    except Exception as e:
        print(f"\n  ❌ Erro: {e}")
        return 1
    return 0


# ─── Main ──────────────────────────────────────────────────────────────

def main():
    # Self-watchdog: thread em background que mata o processo se heartbeat
    # ficar > 8min sem atualizar (proteção contra travamento do Playwright).
    # O start_daemon.sh reinicia o daemon limpo em ~10s via loop while.
    _start_self_watchdog()

    parser = argparse.ArgumentParser(
        description="Trading Terminal V1.2 — Live Daemon (Etapa 4B)"
    )
    parser.add_argument("--urls", default=None,
                        help="URLs do Flashscore separadas por vírgula")
    parser.add_argument("--urls-file", default=None,
                        help="Arquivo com URLs (uma por linha)")
    parser.add_argument("--interval", "-i", type=int, default=120,
                        help="Intervalo entre ciclos em segundos (default: 120)")
    parser.add_argument("--send-telegram", action="store_true",
                        help="Enviar notificações no Telegram [SIMULAÇÃO]")
    parser.add_argument("--config", "-c", default=None,
                        help="Caminho do config.yaml")
    parser.add_argument("--headless", action="store_true", default=True,
                        help="Rodar browser sem janela (default)")
    parser.add_argument("--headed", action="store_true",
                        help="Rodar browser com janela visível")
    parser.add_argument("--once", action="store_true",
                        help="Rodar apenas um ciclo e sair")
    parser.add_argument("--base-url", default="https://www.flashscore.com.br/",
                        help="URL base para descobrir jogos ao vivo")
    parser.add_argument("--max-games", type=int, default=20,
                        help="Máximo de jogos por ciclo no auto-discover (default: 20)")

    # ─── Modo WATCHLIST (opt-in, fallback OFF por default) ─────────
    parser.add_argument("--use-watchlist", action="store_true", default=False,
                        help="Ativa arquitetura nova: discovery + scan separados, "
                             "watchlist priorizada. Default: False (modo antigo).")
    parser.add_argument("--discovery-interval", type=int, default=120,
                        help="[watchlist] Segundos entre discoveries (default: 120 — "
                             "dossiê v1.1 Seção 12).")
    parser.add_argument("--scan-interval", type=int, default=120,
                        help="[watchlist] Segundos-alvo entre scans (default: 120 — "
                             "dossiê v1.1 Seção 10). Sleep real = max(15, scan_interval - elapsed).")
    parser.add_argument("--max-watchlist", type=int, default=15,
                        help="[watchlist] Tamanho máximo da watchlist (default: 15). "
                             "Tier 0 (posição/sinal recente) pode estourar.")
    parser.add_argument("--tier3-reserved", type=int, default=3,
                        help="[watchlist] Slots mínimos reservados pro round-robin (default: 3)")
    parser.add_argument("--stale-ttl-min", type=int, default=15,
                        help="[watchlist] TTL em minutos pro stale (default: 15)")
    parser.add_argument("--no-stats-ttl-min", type=int, default=30,
                        help="[watchlist] Teto do backoff de no_stats em min (default: 30, informativo — "
                             "backoff é 5/15/30 min exponencial fixo)")
    parser.add_argument("--read-match-timeout-ms", type=int, default=18000,
                        help="[watchlist] Timeout por read_match em ms (default: 18000). "
                             "Headless precisa mais tempo que headed pra renderizar.")

    # ─── Modo de operação ────────────────────────────────────────
    # codigo_3_1: Código 3:1 — A Matriz das Chances Claras (NOVO PADRÃO).
    #   Agente simples: alerta CC x Gol Devendo. Sem gestão, sem cooldown,
    #   sem ENTER/EXIT. Substitui as regras V1.2 (que ficam dormentes, prontas
    #   para rollback).
    # motor_v12: regras antigas do Motor V1.2 (Back T1/T2/Small, Over Premium/
    #   Bilateral/Small/Gol Limite, Pós-Back, Pós-Over, gestão completa).
    parser.add_argument("--mode",
                        choices=["codigo_3_1", "motor_v12"],
                        default="codigo_3_1",
                        help="Modo de operação. Default: codigo_3_1 (Código 3:1 — agente "
                             "simples). Para rollback ao Motor V1.2, use --mode motor_v12.")

    # ─── Modo debug: --find-game ─────────────────────────────────
    # Localiza jogo no catálogo persistido e mostra por que entrou/não na watchlist.
    # Não inicia daemon, não escaneia, não envia Telegram. Roda offline.
    parser.add_argument("--find-game", nargs="+", metavar="NAME",
                        default=None,
                        help="DEBUG: busca jogo no catálogo por aliases (1+ nomes), mostra "
                             "estado completo e classificação na watchlist. Ex: "
                             "python3 live_daemon.py --find-game corinthians atletico-mg")

    parser.add_argument("--debug-dom-game", nargs="+", metavar="NAME",
                        default=None,
                        help="DEBUG: abre Flashscore real via Playwright, localiza link do "
                             "jogo por aliases, dumpa 15 níveis de ancestrais. "
                             "Ex: --debug-dom-game corinthians atletico-mg")

    parser.add_argument("--debug-league-walker", nargs="+", metavar="NAME",
                        default=None,
                        help="DEBUG: roda o MESMO walker do discovery contra o Flashscore "
                             "real e mostra o resultado pro jogo buscado + estatísticas "
                             "globais. Use pra confirmar se o walker está extraindo "
                             "headerLeague corretamente. Ex: --debug-league-walker "
                             "corinthians atletico-mg")

    args = parser.parse_args()

    # Modos debug (offline ou online — não iniciam daemon)
    if args.find_game:
        return _run_find_game(args.find_game)
    if args.debug_dom_game:
        return _run_debug_dom_game(args.debug_dom_game, args.base_url)
    if args.debug_league_walker:
        return _run_debug_league_walker(args.debug_league_walker, args.base_url)
    cfg = load_config(args.config)
    headless = not args.headed

    # Telegram
    tg = None
    if args.send_telegram:
        tg_cfg = dict(cfg)
        tg_cfg.setdefault("telegram", {})
        tg_cfg["telegram"]["enabled"] = True
        tg = TelegramClient(tg_cfg)

    # URLs fixas ou auto-discover
    fixed_urls = []
    if args.urls:
        fixed_urls = [u.strip() for u in args.urls.split(",") if u.strip()]
    elif args.urls_file:
        fixed_urls = [l.strip() for l in Path(args.urls_file).read_text().splitlines()
                      if l.strip() and not l.startswith("#")]

    auto_discover = len(fixed_urls) == 0

    # State
    state = load_state()

    # Header — branding oficial conforme dossiê v1.1 Seção 0
    print(f"")
    if args.mode == "codigo_3_1":
        print(f"  ╔══════════════════════════════════════════════╗")
        print(f"  ║  O CÓDIGO 3:1 — Terminal de Chances Claras  ║")
        print(f"  ║  Modo: ALERTA POR CHANCES CLARAS            ║")
        print(f"  ╚══════════════════════════════════════════════╝")
        print(f"")
        print(f"  Agente: codigo_3_1")
        print(f"  Scan-alvo: {args.scan_interval}s")
        print(f"  Discovery-alvo: {args.discovery_interval}s")
        if tg:
            tg_status = "PRONTO" if tg.is_ready() else "ERRO"
            print(f"  Telegram: {tg_status}")
        else:
            print(f"  Telegram: OFF (use --send-telegram)")
        print(f"  Heartbeat: logs/heartbeat.json")
        print(f"  Watchdog: python3 watchdog.py (rodar em terminal separado)")
        print(f"  Log: {LOG_FILE}")
        print(f"  State: {STATE_FILE}")
        print(f"  Catalog: {CATALOG_FILE}")
        print(f"  Parar: Ctrl+C")
    else:
        print(f"{'#' * 72}")
        print(f"  LIVE DAEMON — Motor V1.2 (rollback)")
        if args.use_watchlist:
            print(f"  Agente: MOTOR_V12 | discovery {args.discovery_interval}s | "
                  f"scan-alvo {args.scan_interval}s | max {args.max_watchlist} jogos")
            print(f"  Read-match timeout: {args.read_match_timeout_ms}ms | "
                  f"Stale TTL: {args.stale_ttl_min}min")
        else:
            print(f"  Intervalo: {args.interval}s")
            print(f"  Modo: {'auto-discover' if auto_discover else f'{len(fixed_urls)} URLs fixas'} (LEGACY)")
        print(f"  Browser: {'headless' if headless else 'headed'}")
        if tg:
            print(f"  Telegram: {tg.get_status()}")
        else:
            print(f"  Telegram: OFF (use --send-telegram)")
        print(f"  Log: {LOG_FILE}")
        print(f"  State: {STATE_FILE}")
        if args.use_watchlist:
            print(f"  Catalog: {CATALOG_FILE}")
        print(f"  Parar: Ctrl+C")
        print(f"{'#' * 72}")

    # ─── Branch: modo WATCHLIST vs LEGACY ──────────────────────────
    # Modo WATCHLIST é totalmente isolado em run_watchlist_loop().
    # Modo LEGACY (else) preserva byte-a-byte o código original.
    if args.use_watchlist:
        with FlashscoreReader(headless=headless) as reader:
            run_watchlist_loop(reader, args, cfg, tg, state)
        print(f"\n{'#' * 72}")
        print(f"  DAEMON FINALIZADO (watchlist)")
        print(f"  Log: {LOG_FILE}")
        print(f"  Catalog: {CATALOG_FILE}")
        print(f"  State: {STATE_FILE}")
        print(f"{'#' * 72}\n")
        return

    cycle_count = 0

    with FlashscoreReader(headless=headless) as reader:
        while not _PARAR:
            cycle_count += 1

            # Descobrir ou usar URLs fixas
            if auto_discover:
                print(f"\n{'─' * 72}")
                print(f"  \033[1mSCAN #{cycle_count}\033[0m — {_ts()} — Buscando jogos ao vivo...")
                try:
                    disc_page = reader._context.new_page()
                    disc_page.goto(args.base_url, wait_until="domcontentloaded", timeout=15000)
                    reader._accept_cookies(disc_page)

                    # Clicar "AO VIVO" via JS (elemento é <div>, não <a>/<button>)
                    ao_vivo_clicked = disc_page.evaluate("""
                    () => {
                      const tab = document.querySelector(
                        '.filters__tab[data-analytics-alias="live"]'
                      );
                      if (tab) { tab.click(); return true; }
                      // Fallback: buscar por texto
                      const tabs = document.querySelectorAll('.filters__tab');
                      for (const t of tabs) {
                        if (t.textContent.toLowerCase().includes('ao vivo') ||
                            t.textContent.toLowerCase().includes('live')) {
                          t.click(); return true;
                        }
                      }
                      return false;
                    }
                    """)

                    if ao_vivo_clicked:
                        disc_page.wait_for_timeout(2500)
                    else:
                        print(f"  \033[33m⚠️  Botão 'AO VIVO' não encontrado\033[0m")

                    # Expandir ligas colapsadas ("exibir jogos (N)")
                    disc_page.evaluate("""
                    () => {
                      document.querySelectorAll('[class*="event__expander"], [class*="wcl-scores"]').forEach(el => {
                        const p = el.closest('[class*="leagues--live"], [class*="sportName"]');
                        if (p) p.click();
                      });
                      // Click "exibir jogos" spans
                      document.querySelectorAll('span').forEach(s => {
                        if (/exibir jogos?/i.test(s.textContent)) {
                          const clickable = s.closest('[role="button"], a, [class*="event__expander"]') || s.parentElement;
                          if (clickable) clickable.click();
                        }
                      });
                    }
                    """)
                    disc_page.wait_for_timeout(1500)

                    # Coletar TODOS os links de jogos
                    all_links = disc_page.eval_on_selector_all(
                        'a[href*="/jogo/"]',
                        "els => Array.from(new Set(els.map(e => e.href)))"
                    )
                    disc_page.close()
                    total_found = len(all_links)

                    # Limpar hash antigo mas MANTER query params, e
                    # adicionar hash de stats (como PAINEL_V8 faz).
                    # CORREÇÃO: sem barra entre query e hash (quebrava ?mid=xxx).
                    urls = [link.split("#")[0].rstrip("/") + "#/match-summary/match-statistics/0"
                            for link in all_links]
                    urls = list(dict.fromkeys(urls))
                    if len(urls) > args.max_games:
                        urls = urls[:args.max_games]
                    print(f"  🔍 {total_found} jogos ao vivo → escaneando {len(urls)}")

                except Exception as e:
                    print(f"  [{_ts()}] ⚠️  Erro ao descobrir jogos: {e}")
                    urls = []
            else:
                urls = fixed_urls
                print(f"\n{'─' * 72}")
                print(f"  \033[1mSCAN #{cycle_count}\033[0m — {_ts()} — {len(urls)} jogos fixos")

            if urls and not _PARAR:
                print(SEPARATOR)
                result = run_cycle(reader, urls, cfg, tg, state)

            if args.once:
                break

            if not _PARAR:
                remaining = args.interval
                print(f"\n  ⏳ Dormindo {remaining}s... (Ctrl+C para parar)")
                # v2.9 — toca tick antes/durante sleep no modo legacy também
                _touch_live_tick(source="sleep_start")
                for _i in range(args.interval):
                    if _PARAR:
                        break
                    time.sleep(1)
                    if (_i + 1) % 15 == 0:
                        _touch_live_tick(source="sleep")

    print(f"\n{'#' * 72}")
    print(f"  DAEMON FINALIZADO — {cycle_count} ciclos completados")
    print(f"  Log: {LOG_FILE}")
    print(f"  State: {STATE_FILE}")
    print(f"{'#' * 72}\n")


if __name__ == "__main__":
    main()
