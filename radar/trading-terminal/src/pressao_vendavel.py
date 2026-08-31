"""
PRESSÃO VENDÁVEL — Rota de detecção de trade BACK alta + LAY baixa.

Filosofia (trader, não apostador):
  - Pegar BACK quando odd ainda tá alta porque time NÃO materializou
  - Vender (LAY) quando vier o gol e odd despencar
  - Mercado fica "atrás" das estatísticas — sistema antecipa

Quando dispara:
  - Time empatado OU 1 gol atrás (odd ainda tem prêmio)
  - Mas tem dominância estatística clara
  - Pressão acumulada + qualidade na finalização
  - Adversário sem reação

Critérios (TODOS obrigatórios — defensivo igual TRINCA):
  1. Janela: min 25-70
  2. Placar: empatado OU candidato atrás de 1 gol
  3. CC candidato ≥ 2
  4. xG candidato ≥ 1.0
  5. xGOT candidato ≥ 0.8
  6. Posse ≥ 60% OU toques área ≥ 2x adversário
  7. SOT% ≥ 35%
  8. Adversário: xG ≤ 0.7

Tese operacional:
  "BACK [time] agora. Odd estimada {ODD_HINT}. Quando vier o gol, odd
  despenca pra {ODD_GOAL_HINT}. Sair vendendo aí."
"""
__version__ = "1.0.0"

# Filtros
MIN_MINUTE      = 25
MAX_MINUTE      = 70
MIN_CC          = 2
MIN_XG          = 1.0
MIN_XGOT        = 0.8
MIN_POSSE       = 60.0
MIN_TOQ_RATIO   = 2.0
MIN_SOT_PCT     = 0.35
MAX_OPP_XG      = 0.7


def _safe_div(num, den):
    return (num / den) if den else 0.0


def _eval_side(side: str, ms_dict: dict, ctx: dict) -> dict:
    """Avalia critérios pra UM lado (home ou away)."""
    minute = ms_dict.get("minute", 0)
    h_g = ms_dict.get("home_score", 0)
    a_g = ms_dict.get("away_score", 0)
    diff = h_g - a_g

    other = "away" if side == "home" else "home"
    own_g = h_g if side == "home" else a_g
    opp_g = a_g if side == "home" else h_g

    # diff próprio: positivo = na frente, negativo = atrás
    own_diff = own_g - opp_g

    cc = ms_dict.get(f"{side}_cc", 0) or 0
    xg = ms_dict.get(f"{side}_xg", 0.0) or 0.0
    xgot = ms_dict.get(f"{side}_xgot", 0.0) or 0.0
    shots = ms_dict.get(f"{side}_shots", 0) or 0
    sot = ms_dict.get(f"{side}_sot", 0) or 0
    opp_xg = ms_dict.get(f"{other}_xg", 0.0) or 0.0
    opp_cc = ms_dict.get(f"{other}_cc", 0) or 0

    posse_h, posse_a = ctx.get("posse", (50, 50))
    toq_h, toq_a = ctx.get("toques_area", (0, 0))
    posse = posse_h if side == "home" else posse_a
    toq = toq_h if side == "home" else toq_a
    toq_opp = toq_a if side == "home" else toq_h

    out = {
        "side": side, "minute": minute,
        "score": f"{own_g}-{opp_g}",
        "qualified": False, "fails": [],
        "metrics": {
            "cc": cc, "xg": xg, "xgot": xgot,
            "shots": shots, "sot": sot,
            "sot_pct": round(_safe_div(sot, shots), 3),
            "posse": posse, "toq": toq, "toq_opp": toq_opp,
            "opp_xg": opp_xg, "own_diff": own_diff,
        },
    }

    # 1. Janela
    if minute < MIN_MINUTE:
        out["fails"].append(f"minute<{MIN_MINUTE}")
        return out
    if minute > MAX_MINUTE:
        out["fails"].append(f"minute>{MAX_MINUTE}")
        return out

    # 2. Placar: empatado ou atrás de 1
    if own_diff > 0:
        out["fails"].append(f"ja_na_frente_diff={own_diff}")
        return out
    if own_diff <= -2:
        out["fails"].append(f"atras_demais_diff={own_diff}")
        return out

    # 3. CC mínimo
    if cc < MIN_CC:
        out["fails"].append(f"cc<{MIN_CC}")
        return out

    # 4. xG mínimo
    if xg < MIN_XG:
        out["fails"].append(f"xg<{MIN_XG}")
        return out

    # 5. xGOT mínimo
    if xgot < MIN_XGOT:
        out["fails"].append(f"xgot<{MIN_XGOT}")
        return out

    # 6. Posse OU ratio de toques
    posse_ok = posse >= MIN_POSSE
    ratio = _safe_div(toq, toq_opp) if toq_opp > 0 else 99
    toq_ratio_ok = ratio >= MIN_TOQ_RATIO and toq >= 8
    if not (posse_ok or toq_ratio_ok):
        out["fails"].append(
            f"sem_dominancia (posse={posse:.0f}, toq_ratio={ratio:.1f})")
        return out

    # 7. SOT%
    sot_pct = _safe_div(sot, shots)
    if sot_pct < MIN_SOT_PCT:
        out["fails"].append(f"sot_pct<{MIN_SOT_PCT}")
        return out

    # 8. Adversário sem reação
    if opp_xg > MAX_OPP_XG:
        out["fails"].append(f"opp_xg>{MAX_OPP_XG}")
        return out

    out["qualified"] = True
    return out


