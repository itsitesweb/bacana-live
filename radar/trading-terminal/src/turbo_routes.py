"""
TURBO_ROUTES — 2 rotas de classificação + 3 tiers (WATCH/FORTE/PREMIUM).

A reforma v3.1 substitui a Trinca rígida única por um sistema dual:

  ROTA A — Chances Claras (a métrica mãe)
    Jogo qualificado por ritmo de CC + dívida CC/xG/xGOT.

  ROTA B — Volume Qualificado (sem CC, mas pró-gol)
    Jogo qualificado por ritmo de finalizações + SOT % + dívida xG/xGOT.

O jogo passa se bater UMA das duas rotas. Tier final = maior tier alcançado
entre as duas.

WATCH → radar interno (não Telegram)
FORTE → Telegram, entrada padrão (passa por DT)
PREMIUM → Telegram, entrada qualificada (passa por DT completa)

Função pura. NÃO importa Telegram, daemon, regra legacy.

Compatibilidade: o módulo usa o classificador de escopo da Trinca atual
(unilateral/bilateral) via triple_debt_filter._classify_scope.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from src.triple_debt_filter import _classify_scope

__version__ = "1.0.0"

# === Tiers ===============================================================
TIER_NONE     = None
TIER_WATCH    = "WATCH"
TIER_FORTE    = "FORTE"
TIER_PREMIUM  = "PREMIUM"

TIER_ORDER = {TIER_WATCH: 1, TIER_FORTE: 2, TIER_PREMIUM: 3}


# === Rotas ===============================================================
ROUTE_A = "rota_a_chances_claras"
ROUTE_B = "rota_b_volume_qualificado"


# === Critérios — Rota A (Chances Claras) =================================
# Ritmo CC máximo (min por chance clara) por tier
A_CC_RATE = {TIER_WATCH: 15.0, TIER_FORTE: 12.0, TIER_PREMIUM: 10.0}
# Margem xG sobre gols (xg >= gols + margem)
A_XG_MARGIN = {TIER_WATCH: 0.80, TIER_FORTE: 1.00, TIER_PREMIUM: 1.00}
# Margem xGOT sobre gols (None = não exige)
A_XGOT_MARGIN = {TIER_WATCH: None, TIER_FORTE: 0.70, TIER_PREMIUM: 1.00}


# === Critérios — Rota B (Volume Qualificado) =============================
# Ritmo finalizações máximo (min por chute) por tier
B_SHOT_RATE = {TIER_WATCH: 4.0, TIER_FORTE: 3.5, TIER_PREMIUM: 3.0}
# SOT % mínimo (piso fixo de qualidade)
B_SOT_PCT_MIN = 0.35
# Margem xG / xGOT (iguais à Rota A)
B_XG_MARGIN = {TIER_WATCH: 0.80, TIER_FORTE: 1.00, TIER_PREMIUM: 1.00}
B_XGOT_MARGIN = {TIER_WATCH: None, TIER_FORTE: 0.70, TIER_PREMIUM: 1.00}


# === Reasons =============================================================
REASON_NO_SCOPE         = "no_scope_classified"
REASON_NO_TIER_MATCHED  = "no_tier_matched"
REASON_OK               = None


# === Helpers =============================================================
def _f(v, default=0.0):
    try: return float(v)
    except (TypeError, ValueError): return default

def _num(v, default=0):
    try: return float(v) if isinstance(v, float) else int(v)
    except (TypeError, ValueError): return default

def _safe_div(num, den):
    return (num / den) if den else 0.0


def _classify_scope_shots(p):
    """Classificador de escopo PRÓPRIO da Rota B — baseado em finalizações.
    Aceita jogos sem CC. Pensado pra captar jogo pró-gol com volume.

    Returns (scope, scope_side):
      - unilateral: 1 time concentra ≥65% das finalizações + ≥6 finalizações
      - bilateral: total ≥8 finalizações + lado fraco contribui
      - none: produção insuficiente
    """
    h_shots = _num(p.get("home_shots"))
    a_shots = _num(p.get("away_shots"))
    h_sot   = _num(p.get("home_sot"))
    a_sot   = _num(p.get("away_sot"))
    total = h_shots + a_shots
    if total < 4:
        return ("none", None)

    h_share = _safe_div(h_shots, total)
    a_share = _safe_div(a_shots, total)

    # Unilateral em home
    if h_shots >= 6 and h_share >= 0.65 and a_shots <= 4:
        return ("unilateral", "home")
    if a_shots >= 6 and a_share >= 0.65 and h_shots <= 4:
        return ("unilateral", "away")

    # Bilateral: ambos contribuem mínimo
    weak = min(h_shots, a_shots)
    weak_sot = min(h_sot, a_sot)
    if total >= 8 and weak >= 2 and weak_sot >= 1:
        return ("bilateral", "total")

    return ("none", None)


def _values_in_scope(scope, scope_side, p):
    """Retorna (cc, xg, xgot, shots, sot, goals) no escopo."""
    h_cc   = _num(p.get("home_cc"));   a_cc   = _num(p.get("away_cc"))
    h_xg   = _f(p.get("home_xg"));     a_xg   = _f(p.get("away_xg"))
    h_xgot = _f(p.get("home_xgot"));   a_xgot = _f(p.get("away_xgot"))
    h_sh   = _num(p.get("home_shots")); a_sh   = _num(p.get("away_shots"))
    h_sot  = _num(p.get("home_sot"));  a_sot  = _num(p.get("away_sot"))
    h_g    = _num(p.get("home_goals")); a_g    = _num(p.get("away_goals"))

    if scope == "unilateral":
        if scope_side == "home":
            return (h_cc, h_xg, h_xgot, h_sh, h_sot, h_g)
        return (a_cc, a_xg, a_xgot, a_sh, a_sot, a_g)
    # bilateral
    return (h_cc + a_cc, h_xg + a_xg, h_xgot + a_xgot,
            h_sh + a_sh, h_sot + a_sot, h_g + a_g)


def _check_rota_a(tier, *, cc, xg, xgot, goals, minute):
    """True se o jogo bate Rota A no tier dado."""
    if cc <= 0:
        return False, f"cc_in_scope={cc}"
    cc_rate = minute / cc
    if cc_rate > A_CC_RATE[tier]:
        return False, f"cc_rate={cc_rate:.1f}>limit={A_CC_RATE[tier]}"
    # CC debt: floor(cc/3) > goals
    expected_by_cc = int(cc // 3)
    if expected_by_cc <= goals:
        return False, f"cc_debt_failed: expected={expected_by_cc}<=goals={goals}"
    # xG debt
    if xg < goals + A_XG_MARGIN[tier]:
        return False, f"xg_debt_failed: {xg:.2f}<{goals}+{A_XG_MARGIN[tier]}"
    # xGOT debt (opcional no WATCH)
    if A_XGOT_MARGIN[tier] is not None:
        if xgot < goals + A_XGOT_MARGIN[tier]:
            return False, f"xgot_debt_failed: {xgot:.2f}<{goals}+{A_XGOT_MARGIN[tier]}"
    return True, "ok"


def _check_rota_b(tier, *, shots, sot, xg, xgot, goals, minute):
    """True se o jogo bate Rota B no tier dado."""
    if shots <= 0:
        return False, f"shots_in_scope={shots}"
    shot_rate = minute / shots
    if shot_rate > B_SHOT_RATE[tier]:
        return False, f"shot_rate={shot_rate:.2f}>limit={B_SHOT_RATE[tier]}"
    sot_pct = _safe_div(sot, shots)
    if sot_pct < B_SOT_PCT_MIN:
        return False, f"sot_pct={sot_pct:.2f}<{B_SOT_PCT_MIN}"
    if xg < goals + B_XG_MARGIN[tier]:
        return False, f"xg_debt_failed: {xg:.2f}<{goals}+{B_XG_MARGIN[tier]}"
    if B_XGOT_MARGIN[tier] is not None:
        if xgot < goals + B_XGOT_MARGIN[tier]:
            return False, f"xgot_debt_failed: {xgot:.2f}<{goals}+{B_XGOT_MARGIN[tier]}"
    return True, "ok"


# === Núcleo ==============================================================
def classify_routes(match_state):
    """Avalia as 2 rotas em 3 tiers e devolve o maior tier alcançado.

    Args:
      match_state: dict com home_cc/away_cc, home_xg/away_xg,
        home_xgot/away_xgot, home_shots/away_shots, home_sot/away_sot,
        home_goals/away_goals, minute.

    Returns: dict com:
      classified: bool
      tier: WATCH | FORTE | PREMIUM | None
      route: rota_a_chances_claras | rota_b_volume_qualificado | None
      scope: unilateral | bilateral | none
      scope_side: home | away | total | None
      route_a_tier: maior tier alcançado pela Rota A
      route_b_tier: maior tier alcançado pela Rota B
      reason: None se classificou, motivo se não
      details: dict com cc_rate, shot_rate, sot_pct, etc — auditável
      schema_version, evaluated_at_utc
    """
    p = match_state or {}
    minute = max(1, _num(p.get("minute"), 1))   # evita div por zero

    out = {
        "schema_version": __version__,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "classified": False,
        "tier": TIER_NONE,
        "route": None,
        "scope": None, "scope_side": None,
        "route_a_tier": TIER_NONE,
        "route_b_tier": TIER_NONE,
        "reason": None,
        "details": {},
    }

    # 1A. Classificar escopo da Rota A (chances claras)
    scope_a, side_a, _meta_a = _classify_scope(p)

    # 1B. Classificar escopo da Rota B (finalizações totais — pode pegar
    # jogos sem chance clara)
    scope_b, side_b = _classify_scope_shots(p)

    # Reportar o escopo "principal" (preferencial: o que tier maior usar)
    # Vamos preencher depois de saber quem ganhou
    if scope_a == "none" and scope_b == "none":
        out["scope"] = "none"
        out["scope_side"] = None
        out["reason"] = REASON_NO_SCOPE
        return out

    # 2A. Valores no escopo da Rota A
    if scope_a != "none":
        cc_a, xg_a, xgot_a, shots_a, sot_a, goals_a = _values_in_scope(
            scope_a, side_a, p)
        for tier in (TIER_PREMIUM, TIER_FORTE, TIER_WATCH):
            ok, _ = _check_rota_a(tier, cc=cc_a, xg=xg_a, xgot=xgot_a,
                                       goals=goals_a, minute=minute)
            if ok:
                out["route_a_tier"] = tier
                break

    # 2B. Valores no escopo da Rota B
    if scope_b != "none":
        cc_b, xg_b, xgot_b, shots_b, sot_b, goals_b = _values_in_scope(
            scope_b, side_b, p)
        for tier in (TIER_PREMIUM, TIER_FORTE, TIER_WATCH):
            ok, _ = _check_rota_b(tier, shots=shots_b, sot=sot_b,
                                       xg=xg_b, xgot=xgot_b,
                                       goals=goals_b, minute=minute)
            if ok:
                out["route_b_tier"] = tier
                break

    # 3. Preencher escopo principal e details na rota vencedora
    a, b = out["route_a_tier"], out["route_b_tier"]
    a_rank = TIER_ORDER.get(a, 0); b_rank = TIER_ORDER.get(b, 0)
    if a_rank >= b_rank and a_rank > 0:
        scope, scope_side = scope_a, side_a
        cc, xg, xgot, shots, sot, goals = _values_in_scope(scope_a, side_a, p)
    elif b_rank > 0:
        scope, scope_side = scope_b, side_b
        cc, xg, xgot, shots, sot, goals = _values_in_scope(scope_b, side_b, p)
    else:
        # Nenhuma rota encontrou tier — usa A por default pra reportar
        scope, scope_side = (scope_a if scope_a != "none" else scope_b,
                              side_a if scope_a != "none" else side_b)
        cc, xg, xgot, shots, sot, goals = _values_in_scope(scope, scope_side, p)
    out["scope"] = scope
    out["scope_side"] = scope_side
    out["details"] = {
        "minute": minute,
        "cc": cc, "xg": round(xg, 3), "xgot": round(xgot, 3),
        "shots": shots, "sot": sot, "goals": goals,
        "cc_rate": round(_safe_div(minute, cc), 2) if cc else None,
        "shot_rate": round(_safe_div(minute, shots), 2) if shots else None,
        "sot_pct": round(_safe_div(sot, shots), 3) if shots else None,
        "scope_a": scope_a, "scope_b": scope_b,
    }

    # 5. Escolhe o MAIOR tier entre as duas
    a, b = out["route_a_tier"], out["route_b_tier"]
    a_rank = TIER_ORDER.get(a, 0)
    b_rank = TIER_ORDER.get(b, 0)
    if a_rank == 0 and b_rank == 0:
        out["reason"] = REASON_NO_TIER_MATCHED
        return out
    if a_rank >= b_rank:
        out["tier"] = a; out["route"] = ROUTE_A
    else:
        out["tier"] = b; out["route"] = ROUTE_B
    out["classified"] = True
    return out


# === Helpers de tier =====================================================
def is_watch(result):
    return result.get("tier") == TIER_WATCH

def is_forte_or_premium(result):
    return result.get("tier") in (TIER_FORTE, TIER_PREMIUM)


# === Radar interno (banco append-only para WATCH) =========================
_ROOT = Path(__file__).resolve().parent.parent
RADAR_LOG_PATH = _ROOT / "logs" / "turbo_radar.jsonl"


def radar_log(record, *, path=None):
    """Appenda WATCH em logs/turbo_radar.jsonl. NÃO toca Telegram.
    Esse banco é pra consulta sua — radar interno."""
    p = Path(path) if path else RADAR_LOG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return p


def build_radar_record(ms_dict, decision_dict, routes_result):
    """Monta record do WATCH pra logar no radar."""
    return {
        "timestamp": routes_result.get("evaluated_at_utc"),
        "match_id": ms_dict.get("match_id"),
        "home_team": ms_dict.get("home"), "away_team": ms_dict.get("away"),
        "minute": ms_dict.get("minute"),
        "score": f"{ms_dict.get('home_score', 0)}-{ms_dict.get('away_score', 0)}",
        "original_tier": decision_dict.get("message_severity"),
        "original_alert_type": decision_dict.get("recommended_action"),
        "tier": routes_result.get("tier"),
        "route": routes_result.get("route"),
        "scope": routes_result.get("scope"),
        "scope_side": routes_result.get("scope_side"),
        "route_a_tier": routes_result.get("route_a_tier"),
        "route_b_tier": routes_result.get("route_b_tier"),
        "details": routes_result.get("details"),
        "destination": "RADAR_INTERNO_NO_TELEGRAM",
        "version": __version__,
    }
