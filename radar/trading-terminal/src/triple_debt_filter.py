"""
TRIPLE_DEBT_FILTER — Nova regra-mãe 3.1.2.0 Turbo.

Camada obrigatória de validação ANTES de notificar:
A TRINCA exige três dívidas estatísticas simultâneas (AND lógico):
  - dívida por chances claras (CC)
  - dívida por xG
  - dívida por xGOT

Fluxo:
  1. Classificar escopo (unilateral / bilateral / none) — determinístico.
  2. Calcular as 3 dívidas no escopo correto.
  3. TRINCA forma se as 3 são true.
  4. Em dry-run: appendar resultado em logs/triple_debt_audit.jsonl.

Função pura — NÃO toca regra legacy 3.1.2.0 (src/codigo_3_1.py,
rules_over.py, rules_back.py), Telegram, banco limpo, daemon ou
qualquer outro arquivo. Audit log opcional, em arquivo novo.

Uso típico (no daemon, futuro, em dry-run):
    from src.triple_debt_filter import validate_triple_debt_filter, audit_log
    result = validate_triple_debt_filter(match_state)
    audit_log(match_state, original_tier, original_alert_type, result)
    # Dry-run: NÃO usa result["would_block_signal"] pra bloquear nada.
    # Enforcement futuro: if result["would_block_signal"]: skip_telegram()
"""
import json
from datetime import datetime, timezone
from pathlib import Path

__version__ = "1.0.0"

# === Limiares (do spec) ==================================================
# Escopo unilateral — 5 critérios; precisa bater ≥4 obrigatoriamente
# incluindo A (side_cc ≥ 3)
UNI_MIN_CC               = 3
UNI_MIN_CC_SHARE         = 0.70
UNI_MIN_XG_SHARE         = 0.65
UNI_MIN_XGOT_SHARE       = 0.65
UNI_MAX_OPP_CC           = 1
UNI_MIN_CC_DIFF          = 2
UNI_MIN_CRITERIA_HIT     = 4   # de 5; A obrigatório

# Escopo bilateral — 4 critérios (A-D)
BI_MIN_TOTAL_CC          = 3
BI_MIN_TOTAL_XG          = 1.00
BI_MIN_TOTAL_XGOT        = 1.00
# Contribuição mínima do lado mais fraco — ≥2 de 3
BI_WEAK_MIN_CC           = 1
BI_WEAK_MIN_XG           = 0.30
BI_WEAK_MIN_XGOT         = 0.25
BI_WEAK_MIN_CRITERIA_HIT = 2

# Dívida xG/xGOT: precisa superar gols + 1.00
DEBT_MARGIN              = 1.00

# === Block reasons =======================================================
REASON_FAILED_CC               = "triple_debt_failed_cc"
REASON_FAILED_XG               = "triple_debt_failed_xg"
REASON_FAILED_XGOT             = "triple_debt_failed_xgot"
REASON_FAILED_MULTIPLE         = "triple_debt_failed_multiple"
REASON_NO_REAL_DEBT            = "triple_debt_no_real_debt"
REASON_SCOPE_NOT_CLASSIFIED    = "triple_debt_scope_not_classified"
# Dado ausente no feed — distinto de falha esportiva.
REASON_MISSING_XGOT            = "triple_debt_missing_xgot"
REASON_MISSING_XG              = "triple_debt_missing_xg"
REASON_MISSING_CC              = "triple_debt_missing_cc"


# === Helpers =============================================================
def _num(v, default=0):
    try:
        return float(v) if isinstance(v, float) else int(v)
    except (TypeError, ValueError):
        return default


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_div(num, den):
    return (num / den) if den else 0.0


def _check_unilateral_side(side, *, side_cc, opp_cc,
                              side_cc_share, side_xg_share, side_xgot_share):
    """Retorna (hits:int, mandatory_A:bool, breakdown:dict).
    side é informativo (string)."""
    A = side_cc >= UNI_MIN_CC
    B = side_cc_share   >= UNI_MIN_CC_SHARE
    C = side_xg_share   >= UNI_MIN_XG_SHARE
    D = side_xgot_share >= UNI_MIN_XGOT_SHARE
    E = (opp_cc <= UNI_MAX_OPP_CC) or ((side_cc - opp_cc) >= UNI_MIN_CC_DIFF)
    hits = sum(1 for x in (A, B, C, D, E) if x)
    return hits, A, {
        "A_side_cc_ge_3": A, "B_cc_share_ge_70": B,
        "C_xg_share_ge_65": C, "D_xgot_share_ge_65": D,
        "E_opp_cc_isolated": E,
    }