def evaluate(ms_dict: dict, ctx: dict, scenario: dict = None) -> dict:
    """Avalia AMBOS os lados. Retorna o melhor candidato qualificado.

    Returns:
      {
        "qualified": bool,
        "side": "home"|"away"|None,
        "team": str,
        "minute": int,
        "score": str,
        "tese": str,
        "metrics": {...},
        "probability": {...},  ← se qualified, dict com prob/fair_odd/min_odd
        "audit": {"home": {...}, "away": {...}}
      }
    """
    minute = ms_dict.get("minute", 0)
    home = ms_dict.get("home", "")
    away = ms_dict.get("away", "")

    home_eval = _eval_side("home", ms_dict, ctx)
    away_eval = _eval_side("away", ms_dict, ctx)

    out = {
        "schema_version": __version__,
        "qualified": False,
        "side": None,
        "team": "",
        "minute": minute,
        "score": f"{ms_dict.get('home_score',0)}-{ms_dict.get('away_score',0)}",
        "tese": "",
        "metrics": {},
        "audit": {"home": home_eval, "away": away_eval},
    }

    qualified = []
    if home_eval["qualified"]:
        qualified.append(("home", home, home_eval))
    if away_eval["qualified"]:
        qualified.append(("away", away, away_eval))

    if not qualified:
        return out

    # Escolhe lado com maior xG (proxy de "mais perto de furar")
    side, team, ev = max(qualified, key=lambda x: x[2]["metrics"]["xg"])
    m = ev["metrics"]

    # Probabilidade real via Poisson
    try:
        from src import match_probability as _prob
    except ImportError:
        from . import match_probability as _prob
    sc = scenario or {"scenario": "indef", "side": None}
    prob = _prob.compute_event_probability(ms_dict, sc, side)

    tese = (
        f"BACK {team} agora — pressão acumulada e adversário sem reação. "
        f"Modelo aponta {prob['prob_target']:.0f}% de probabilidade do "
        f"{team} vencer. Odd justa = {prob['fair_odd']:.2f}. "
        f"Entrar apenas se odd ≥ {prob['min_recommended_odd']:.2f}."
    )

    out["qualified"] = True
    out["side"] = side
    out["team"] = team
    out["tese"] = tese
    out["metrics"] = m
    out["probability"] = prob
    return out
