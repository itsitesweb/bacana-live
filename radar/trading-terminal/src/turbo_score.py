"""
TURBO_SCORE — Score ponderado da Quádrupla + 6 filtros eliminatórios.

Pesos confirmados pelo usuário:
  CC    35% — métrica mãe, resultado material
  xGOT  25% — finalização que acertou alvo
  xG    20% — qualidade do chute construído
  xA    20% — qualidade do passe que criou a chance

Filtros eliminatórios (TODOS obrigatórios):
  1. minute >= 15 (aquecimento)
  2. SOT % >= 30% (eficiência mínima)
  3. ritmo CC <= 15 min/CC (métrica mãe presente)
  4. ritmo finalizações <= 3.5 min/chute (jogo agressivo)
  5. SOT absoluto projetado >= 9 no jogo (jogo qualificado)
  6. nenhuma das 4 métricas igual a zero

Tiers:
  PREMIUM 85+ | FORTE 75-84 | WATCH 60-74 | Silêncio <60

Função pura. Não toca Telegram, não escreve em disco.
"""
__version__ = "1.0.0"

# Pesos
W_CC, W_XGOT, W_XG, W_XA = 0.35, 0.25, 0.20, 0.20

# Filtros
MIN_MINUTE_FOR_ENTRY     = 15
MIN_SOT_PCT              = 0.30
MAX_CC_RATE              = 15.0
MAX_SHOT_RATE            = 3.5
MIN_SOT_ABSOLUTE_PROJECTED = 9
GAME_TOTAL_MINUTES       = 95

# Thresholds
THRESHOLD_PREMIUM = 85
THRESHOLD_FORTE   = 75
THRESHOLD_WATCH   = 60


def _safe_div(num, den):
    return (num / den) if den else 0.0


def _normalize_cc_rate(cc_rate: float) -> float:
    """Rate CC menor é melhor. 8min/CC=100, 15min/CC=60, 20+=0."""
    if cc_rate <= 0: return 0.0
    if cc_rate <= 8:  return 100.0
    if cc_rate <= 12: return 90.0 - (cc_rate - 8) * 5
    if cc_rate <= 15: return 70.0 - (cc_rate - 12) * 3.33
    return max(0.0, 60.0 - (cc_rate - 15) * 6)


def _normalize_xgot(xgot: float, goals: int) -> float:
    """xGOT relativo a gols. xgot > goals + 1.0 é PREMIUM."""
    delta = xgot - goals
    if delta >= 1.5: return 100.0
    if delta >= 1.0: return 80.0 + (delta - 1.0) * 40
    if delta >= 0.5: return 50.0 + (delta - 0.5) * 60
    if delta >= 0.0: return 20.0 + delta * 60
    return max(0.0, 20.0 + delta * 30)


def _normalize_xg(xg: float, goals: int) -> float:
    delta = xg - goals
    if delta >= 1.5: return 100.0
    if delta >= 1.0: return 85.0 + (delta - 1.0) * 30
    if delta >= 0.5: return 55.0 + (delta - 0.5) * 60
    if delta >= 0.0: return 25.0 + delta * 60
    return max(0.0, 25.0 + delta * 25)


def _normalize_xa(xa: float) -> float:
    """xA absoluto — quantos passes qualificados criando chance."""
    if xa >= 1.5: return 100.0
    if xa >= 1.0: return 80.0 + (xa - 1.0) * 40
    if xa >= 0.6: return 50.0 + (xa - 0.6) * 75
    if xa >= 0.3: return 25.0 + (xa - 0.3) * 83
    return max(0.0, xa * 83)


def _scope_aggregate(ms_dict: dict):
    """Soma das duas equipes (escopo bilateral) ou apenas o dominante.
    Critério: se um time concentra >=70% da produção de CC + SOT, é unilateral.
    Senão soma os dois.
    """
    h_cc = ms_dict.get("home_cc",0) or ms_dict.get("home_bc",0)
    a_cc = ms_dict.get("away_cc",0) or ms_dict.get("away_bc",0)
    h_xg = ms_dict.get("home_xg",0.0); a_xg = ms_dict.get("away_xg",0.0)
    h_xgot = ms_dict.get("home_xgot",0.0); a_xgot = ms_dict.get("away_xgot",0.0)
    h_xa = ms_dict.get("home_xa",0.0); a_xa = ms_dict.get("away_xa",0.0)
    h_shots = ms_dict.get("home_shots",0); a_shots = ms_dict.get("away_shots",0)
    h_sot = ms_dict.get("home_sot",0); a_sot = ms_dict.get("away_sot",0)
    h_g = ms_dict.get("home_score",0); a_g = ms_dict.get("away_score",0)

    total_cc = h_cc + a_cc
    total_shots = h_shots + a_shots
    h_share_cc = _safe_div(h_cc, total_cc)
    h_share_shots = _safe_div(h_shots, total_shots)

    # Unilateral home?
    if h_share_cc >= 0.70 and h_share_shots >= 0.70 and h_cc >= 3:
        return ("unilateral", "home", h_cc, h_xg, h_xgot, h_xa, h_shots, h_sot, h_g)
    if (1 - h_share_cc) >= 0.70 and (1 - h_share_shots) >= 0.70 and a_cc >= 3:
        return ("unilateral", "away", a_cc, a_xg, a_xgot, a_xa, a_shots, a_sot, a_g)
    # Bilateral
    return ("bilateral", "total",
            total_cc, h_xg + a_xg, h_xgot + a_xgot, h_xa + a_xa,
            total_shots, h_sot + a_sot, h_g + a_g)


