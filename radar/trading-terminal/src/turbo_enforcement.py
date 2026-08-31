"""
TURBO_ENFORCEMENT — wrapper que combina as travas da Regra 3.1.2.0 Turbo:
  1. TRINCA (triple_debt_filter) — nova regra-mãe
  2. DOMINANT_TRAILING_PROTECTION — proteção contra trailing-trap

Decisão final é estritamente AND: o candidato só passa se as duas travas
aprovarem. Falha fechada — qualquer exceção bloqueia o envio.

Telegram NUNCA é importado/chamado aqui. Esse módulo só decide se o
caller (live_daemon) deve emitir ou bloquear.

Banco append-only de near misses: logs/turbo_near_misses.jsonl.
Banco append-only de approved: logs/turbo_approved_signals.jsonl.
Banco limpo legacy (rule_3_1_2_signals.jsonl) NÃO é tocado.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from src.triple_debt_filter import validate_triple_debt_filter
from src.dominant_trailing_protection import validate as validate_dominant_trailing
# v3.1 — routes substituem a Trinca rígida
from src import turbo_routes as _routes


__version__ = "2.0.0"   # v2: routes + tier (WATCH/FORTE/PREMIUM)


# === Decisões finais =====================================================
FINAL_SENT                       = "sent"
FINAL_BLOCKED_TRIPLE             = "blocked_triple"
FINAL_BLOCKED_MISSING_DATA       = "blocked_missing_data"
FINAL_BLOCKED_DOMINANT_TRAILING  = "blocked_dominant_trailing"
FINAL_BLOCKED_ERROR              = "blocked_error"
# v3.1 — novos finals pra routes
FINAL_RADAR_WATCH                = "radar_watch"   # WATCH → não Telegram
FINAL_BLOCKED_NO_TIER            = "blocked_no_tier"  # nenhum tier atingido


# === Paths dos logs ======================================================
_ROOT = Path(__file__).resolve().parent.parent
NEAR_MISS_LOG_PATH       = _ROOT / "logs" / "turbo_near_misses.jsonl"
APPROVED_SIGNALS_LOG_PATH = _ROOT / "logs" / "turbo_approved_signals.jsonl"


# === Adapters ============================================================
def _build_triple_state(ms_dict):
    """MatchState-dict → schema esperado pelo triple_debt_filter.
    PROPAGA os campos _raw (None = ausente) pra TRINCA detectar
    bloqueio por dado ausente em vez de mascarar como falha esportiva.
    v3.1: agora também propaga shots/sot pra Rota B."""
    # Aceita ambas as variantes (daemon usa home_bc, testes podem usar home_cc)
    home_cc = ms_dict.get("home_cc",   ms_dict.get("home_bc", 0))
    away_cc = ms_dict.get("away_cc",   ms_dict.get("away_bc", 0))
    return {
        "match_id":   ms_dict.get("match_id", ""),
        "home":       ms_dict.get("home", ""),
        "away":       ms_dict.get("away", ""),
        "minute":     ms_dict.get("minute", 0),
        "home_cc":    home_cc,
        "away_cc":    away_cc,
        "home_xg":    ms_dict.get("home_xg", 0.0),
        "away_xg":    ms_dict.get("away_xg", 0.0),
        "home_xgot":  ms_dict.get("home_xgot", 0.0),
        "away_xgot":  ms_dict.get("away_xgot", 0.0),
        "home_shots": ms_dict.get("home_shots", 0),
        "away_shots": ms_dict.get("away_shots", 0),
        "home_sot":   ms_dict.get("home_sot", 0),
        "away_sot":   ms_dict.get("away_sot", 0),
        "home_goals": ms_dict.get("home_goals",
                                     ms_dict.get("home_score", 0)),
        "away_goals": ms_dict.get("away_goals",
                                     ms_dict.get("away_score", 0)),
        # _raw — backward compat
        **{k: ms_dict[k] for k in (
            "home_xgot_raw", "away_xgot_raw",
            "home_xg_raw",   "away_xg_raw",
            "home_bc_raw",   "away_bc_raw",
            "home_sot_raw",  "away_sot_raw",
        ) if k in ms_dict},
    }


def _build_dominant_payload(ms_dict, decision_dict):
    """MatchState+Decision → schema esperado por dominant_trailing.validate."""
    return {
        "match_id":            ms_dict.get("match_id"),
        "home":                ms_dict.get("home"),
        "away":                ms_dict.get("away"),
        "minute_at_alert":     ms_dict.get("minute", 0),
        "home_score_at_alert": ms_dict.get("home_score", 0),
        "away_score_at_alert": ms_dict.get("away_score", 0),
        "home_bc_at_alert":    ms_dict.get("home_bc", 0),
        "away_bc_at_alert":    ms_dict.get("away_bc", 0),
        "home_xg_at_alert":    ms_dict.get("home_xg", 0.0),
        "away_xg_at_alert":    ms_dict.get("away_xg", 0.0),
        "home_sot_at_alert":   ms_dict.get("home_sot", 0),
        "away_sot_at_alert":   ms_dict.get("away_sot", 0),
        "level":               decision_dict.get("message_severity", ""),
        "alert_type":          decision_dict.get("recommended_action", ""),
    }


# === Near miss helpers ===================================================
def _compute_distance(triple_result):
    """Quanto falta pra TRINCA formar (por perna)."""
    goals    = triple_result.get("goals_in_scope", 0) or 0
    cc       = triple_result.get("cc_in_scope", 0) or 0
    xg       = float(triple_result.get("xg_in_scope", 0.0) or 0.0)
    xgot     = float(triple_result.get("xgot_in_scope", 0.0) or 0.0)
    next_cc  = (goals + 1) * 3   # CC mínimo pra debt formar
    return {
        "cc":   max(0, next_cc - cc),
        "xg":   round(max(0.0, (goals + 1.00) - xg), 3),
        "xgot": round(max(0.0, (goals + 1.00) - xgot), 3),
    }


def _near_miss_type(triple_result, dt_result):
    failed = triple_result.get("failed_reasons") or []
    br = (triple_result.get("block_reason") or "")
    # Dado ausente — diagnóstico, NÃO falha esportiva
    if br == "triple_debt_missing_xgot":  return "missing_xgot"
    if br == "triple_debt_missing_xg":    return "missing_xg"
    if br == "triple_debt_missing_cc":    return "missing_cc"
    if triple_result.get("triple_debt_formed") and dt_result \
            and not dt_result.get("entry_allowed", True):
        return "passed_triple_blocked_by_dominant_trailing"
    if len(failed) == 1:
        return "failed_one_triple_leg"
    if len(failed) == 2:
        return "failed_two_triple_legs"
    if len(failed) == 3:
        return "no_real_debt"
    if triple_result.get("scope") == "none":
        return "scope_not_classified"
    return "other"


def _near_miss_score(triple_result):
    """0..3 — quantas pernas passaram (mais perto = mais alto)."""
    return sum(1 for k in ("cc_debt", "xg_debt", "xgot_debt")
                if triple_result.get(k))


# === Núcleo ==============================================================
def evaluate_turbo(ms_dict, decision_dict, *, match_history=None):
    """v3.1 — REFORMA com 2 ROTAS + 3 TIERS.

    Fluxo:
      1. classify_routes(match_state) decide tier final (WATCH/FORTE/PREMIUM
         ou None) usando Rota A (CC) OU Rota B (Volume).
      2. Se tier=None ou scope=none → blocked_no_tier.
      3. Se tier=WATCH → radar_watch (NÃO chama DT, NÃO chama Telegram).
      4. Se tier=FORTE ou PREMIUM → roda DT como antes.
      5. DT aprovou → sent. DT bloqueou → blocked_dominant_trailing.
      6. Erro em qualquer camada → falha fechada (blocked_error).

    Returns:
      allowed: bool
      tier: WATCH | FORTE | PREMIUM | None
      route: rota_a | rota_b | None
      final_decision: sent | radar_watch | blocked_no_tier |
                       blocked_dominant_trailing | blocked_error
      routes_result: dict completo do classifier
      dominant_trailing_result: dict | None (só populado em FORTE/PREMIUM)
      error: str | None
    """
    out = {
        "schema_version": __version__,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "allowed": False,
        "tier": None,
        "route": None,
        "final_decision": FINAL_BLOCKED_ERROR,
        "routes_result": None,
        "dominant_trailing_result": None,
        "error": None,
    }
    try:
        # 1. Classificar pelas 2 rotas
        routes = _routes.classify_routes(_build_triple_state(ms_dict))
        out["routes_result"] = routes

        if not routes.get("classified"):
            out["allowed"] = False
            out["final_decision"] = FINAL_BLOCKED_NO_TIER
            return out

        tier = routes.get("tier")
        out["tier"] = tier
        out["route"] = routes.get("route")

        # 2. WATCH → radar interno, NÃO chama DT, NÃO chama Telegram
        if tier == _routes.TIER_WATCH:
            out["allowed"] = False   # NÃO autorizado pra Telegram
            out["final_decision"] = FINAL_RADAR_WATCH
            return out

        # 3. FORTE/PREMIUM → DT roda
        dt = validate_dominant_trailing(
            _build_dominant_payload(ms_dict, decision_dict),
            match_history=match_history)
        out["dominant_trailing_result"] = dt

        if not dt.get("entry_allowed"):
            out["allowed"] = False
            out["final_decision"] = FINAL_BLOCKED_DOMINANT_TRAILING
            return out

        # 4. Aprovado
        out["allowed"] = True
        out["final_decision"] = FINAL_SENT
        return out
    except Exception as e:
        out["allowed"] = False
        out["final_decision"] = FINAL_BLOCKED_ERROR
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        return out


def evaluate_turbo_legacy_trinca(ms_dict, decision_dict, *, match_history=None):
    """LEGACY (v1) — Trinca rígida absoluta. Mantida para backward compat
    de testes antigos. Use evaluate_turbo (v3.1) em produção."""
    return _evaluate_turbo_legacy_v1(ms_dict, decision_dict,
                                       match_history=match_history)


def _evaluate_turbo_legacy_v1(ms_dict, decision_dict, *, match_history=None):
    """Roda TRINCA + DOMINANT_TRAILING_PROTECTION em ORDEM INEGOCIÁVEL.

    Contrato de ordem (PROIBIDO inverter):
      1. TRINCA SEMPRE roda primeiro.
      2. Se a TRINCA não formar → bloqueia imediato + return.
         DT NÃO é avaliado nesse caso.
      3. DT só roda quando triple_debt_formed=True.
      4. DT NÃO decide gol devendo — quem decide é EXCLUSIVAMENTE a TRINCA.
         DT serve apenas como trava secundária contra armadilha de placar
         (dominante perdendo sem reação ofensiva recente).
      5. Se a TRINCA formou e o dominante NÃO está perdendo, DT aprova direto.
      6. Se TRINCA formou + dominante perdendo + houve reação confirmada
         (≥2 dos 6 critérios), DT aprova.
      7. Se TRINCA formou + dominante perdendo + SEM reação, DT bloqueia.
      8. Erro em qualquer trava → falha fechada (blocked_error).

    Returns dict com:
      allowed: bool
      final_decision: "sent"|"blocked_triple"|"blocked_dominant_trailing"|"blocked_error"
      triple_debt_result: dict | None
      dominant_trailing_result: dict | None
      error: str | None
    """
    out = {
        "schema_version": __version__,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "allowed": False,
        "final_decision": FINAL_BLOCKED_ERROR,
        "triple_debt_result": None,
        "dominant_trailing_result": None,
        "error": None,
    }
    try:
        triple = validate_triple_debt_filter(_build_triple_state(ms_dict))
        out["triple_debt_result"] = triple
        if not triple.get("triple_debt_formed"):
            out["allowed"] = False
            br = (triple.get("block_reason") or "")
            # Distinguir dado ausente (qualidade de input) de falha
            # esportiva (regra). Bloqueio MISSING_DATA é diagnóstico.
            if br.startswith("triple_debt_missing_"):
                out["final_decision"] = FINAL_BLOCKED_MISSING_DATA
            else:
                out["final_decision"] = FINAL_BLOCKED_TRIPLE
            return out

        dt = validate_dominant_trailing(
            _build_dominant_payload(ms_dict, decision_dict),
            match_history=match_history)
        out["dominant_trailing_result"] = dt

        if not dt.get("entry_allowed"):
            out["allowed"] = False
            out["final_decision"] = FINAL_BLOCKED_DOMINANT_TRAILING
            return out

        out["allowed"] = True
        out["final_decision"] = FINAL_SENT
        return out
    except Exception as e:
        # Falha fechada: erro de proteção bloqueia.
        out["allowed"] = False
        out["final_decision"] = FINAL_BLOCKED_ERROR
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        return out


# === Records pra logs ====================================================
def build_near_miss_record(ms_dict, decision_dict, eval_result):
    """Record completo pra append em turbo_near_misses.jsonl."""
    triple = eval_result.get("triple_debt_result") or {}
    dt     = eval_result.get("dominant_trailing_result") or {}
    h_cc   = ms_dict.get("home_bc", 0); a_cc   = ms_dict.get("away_bc", 0)
    h_xg   = ms_dict.get("home_xg", 0.0); a_xg   = ms_dict.get("away_xg", 0.0)
    h_xgot = ms_dict.get("home_xgot", 0.0); a_xgot = ms_dict.get("away_xgot", 0.0)
    h_g    = ms_dict.get("home_score", 0); a_g    = ms_dict.get("away_score", 0)
    dt_result_str = None
    if dt:
        if dt.get("entry_allowed"):
            dt_result_str = "approved"
        else:
            dt_result_str = dt.get("alert_tier") or "blocked"
    return {
        "timestamp":        eval_result.get("evaluated_at_utc"),
        "match_id":         ms_dict.get("match_id"),
        "home_team":        ms_dict.get("home"),
        "away_team":        ms_dict.get("away"),
        "minute":           ms_dict.get("minute"),
        "score_at_signal":  f"{h_g}-{a_g}",
        "original_tier":    decision_dict.get("message_severity"),
        "original_alert_type": decision_dict.get("recommended_action"),
        "candidate_market": decision_dict.get("market_target"),
        "home_cc": h_cc, "away_cc": a_cc, "total_cc": h_cc + a_cc,
        "home_xg": h_xg, "away_xg": a_xg,
        "total_xg": round(h_xg + a_xg, 3),
        "home_xgot": h_xgot, "away_xgot": a_xgot,
        "total_xgot": round(h_xgot + a_xgot, 3),
        "home_goals": h_g, "away_goals": a_g,
        "scope":           triple.get("scope"),
        "scope_side":      triple.get("scope_side"),
        "cc_in_scope":     triple.get("cc_in_scope"),
        "xg_in_scope":     triple.get("xg_in_scope"),
        "xgot_in_scope":   triple.get("xgot_in_scope"),
        "goals_in_scope":  triple.get("goals_in_scope"),
        "cc_debt":   triple.get("cc_debt"),
        "xg_debt":   triple.get("xg_debt"),
        "xgot_debt": triple.get("xgot_debt"),
        "triple_debt_formed": triple.get("triple_debt_formed"),
        "failed_reasons":     triple.get("failed_reasons") or [],
        "block_reason":       triple.get("block_reason"),
        "near_miss_type":     _near_miss_type(triple, dt),
        "near_miss_score":    _near_miss_score(triple),
        "distance_to_pass":   _compute_distance(triple),
        "dominant_trailing_result":       dt_result_str,
        "dominant_trailing_block_reason": (dt.get("block_reason")
                                            if dt else None),
        "final_decision":  eval_result.get("final_decision"),
        "telegram_sent":   eval_result.get("final_decision") == FINAL_SENT,
        "error":           eval_result.get("error"),
        "turbo_version":   __version__,
    }


def build_approved_record(ms_dict, decision_dict, eval_result):
    """Record pra sinal aprovado (banco sidecar)."""
    record = build_near_miss_record(ms_dict, decision_dict, eval_result)
    record["turbo_enforced"]            = True
    record["triple_debt_formed"]        = True
    record["dominant_trailing_approved"] = True
    return record


def near_miss_log(record, *, path=None):
    p = Path(path) if path else NEAR_MISS_LOG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return p


def approved_signal_log(record, *, path=None):
    p = Path(path) if path else APPROVED_SIGNALS_LOG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return p