def _check_bilateral(*, total_cc, total_xg, total_xgot,
                        weak_cc, weak_xg, weak_xgot):
    """Retorna (hits_main:int, weak_hits:int, breakdown:dict)."""
    A = total_cc   >= BI_MIN_TOTAL_CC
    B = total_xg   >= BI_MIN_TOTAL_XG
    C = total_xgot >= BI_MIN_TOTAL_XGOT
    weak_cc_ok   = weak_cc   >= BI_WEAK_MIN_CC
    weak_xg_ok   = weak_xg   >= BI_WEAK_MIN_XG
    weak_xgot_ok = weak_xgot >= BI_WEAK_MIN_XGOT
    weak_hits = sum(1 for x in (weak_cc_ok, weak_xg_ok, weak_xgot_ok) if x)
    main_hits = sum(1 for x in (A, B, C) if x)
    # Critério D: lado fraco contribuiu (≥2 de 3)
    D = weak_hits >= BI_WEAK_MIN_CRITERIA_HIT
    breakdown = {
        "A_total_cc_ge_3":   A,
        "B_total_xg_ge_1":   B,
        "C_total_xgot_ge_1": C,
        "D_weak_contributed": D,
        "weak_breakdown": {
            "cc_ok": weak_cc_ok, "xg_ok": weak_xg_ok, "xgot_ok": weak_xgot_ok,
        },
    }
    return main_hits, weak_hits, A and B and C and D, breakdown


def _classify_scope(match_state):
    """Decide scope='unilateral'|'bilateral'|'none' e scope_side.
    Determinístico — não olha placar."""
    h_cc = _num(match_state.get("home_cc"))
    a_cc = _num(match_state.get("away_cc"))
    h_xg = _f(match_state.get("home_xg"))
    a_xg = _f(match_state.get("away_xg"))
    h_xgot = _f(match_state.get("home_xgot"))
    a_xgot = _f(match_state.get("away_xgot"))

    total_cc   = h_cc + a_cc
    total_xg   = h_xg + a_xg
    total_xgot = h_xgot + a_xgot

    h_cc_share   = _safe_div(h_cc,   total_cc)
    a_cc_share   = _safe_div(a_cc,   total_cc)
    h_xg_share   = _safe_div(h_xg,   total_xg)
    a_xg_share   = _safe_div(a_xg,   total_xg)
    h_xgot_share = _safe_div(h_xgot, total_xgot)
    a_xgot_share = _safe_div(a_xgot, total_xgot)

    # Check unilateral em cada lado
    h_hits, h_A, h_br = _check_unilateral_side("home",
        side_cc=h_cc, opp_cc=a_cc,
        side_cc_share=h_cc_share,
        side_xg_share=h_xg_share,
        side_xgot_share=h_xgot_share)
    a_hits, a_A, a_br = _check_unilateral_side("away",
        side_cc=a_cc, opp_cc=h_cc,
        side_cc_share=a_cc_share,
        side_xg_share=a_xg_share,
        side_xgot_share=a_xgot_share)

    home_is_uni = h_A and h_hits >= UNI_MIN_CRITERIA_HIT
    away_is_uni = a_A and a_hits >= UNI_MIN_CRITERIA_HIT

    meta = {
        "totals": {"cc": total_cc, "xg": round(total_xg, 3),
                    "xgot": round(total_xgot, 3)},
        "shares": {
            "home_cc": round(h_cc_share, 3), "away_cc": round(a_cc_share, 3),
            "home_xg": round(h_xg_share, 3), "away_xg": round(a_xg_share, 3),
            "home_xgot": round(h_xgot_share, 3),
            "away_xgot": round(a_xgot_share, 3),
        },
        "unilateral_home": {"hits": h_hits, "mandatory_A": h_A,
                             "breakdown": h_br},
        "unilateral_away": {"hits": a_hits, "mandatory_A": a_A,
                             "breakdown": a_br},
    }

    # Resolve conflito: se ambos qualificam (raro), vence o de mais hits
    # ou desempate pelo share de CC
    if home_is_uni and away_is_uni:
        if h_hits != a_hits:
            return ("unilateral", "home" if h_hits > a_hits else "away", meta)
        return ("unilateral", "home" if h_cc_share >= a_cc_share else "away", meta)
    if home_is_uni:
        return ("unilateral", "home", meta)
    if away_is_uni:
        return ("unilateral", "away", meta)

    # Bilateral: nenhum dos lados é unilateral
    weak_side = "away" if h_cc >= a_cc else "home"
    weak_cc   = a_cc   if weak_side == "away" else h_cc
    weak_xg   = a_xg   if weak_side == "away" else h_xg
    weak_xgot = a_xgot if weak_side == "away" else h_xgot
    bi_main_hits, bi_weak_hits, bi_qualifies, bi_br = _check_bilateral(
        total_cc=total_cc, total_xg=total_xg, total_xgot=total_xgot,
        weak_cc=weak_cc, weak_xg=weak_xg, weak_xgot=weak_xgot)
    meta["bilateral"] = {
        "main_hits": bi_main_hits, "weak_hits": bi_weak_hits,
        "weak_side": weak_side, "breakdown": bi_br,
    }
    if bi_qualifies:
        return ("bilateral", "total", meta)
    return ("none", None, meta)


