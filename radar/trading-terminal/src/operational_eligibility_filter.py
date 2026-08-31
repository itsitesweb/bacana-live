"""
OPERATIONAL_ELIGIBILITY_FILTER — camada de elegibilidade ANTES da Turbo.

Filtra jogos inelegíveis pra evitar:
  - consumir slot dos 20 jogos principais com lixo
  - poluir turbo_near_misses com bloqueios que nem deveriam chegar lá
  - chamar validate_triple_debt_filter/Turbo desnecessariamente

NÃO é regra esportiva. NÃO altera TRINCA, DT, Telegram.
Vem ANTES do evaluate_turbo() no fluxo do daemon.

Reasons (do spec do usuário):
  - finished_minute_90
  - missing_all_core_stats
  - repeated_missing_xgot
  - reserve_or_youth_competition
  - stale_pre_fake
  - no_trade_non_actionable

Banco append-only: logs/operational_excluded.jsonl
"""
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

__version__ = "1.0.0"

# === Reasons =============================================================
REASON_FINISHED_MIN_90        = "finished_minute_90"
REASON_MISSING_CORE_STATS     = "missing_all_core_stats"
REASON_REPEATED_MISSING_XGOT  = "repeated_missing_xgot"
REASON_RESERVE_YOUTH          = "reserve_or_youth_competition"
REASON_STALE_PRE_FAKE         = "stale_pre_fake"
REASON_NO_TRADE_NONACTIONABLE = "no_trade_non_actionable"


# === Detecção reserve/youth ==============================================
# Padrões testados contra home, away, league_name
_RESERVE_PATTERNS = [
    r"\bU1[5-9]\b", r"\bU2[0-3]\b",                # U15..U19, U20..U23
    r"\bSUB[-\s]?1[5-9]\b", r"\bSUB[-\s]?2[0-3]\b",  # SUB-15..SUB-23
    r"\bRESERVE[S]?\b", r"\bRESERVA[S]?\b",
    r"\bYOUTH\b", r"\bJUNIOR[S]?\b", r"\bJUVENI[LS]\b",
    r"\bAMATEUR\b", r"\bACADEMY\b", r"\bACADEMIA\b",
    r"\bWOMEN\b", r"\bFEMININ[OA]\b",
    # Times "B" / "II" / "2" como sufixo
    r"\s+II\s*$",   r"\s+B\s*$",   r"\s+2\s*$",
]
_RESERVE_RE = [re.compile(p, re.IGNORECASE) for p in _RESERVE_PATTERNS]

# Whitelist — competições/times que CASAM reserva mas são main
# (deixar vazia por enquanto; user adiciona se precisar)
_WHITELIST_NAMES = set()


def _looks_like_reserve(name: str) -> bool:
    if not name: return False
    name = name.strip()
    if not name: return False
    if name in _WHITELIST_NAMES: return False
    for r in _RESERVE_RE:
        if r.search(name): return True
    return False


def _all_raw_core_missing(ms_dict) -> bool:
    """True quando home_xg_raw, away_xg_raw, home_xgot_raw, away_xgot_raw,
    home_bc_raw, away_bc_raw são TODOS None (ou ausentes do dict)."""
    keys = ("home_xg_raw", "away_xg_raw",
            "home_xgot_raw", "away_xgot_raw",
            "home_bc_raw", "away_bc_raw")
    # Se nem aparecem no dict, considera missing (fail-safe)
    return all(ms_dict.get(k) is None for k in keys)