def evaluate(ms_dict: dict) -> dict:
    """Avalia o jogo. Returns:
      {
        "passed_filters": bool,
        "failed_filter": str | None,
        "tier": "PREMIUM" | "FORTE" | "WATCH" | None,
        "score": float (0-100),
        "scope": "unilateral" | "bilateral",
        "scope_side": "home" | "away" | "total",
        "details": {... auditável ...}
      }
    """
    minute = max(1, int(ms_dict.get("minute", 0) or 1))
    out = {
        "schema_version": __version__,
        "passed_filters": False,
        "failed_filter": None,
        "tier": None, "score": 0.0,
        "scope": None, "scope_side": None,
        "details": {"minute": minute},
    }

    # ─── Filtro 1: aquecimento ───────────────────────────────
    if minute < MIN_MINUTE_FOR_ENTRY:
        out["failed_filter"] = f"warmup_minute<{MIN_MINUTE_FOR_ENTRY}"
        return out

    # Escopo + valores
    scope, side, cc, xg, xgot, xa, shots, sot, goals = _scope_aggregate(ms_dict)
    out["scope"], out["scope_side"] = scope, side
    out["details"].update({
        "cc": cc, "xg": round(xg,3), "xgot": round(xgot,3), "xa": round(xa,3),
        "shots": shots, "sot": sot, "goals": goals,
    })

    # ─── Filtro 6: nenhuma das 4 zero ────────────────────────
    if cc <= 0 or xg <= 0 or xgot <= 0 or xa <= 0:
        out["failed_filter"] = "metric_is_zero"
        return out

    # ─── Filtro 2: SOT % >= 30% ──────────────────────────────
    sot_pct = _safe_div(sot, shots)
    out["details"]["sot_pct"] = round(sot_pct, 3)
    if sot_pct < MIN_SOT_PCT:
        out["failed_filter"] = f"sot_pct<{MIN_SOT_PCT}"
        return out

    # ─── Filtro 3: ritmo CC <= 15 min/CC ─────────────────────
    cc_rate = _safe_div(minute, cc)
    out["details"]["cc_rate"] = round(cc_rate, 2)
    if cc_rate > MAX_CC_RATE:
        out["failed_filter"] = f"cc_rate>{MAX_CC_RATE}"
        return out

    # ─── Filtro 4: ritmo finalizações <= 3.5 ─────────────────
    shot_rate = _safe_div(minute, shots)
    out["details"]["shot_rate"] = round(shot_rate, 2)
    if shot_rate > MAX_SHOT_RATE:
        out["failed_filter"] = f"shot_rate>{MAX_SHOT_RATE}"
        return out

    # ─── Filtro 5: SOT absoluto projetado >= 9 ───────────────
    sot_projected = sot * (GAME_TOTAL_MINUTES / minute)
    out["details"]["sot_projected"] = round(sot_projected, 1)
    if sot_projected < MIN_SOT_ABSOLUTE_PROJECTED:
        out["failed_filter"] = f"sot_projected<{MIN_SOT_ABSOLUTE_PROJECTED}"
        return out

    # ─── Score ponderado ─────────────────────────────────────
    n_cc   = _normalize_cc_rate(cc_rate)
    n_xgot = _normalize_xgot(xgot, goals)
    n_xg   = _normalize_xg(xg, goals)
    n_xa   = _normalize_xa(xa)
    score = (n_cc * W_CC) + (n_xgot * W_XGOT) + (n_xg * W_XG) + (n_xa * W_XA)
    score = round(score, 2)
    out["details"]["score_components"] = {
        "cc_norm": round(n_cc,1), "xgot_norm": round(n_xgot,1),
        "xg_norm": round(n_xg,1), "xa_norm": round(n_xa,1),
    }

    # Tier
    if score >= THRESHOLD_PREMIUM:   tier = "PREMIUM"
    elif score >= THRESHOLD_FORTE:   tier = "FORTE"
    elif score >= THRESHOLD_WATCH:   tier = "WATCH"
    else:                            tier = None

    out["passed_filters"] = True
    out["score"] = score
    out["tier"] = tier
    return out