# === Resposta padrão pra dado ausente ====================================
def _build_missing_data_response(reason, p, which):
    """Constrói retorno consistente quando _raw está None.
    Diagnóstico explícito — NUNCA mascarar como falha esportiva."""
    return {
        "schema_version": __version__,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "triple_debt_formed": False,
        "scope": "none", "scope_side": None,
        "scope_meta": {},
        "cc_in_scope": 0, "xg_in_scope": 0.0, "xgot_in_scope": 0.0,
        "goals_in_scope": 0, "expected_goals_by_cc": 0,
        "cc_debt": False, "xg_debt": False, "xgot_debt": False,
        "failed_reasons": [],
        "block_reason": reason,
        "would_block_signal": True,
        "missing_metric": which,
        "missing_home_value": p.get(f"home_{which}_raw"),
        "missing_away_value": p.get(f"away_{which}_raw"),
        "cc_rate_minutes": p.get("cc_rate_minutes"),
    }


# === Núcleo: validate_triple_debt_filter() ===============================
def validate_triple_debt_filter(match_state):
    """Avalia uma fotografia do jogo sob a TRINCA.

    Args:
      match_state: dict com:
        home_cc, away_cc, home_xg, away_xg, home_xgot, away_xgot,
        home_goals, away_goals, minute (opcionais: cc_rate_minutes,
        match_id, home_team, away_team, ...)

    Returns: dict imutável com decisão completa (esquema documentado no
      header do módulo).
    """
    p = match_state or {}

    # === Gate "DADO AUSENTE" ============================================
    # Se o caller passou explicitamente _raw=None (vindo do parser que
    # distingue ausente de zero real), bloquear com motivo específico
    # ANTES de classificar escopo. NÃO mascarar como falha esportiva.
    # Backward compat: só ativa se a chave _raw estiver presente no dict.
    def _missing(key):
        return key in p and p[key] is None
    if _missing("home_xgot_raw") or _missing("away_xgot_raw"):
        return _build_missing_data_response(REASON_MISSING_XGOT, p,
                                              "xgot")
    if _missing("home_xg_raw") or _missing("away_xg_raw"):
        return _build_missing_data_response(REASON_MISSING_XG, p, "xg")
    if _missing("home_bc_raw") or _missing("away_bc_raw"):
        return _build_missing_data_response(REASON_MISSING_CC, p, "cc")

    h_cc = _num(p.get("home_cc"))
    a_cc = _num(p.get("away_cc"))
    h_xg = _f(p.get("home_xg"))
    a_xg = _f(p.get("away_xg"))
    h_xgot = _f(p.get("home_xgot"))
    a_xgot = _f(p.get("away_xgot"))
    h_g = _num(p.get("home_goals"))
    a_g = _num(p.get("away_goals"))

    scope, scope_side, scope_meta = _classify_scope(p)

    out = {
        "schema_version": __version__,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "triple_debt_formed": False,
        "scope": scope, "scope_side": scope_side,
        "scope_meta": scope_meta,
        "cc_in_scope": 0,
        "xg_in_scope": 0.0,
        "xgot_in_scope": 0.0,
        "goals_in_scope": 0,
        "expected_goals_by_cc": 0,
        "cc_debt": False, "xg_debt": False, "xgot_debt": False,
        "failed_reasons": [],
        "block_reason": None,
        "would_block_signal": True,
        "cc_rate_minutes": p.get("cc_rate_minutes"),
    }

    if scope == "none":
        out["block_reason"] = REASON_SCOPE_NOT_CLASSIFIED
        return out

    # Métricas no escopo
    if scope == "unilateral":
        if scope_side == "home":
            cc, xg, xgot, goals = h_cc, h_xg, h_xgot, h_g
        else:
            cc, xg, xgot, goals = a_cc, a_xg, a_xgot, a_g
    else:  # bilateral
        cc, xg, xgot, goals = h_cc + a_cc, h_xg + a_xg, h_xgot + a_xgot, h_g + a_g

    expected = cc // 3  # floor
    cc_debt   = expected > goals
    xg_debt   = xg   >= goals + DEBT_MARGIN
    xgot_debt = xgot >= goals + DEBT_MARGIN

    out["cc_in_scope"] = cc
    out["xg_in_scope"] = round(xg, 3)
    out["xgot_in_scope"] = round(xgot, 3)
    out["goals_in_scope"] = goals
    out["expected_goals_by_cc"] = expected
    out["cc_debt"]   = cc_debt
    out["xg_debt"]   = xg_debt
    out["xgot_debt"] = xgot_debt

    # failed_reasons
    failed = []
    if not cc_debt:   failed.append(REASON_FAILED_CC)
    if not xg_debt:   failed.append(REASON_FAILED_XG)
    if not xgot_debt: failed.append(REASON_FAILED_XGOT)
    out["failed_reasons"] = failed

    if len(failed) == 0:
        out["triple_debt_formed"] = True
        out["block_reason"] = None
        out["would_block_signal"] = False
        return out

    # 3 falhas simultâneas → gols já pagaram (ou nunca houve dívida real)
    if len(failed) == 3:
        out["block_reason"] = REASON_NO_REAL_DEBT
        out["would_block_signal"] = True
        return out

    # 1 falha → reporta a específica
    if len(failed) == 1:
        out["block_reason"] = failed[0]
        out["would_block_signal"] = True
        return out

    # 2 falhas → "multiple"
    out["block_reason"] = REASON_FAILED_MULTIPLE
    out["would_block_signal"] = True
    return out