# === Núcleo: função pura =================================================
def evaluate_operational_eligibility(ms_dict, decision_dict, *,
                                       missing_xgot_streak: int = 0):
    """Avalia se o jogo deve passar pela Turbo. Retorna dict imutável.

    Args:
      ms_dict: dict com match_id, home, away, league_name, minute,
        status_raw, e os campos _raw da MatchState.
      decision_dict: dict com recommended_action, game_profile,
        message_severity.
      missing_xgot_streak: int — quantas vezes seguidas esse match_id
        foi bloqueado por TURBO_BLOCKED_MISSING_XGOT no histórico recente.

    Returns:
      {
        "evaluated_at_utc": ...,
        "match_id", "home", "away", "league", "minute",
        "eligible": bool,
        "reason": str | None,
        "action": "skip_turbo" | "mark_finished" | "mark_no_stats" |
                  "cooldown_30",
        "detected_in": str (se reason=reserve)
      }
    """
    minute     = int(ms_dict.get("minute", 0) or 0)
    home       = (ms_dict.get("home") or "").strip()
    away       = (ms_dict.get("away") or "").strip()
    league     = (ms_dict.get("league_name") or "").strip()
    status_raw = (ms_dict.get("status_raw") or "").strip().upper()
    action     = (decision_dict.get("recommended_action") or "")
    profile    = (decision_dict.get("game_profile") or "").upper()

    base = {
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "match_id":         ms_dict.get("match_id"),
        "home":             home,
        "away":             away,
        "league":           league,
        "minute":           minute,
        "status_raw":       ms_dict.get("status_raw") or "",
        "eligible":         False,
        "reason":           None,
        "action":           None,
    }

    # 4. Reserve/youth (prioridade alta — independente de stats)
    detected_in = None
    for label, nm in (("home", home), ("away", away), ("league", league)):
        if _looks_like_reserve(nm):
            detected_in = f"{label}:{nm}"
            break
    if detected_in:
        return {**base, "reason": REASON_RESERVE_YOUTH,
                "action": "cooldown_30",
                "detected_in": detected_in}

    # 1. minute >= 90 + sem stats vivos → finalizado
    all_missing = _all_raw_core_missing(ms_dict)
    if minute >= 90 and all_missing:
        return {**base, "reason": REASON_FINISHED_MIN_90,
                "action": "mark_finished"}

    # 5. minute == 0 + status pre/scheduled (apareceu em live mas tá em pre)
    PRE_MARKERS = ("PRE", "AGUARDA", "AGUARDANDO", "AGENDA", "AGENDADO",
                   "SCHEDULED", "NOT STARTED", "À INICIAR", "A INICIAR",
                   "PROGRAMADO", "BEFORE MATCH", "WAITING")
    if minute == 0 and any(p in status_raw for p in PRE_MARKERS):
        return {**base, "reason": REASON_STALE_PRE_FAKE,
                "action": "skip_turbo"}

    # 2. Todos _raw core None → cooldown via mark_no_stats
    if all_missing:
        return {**base, "reason": REASON_MISSING_CORE_STATS,
                "action": "mark_no_stats"}

    # 3. Repeated missing_xgot ≥ 2 ciclos → cooldown 30 min
    if missing_xgot_streak >= 2:
        return {**base, "reason": REASON_REPEATED_MISSING_XGOT,
                "action": "cooldown_30",
                "missing_xgot_streak": missing_xgot_streak}

    # 6. NO_TRADE sem ação útil
    if profile == "NO_TRADE" and action in ("NO_ACTION", "", None):
        return {**base, "reason": REASON_NO_TRADE_NONACTIONABLE,
                "action": "skip_turbo"}

    # Passou — pode chamar Turbo
    return {**base, "eligible": True}


# === Estado entre ciclos (streak + cooldown) =============================
# Mantido em memória do processo. Persistência não é necessária pra MVP
# (restart do daemon zera, e o Catalog já tem mark_no_stats persistente
# para os casos críticos).

_missing_xgot_streak: dict = {}    # match_id -> count
_op_cooldown: dict          = {}   # match_id -> datetime UTC


def get_missing_xgot_streak(match_id: str) -> int:
    return int(_missing_xgot_streak.get(match_id, 0))


