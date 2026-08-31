"""
operational_config — flags operacionais do sistema (v2.5).

Centraliza decisões de "o que pode/não pode" que valem pra TODAS as
camadas técnicas (supervisor, watchdog, coverage guard).

Política atual do Tiago:
  Telegram é EXCLUSIVAMENTE para sinais de aposta da Regra 3.1.2.0:
    - WATCH 3.1.2 — RADAR DE GOL / BACK DOMINANTE
    - FORTE 3.1.2 — GOL DEVENDO / BACK DOMINANTE
    - PREMIUM 3.1.2 — GOL MUITO DEVENDO / CC + xG CONFIRMADOS /
                       OVER BILATERAL PESADO / BACK DOMINANTE EXTREMO

  Mensagens TÉCNICAS (supervisor restart, daemon travado, heartbeat stale,
  coverage guard recovered, premium A sem scan, etc.) NÃO devem ir para
  Telegram. Ficam apenas em:
    - terminal (display do daemon/supervisor)
    - logs/codigo31_supervisor.log
    - logs/live_coverage_guard.jsonl
    - logs/heartbeat.json (campos coverage_*)

Como ativar Telegram técnico temporariamente (debug):
  export TECHNICAL_TELEGRAM_ENABLED=1
"""
import os


# ─── Flag global ──────────────────────────────────────────────────────
# Default: DESLIGADO. Sobrescreve via env var TECHNICAL_TELEGRAM_ENABLED=1.
_DEFAULT_TECHNICAL_TG_ENABLED = False


def is_technical_telegram_enabled() -> bool:
    """True se o Telegram técnico está autorizado (supervisor/coverage/watchdog).

    Lido em runtime do env var TECHNICAL_TELEGRAM_ENABLED (1/0/true/false/yes/no).
    Default: False — Telegram exclusivo para sinais da Regra 3.1.2.0.
    """
    raw = os.environ.get("TECHNICAL_TELEGRAM_ENABLED", "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return _DEFAULT_TECHNICAL_TG_ENABLED


# ─── Gates específicos (granularidade futura) ─────────────────────────
# Mantidos como aliases hoje pra que o leitor saiba exatamente qual
# subsistema está consultando. Caso o usuário queira habilitar só um
# subsistema no futuro, basta trocar a implementação aqui.

def coverage_guard_telegram_enabled() -> bool:
    """Coverage Guard envia Telegram técnico? Default: False."""
    return is_technical_telegram_enabled()


def supervisor_telegram_enabled() -> bool:
    """Supervisor (restart/stale heartbeat) envia Telegram técnico? Default: False."""
    return is_technical_telegram_enabled()


def watchdog_telegram_enabled() -> bool:
    """Watchdog técnico envia Telegram? Default: False."""
    return is_technical_telegram_enabled()