# === Audit log (dry-run) =================================================
AUDIT_LOG_PATH = (Path(__file__).resolve().parent.parent
                  / "logs" / "triple_debt_audit.jsonl")


def audit_log(match_state, original_tier, original_alert_type,
                result, *, path=None):
    """Appenda registro de auditoria em logs/triple_debt_audit.jsonl.

    Não altera o match_state, não escreve em nenhum outro arquivo.
    Cria a pasta logs/ se preciso.
    """
    p = Path(path) if path else AUDIT_LOG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    ms = match_state or {}
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "match_id":  ms.get("match_id"),
        "home_team": ms.get("home_team") or ms.get("home"),
        "away_team": ms.get("away_team") or ms.get("away"),
        "minute":    ms.get("minute"),
        "score":     ms.get("score") or
                       f'{_num(ms.get("home_goals"))}-{_num(ms.get("away_goals"))}',
        "original_tier":       original_tier,
        "original_alert_type": original_alert_type,
        "triple_debt_formed":  result.get("triple_debt_formed"),
        "scope":               result.get("scope"),
        "scope_side":          result.get("scope_side"),
        "cc_debt":             result.get("cc_debt"),
        "xg_debt":             result.get("xg_debt"),
        "xgot_debt":           result.get("xgot_debt"),
        "cc_in_scope":         result.get("cc_in_scope"),
        "xg_in_scope":         result.get("xg_in_scope"),
        "xgot_in_scope":       result.get("xgot_in_scope"),
        "goals_in_scope":      result.get("goals_in_scope"),
        "expected_goals_by_cc": result.get("expected_goals_by_cc"),
        "cc_rate_minutes":     result.get("cc_rate_minutes"),
        "failed_reasons":      result.get("failed_reasons"),
        "block_reason":        result.get("block_reason"),
        "would_block_signal":  result.get("would_block_signal"),
    }
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return p