def record_turbo_result(match_id: str, turbo_reason: str) -> None:
    """Chamado pelo daemon APÓS a Turbo decidir. Atualiza streak para
    detectar match_ids que falham missing_xgot por 2 ciclos."""
    if not match_id: return
    if turbo_reason == "TURBO_BLOCKED_MISSING_XGOT":
        _missing_xgot_streak[match_id] = (
            _missing_xgot_streak.get(match_id, 0) + 1
        )
    else:
        # Qualquer outro resultado (aprovado, outra falha) reseta
        _missing_xgot_streak.pop(match_id, None)


def add_cooldown(match_id: str, minutes: int = 30) -> None:
    if not match_id: return
    until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    _op_cooldown[match_id] = until


def is_in_cooldown(match_id: str, *, now=None) -> bool:
    if not match_id: return False
    until = _op_cooldown.get(match_id)
    if not until: return False
    now = now or datetime.now(timezone.utc)
    if now >= until:
        # Expirado — limpa
        _op_cooldown.pop(match_id, None)
        return False
    return True


def _reset_state():
    """Hook pra testes — zera streak/cooldown entre cenários."""
    _missing_xgot_streak.clear()
    _op_cooldown.clear()


# === R2 — Pre-read filter (antes de abrir Flashscore) ====================
def pre_read_eligibility(catalog_entry: dict) -> dict:
    """Avalia se vale a pena CHAMAR read_match pra esse entry.

    Aplica regex reserve/youth nos nomes dos times e da liga DISPONÍVEIS
    no entry do catalog (sem precisar abrir a URL pesada).

    Returns:
      {eligible: bool, reason: str | None, source: str}
    """
    if not catalog_entry:
        return {"eligible": True, "reason": None, "source": "no_entry"}

    # Fontes possíveis de nome (em ordem de confiabilidade)
    league = (catalog_entry.get("premium_league_name")
                or catalog_entry.get("league_name") or "").strip()
    country = (catalog_entry.get("premium_country")
                 or catalog_entry.get("country") or "").strip()
    # Times: do entry direto (preenchido por leituras anteriores) ou
    # parsed da URL (slug)
    home = (catalog_entry.get("home_team") or
              catalog_entry.get("home") or "").strip()
    away = (catalog_entry.get("away_team") or
              catalog_entry.get("away") or "").strip()
    url = catalog_entry.get("url", "")

    # 1) Check explícito por nome (mais confiável)
    for label, nm in (("home", home), ("away", away),
                       ("league", league), ("country", country)):
        if nm and _looks_like_reserve(nm):
            return {"eligible": False,
                    "reason": REASON_RESERVE_YOUTH,
                    "detected_in": f"{label}:{nm}",
                    "source": "entry_name"}

    # 2) Check no slug da URL (último fallback — quando não tem nome ainda)
    if url:
        url_low = url.lower()
        # Padrões: tanto "/u19/" quanto "-u19-" quanto "-u19/" etc
        URL_RE = re.compile(
            r"[/\-]u1[5-9][/\-]|[/\-]u2[0-3][/\-]|"
            r"[/\-]sub-?1[5-9][/\-]|[/\-]sub-?2[0-3][/\-]|"
            r"[/\-]reservas?[/\-]|[/\-]reserves?[/\-]|"
            r"[/\-]youth[/\-]|[/\-]juniores?[/\-]|"
            r"[/\-]feminin[oa][/\-]|[/\-]women[/\-]"
        )
        m = URL_RE.search(url_low)
        if m:
            return {"eligible": False,
                    "reason": REASON_RESERVE_YOUTH,
                    "detected_in": f"url:{m.group(0)}",
                    "source": "url_slug"}

    return {"eligible": True, "reason": None, "source": "passed"}


# === Log =================================================================
LOG_PATH = (Path(__file__).resolve().parent.parent
            / "logs" / "operational_excluded.jsonl")


def log_exclusion(record, *, path=None):
    """Appenda record em logs/operational_excluded.jsonl.
    NÃO toca em logs/turbo_near_misses.jsonl — esses são pra jogos que
    passaram pela elegibilidade operacional."""
    p = Path(path) if path else LOG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return p
