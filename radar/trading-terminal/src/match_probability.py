"""
MATCH_PROBABILITY — Probabilidade real do evento via Poisson.

Modelo:
  - Estima xG remaining (= xG/minuto × minutos restantes × ajuste cenário)
  - Aplica distribuição Poisson independente pra home/away
  - Soma probabilidades de placares finais que levam ao evento desejado

Saída inclui:
  - P(home vence) | P(empate) | P(away vence)
  - P(time alvo vence) = probabilidade real
  - fair_odd = 1 / P
  - min_recommended_odd = fair_odd × margem (8% — proteção contra erro de modelo)

Função PURA. Não depende de Telegram, disco, scraper.
"""
import math

__version__ = "1.1.0"

GAME_END_MIN = 95
MAX_GOALS_REMAINING = 8     # truncamento da matriz Poisson
SAFETY_MARGIN = 1.08        # min_odd = fair_odd × 1.08 (8% colchão)

# ✨ v4.7 — Cap de probabilidade. Modelo Poisson tende a emitir extremos
# (99%, 1%) quando dados são escassos ou cedo demais. Isso é ilusão
# estatística. Cap em [5%, 95%] preserva mercados de favorito esmagador
# mas evita "garantia" estatística (que não existe em futebol ao vivo).
# Cap aplicado e DEPOIS re-normalizado em grupos mutuamente exclusivos
# pra manter soma = 100% (1X2, OVER+UNDER).
PROB_FLOOR = 0.05
PROB_CEILING = 0.95


def _clamp_prob(p: float) -> float:
    """Restringe probabilidade ao intervalo [PROB_FLOOR, PROB_CEILING]."""
    return max(PROB_FLOOR, min(PROB_CEILING, p))


def _renormalize(probs: list) -> list:
    """Re-normaliza lista de probabilidades pra somar 1.0.
    Usado em grupos mutuamente exclusivos (1X2, Over/Under)."""
    total = sum(probs)
    if total <= 0:
        return probs
    return [p / total for p in probs]


# ─── Fator de competição: ajusta confiança do modelo Poisson ───
# Amistosos têm muito mais variância (substituições, ritmo cai, perdedor relaxa)
# Eliminatórias e Champions são mais determinísticos
def _classify_competition(league_name: str) -> str:
    """Retorna tipo da competição baseado no nome da liga."""
    if not league_name:
        return "outro"
    ln = league_name.lower()
    if "amistos" in ln or "friendly" in ln:
        return "amistoso"
    if any(k in ln for k in ("champions", "europa league", "conference league",
                              "libertadores", "sul-americana", "sudamericana")):
        return "copa_continental"
    if any(k in ln for k in ("eliminatorias", "eliminatórias", "wcq",
                              "world cup qualif", "mundial qualif")):
        return "eliminatoria"
    if any(k in ln for k in ("copa do brasil", "copa do mundo", "world cup",
                              "fa cup", "copa del rey", "dfb pokal")):
        return "copa_nacional"
    return "liga_regular"


# Fator multiplicativo no lambda — amistoso reduz; copa amplia
_COMPETITION_LAMBDA_FACTOR = {
    "amistoso":          0.80,   # alta variância, substituições, relaxam
    "liga_regular":      0.95,
    "copa_nacional":     1.00,
    "copa_continental":  1.00,
    "eliminatoria":      1.00,
    "outro":             0.92,
}


# ─── Ajustes de cenário para xG remaining ───
# Calibração CONSERVADORA: produção tende a regredir à média ao longo do jogo
# (cansaço, mudanças táticas, defesas se ajustam). Fatores moderados.
_SCENARIO_FACTOR = {
    ("pressao_asfixiante", True):    1.05,  # quem pressiona segue, mas modera
    ("pressao_asfixiante", False):   0.75,
    ("administra_vantagem", True):   0.50,  # quem ganha vai diminuir bastante
    ("administra_vantagem", False):  1.10,  # quem perde tenta reagir
    ("jogo_aberto",  True):          1.00,
    ("jogo_aberto",  False):         1.00,
    ("contra_ataque", True):         1.05,
    ("contra_ataque", False):        0.85,
    ("posse_improdutiva", True):     0.75,
    ("posse_improdutiva", False):    1.00,
    ("pressao_sem_qualidade", True): 0.85,
    ("pressao_sem_qualidade", False):1.00,
    ("indef", True):                 1.00,
    ("indef", False):                1.00,
}

# Cap de lambda — produção máxima realista nos minutos restantes
# Evita explosões matemáticas quando time tem ritmo absurdo no início
_LAMBDA_CAP = 1.8


def _poisson_pmf(k: int, lam: float) -> float:
    """P(X=k) com X ~ Poisson(lam)."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return (lam ** k) * math.exp(-lam) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0


def estimate_xg_remaining(xg_so_far: float, minute: int,
                            scenario: dict, side: str,
                            ms_dict: dict = None,
                            league_name: str = "") -> float:
    """Estima xG que esse lado vai produzir nos minutos restantes.

    Ajustes em ordem:
      1. Baseline xG/min × minutos_restantes
      2. Fator cenário (pressão, administração, etc.)
      3. Penalidade "jogo ganho" — líder com diff ≥ 3 + min ≥ 60 reduz 20%
      4. Fator competição — amistoso é mais conservador (× 0.80)
      5. Cap de lambda em 1.8 (regressão à média)
    """
    minute = max(1, int(minute))
    minutes_left = max(0, GAME_END_MIN - minute)
    if minutes_left == 0:
        return 0.0
    if xg_so_far <= 0:
        base = 0.10 * (minutes_left / 45.0)
    else:
        base = (xg_so_far / minute) * minutes_left

    # 2. Fator cenário
    sc = scenario.get("scenario", "indef")
    sc_side = scenario.get("side")
    is_dominant = (sc_side == side)
    factor = _SCENARIO_FACTOR.get((sc, is_dominant), 1.0)

    # 3. Penalidade "jogo ganho" — líder em vitória larga + 2º tempo
    if ms_dict:
        h_g = int(ms_dict.get("home_score", 0) or 0)
        a_g = int(ms_dict.get("away_score", 0) or 0)
        diff = h_g - a_g
        is_leader = (side == "home" and diff >= 3) or (side == "away" and diff <= -3)
        if is_leader and minute >= 60:
            # Substituições + ritmo cai mesmo continuando criando no curto prazo
            factor *= 0.80

    # 4. Fator competição
    comp_type = _classify_competition(league_name)
    factor *= _COMPETITION_LAMBDA_FACTOR.get(comp_type, 1.0)

    # 5. Cap
    result = max(0.05, base * factor)
    return min(_LAMBDA_CAP, result)


def compute_all_markets(ms_dict: dict, scenario: dict,
                          league_name: str = "") -> dict:
    """Calcula probabilidades de TODOS os mercados relevantes.

    Mercados:
      - Vencedor: P(home/empate/away)
      - Total: OVER 1.5, 2.5, 3.5 / UNDER 2.5
      - Both Teams to Score (BTS)
      - Próximo gol: P(home), P(away), P(nenhum)
      - Resultado intermediário no fim (placar provável)

    Retorna probabilidades em % + fair odd por mercado.
    """
    minute = int(ms_dict.get("minute", 0) or 0)
    h_g = int(ms_dict.get("home_score", 0) or 0)
    a_g = int(ms_dict.get("away_score", 0) or 0)
    h_xg = float(ms_dict.get("home_xg", 0.0) or 0.0)
    a_xg = float(ms_dict.get("away_xg", 0.0) or 0.0)
    total_g = h_g + a_g

    lam_h = estimate_xg_remaining(h_xg, minute, scenario, "home",
                                     ms_dict=ms_dict, league_name=league_name)
    lam_a = estimate_xg_remaining(a_xg, minute, scenario, "away",
                                     ms_dict=ms_dict, league_name=league_name)

    p_h = [_poisson_pmf(k, lam_h) for k in range(MAX_GOALS_REMAINING + 1)]
    p_a = [_poisson_pmf(k, lam_a) for k in range(MAX_GOALS_REMAINING + 1)]

    # Distribuição completa
    p_home_win = p_draw = p_away_win = 0.0
    p_total = {n: 0.0 for n in range(MAX_GOALS_REMAINING * 2 + 1)}
    p_bts_yes = 0.0

    for h_extra in range(MAX_GOALS_REMAINING + 1):
        for a_extra in range(MAX_GOALS_REMAINING + 1):
            p = p_h[h_extra] * p_a[a_extra]
            final_h = h_g + h_extra
            final_a = a_g + a_extra
            tot = final_h + final_a
            if final_h > final_a:    p_home_win += p
            elif final_h == final_a: p_draw += p
            else:                    p_away_win += p
            if tot <= MAX_GOALS_REMAINING * 2:
                p_total[tot] += p
            if final_h >= 1 and final_a >= 1:
                p_bts_yes += p

    # Normaliza vencedor
    total_w = p_home_win + p_draw + p_away_win
    if total_w > 0:
        p_home_win /= total_w; p_draw /= total_w; p_away_win /= total_w

    # OVER/UNDER (sobre TOTAL FINAL — não só remaining)
    p_over_15 = sum(v for k, v in p_total.items() if k >= 2)
    p_over_25 = sum(v for k, v in p_total.items() if k >= 3)
    p_over_35 = sum(v for k, v in p_total.items() if k >= 4)
    p_under_25 = 1 - p_over_25
    p_under_15 = 1 - p_over_15

    # NEXT GOAL — assumindo independência
    lam_sum = lam_h + lam_a
    if lam_sum > 0:
        p_next_h = lam_h / lam_sum
        p_next_a = lam_a / lam_sum
        p_no_goal = math.exp(-lam_sum)
        p_next_h *= (1 - p_no_goal)
        p_next_a *= (1 - p_no_goal)
    else:
        p_next_h = p_next_a = 0
        p_no_goal = 1.0

    # ✨ HANDICAP ASIÁTICO — quem está na frente "dá" handicap
    # side='home', line=3.5 → home vence final por > 3.5 (4+)
    # Útil quando líder ainda cria e mercado tem prêmio (odd "BACK" zerada)
    def _hcp(side: str, line: float) -> float:
        total = 0.0
        for h in range(MAX_GOALS_REMAINING + 1):
            for a in range(MAX_GOALS_REMAINING + 1):
                final_h = h_g + h
                final_a = a_g + a
                diff = (final_h - final_a) if side == "home" else (final_a - final_h)
                if diff > line:
                    total += p_h[h] * p_a[a]
        return total

    # Handicaps padrão: -0.5, -1.5, -2.5, -3.5, -4.5
    p_hcp_h = {ln: _hcp("home", ln) for ln in (0.5, 1.5, 2.5, 3.5, 4.5)}
    p_hcp_a = {ln: _hcp("away", ln) for ln in (0.5, 1.5, 2.5, 3.5, 4.5)}

    def _to_odd(p):
        return round(1.0 / p, 2) if p > 0 else 99.0

    # ✨ v4.7 — Aplica cap [5%, 95%] e RE-NORMALIZA grupos mutuamente exclusivos.
    # Mantém coerência matemática (1X2 soma 100%, Over+Under soma 100%, etc.)
    # 1X2 (vencedor) — re-normaliza após clamp
    p_home_win, p_draw, p_away_win = _renormalize(
        [_clamp_prob(p_home_win), _clamp_prob(p_draw), _clamp_prob(p_away_win)])
    # Over/Under 2.5 — par mutuamente exclusivo, re-normaliza
    p_over_25, p_under_25 = _renormalize(
        [_clamp_prob(p_over_25), _clamp_prob(p_under_25)])
    # Over/Under 1.5 — mesma lógica
    p_over_15, p_under_15 = _renormalize(
        [_clamp_prob(p_over_15), _clamp_prob(p_under_15)])
    # Over 3.5 não tem complementar único — só cap (não re-normaliza)
    p_over_35 = _clamp_prob(p_over_35)
    # BTS — par binário sim/não, só cap (p_bts_no é derivado depois)
    p_bts_yes = _clamp_prob(p_bts_yes)
    # Next goal — 3 estados (home, away, sem gol). Re-normaliza os 3.
    _no_goal_remain = max(0.0, 1.0 - p_next_h - p_next_a)
    p_next_h, p_next_a, _no_goal_remain = _renormalize(
        [_clamp_prob(p_next_h), _clamp_prob(p_next_a),
         _clamp_prob(_no_goal_remain)])
    # Handicaps — eventos não-exclusivos entre si, só cap individual
    p_hcp_h = {k: _clamp_prob(v) for k, v in p_hcp_h.items()}
    p_hcp_a = {k: _clamp_prob(v) for k, v in p_hcp_a.items()}

    comp_type = _classify_competition(league_name)
    return {
        "schema_version": __version__,
        "minute": minute,
        "score": f"{h_g}-{a_g}",
        "competition_type": comp_type,
        "league_name": league_name,
        "lambda_home": round(lam_h, 2),
        "lambda_away": round(lam_a, 2),
        "minutes_left": max(0, GAME_END_MIN - minute),
        # Vencedor
        "p_home":  round(p_home_win * 100, 1),
        "p_draw":  round(p_draw     * 100, 1),
        "p_away":  round(p_away_win * 100, 1),
        "fair_home": _to_odd(p_home_win),
        "fair_draw": _to_odd(p_draw),
        "fair_away": _to_odd(p_away_win),
        # Over/Under
        "p_over_15":  round(p_over_15  * 100, 1),
        "p_over_25":  round(p_over_25  * 100, 1),
        "p_over_35":  round(p_over_35  * 100, 1),
        "p_under_15": round(p_under_15 * 100, 1),
        "p_under_25": round(p_under_25 * 100, 1),
        "fair_over_25":  _to_odd(p_over_25),
        "fair_under_25": _to_odd(p_under_25),
        "fair_over_15":  _to_odd(p_over_15),
        "fair_over_35":  _to_odd(p_over_35),
        # BTS
        "p_bts_yes": round(p_bts_yes * 100, 1),
        "p_bts_no":  round((1 - p_bts_yes) * 100, 1),
        "fair_bts_yes": _to_odd(p_bts_yes),
        "fair_bts_no":  _to_odd(1 - p_bts_yes),
        # Next goal
        "p_next_home": round(p_next_h * 100, 1),
        "p_next_away": round(p_next_a * 100, 1),
        "p_no_more_goal": round(p_no_goal * 100, 1),
        "fair_next_home": _to_odd(p_next_h),
        "fair_next_away": _to_odd(p_next_a),
        # Handicap home (Espanha vence por X+1 gols ou mais)
        "p_hcp_home_05": round(p_hcp_h[0.5] * 100, 1),
        "p_hcp_home_15": round(p_hcp_h[1.5] * 100, 1),
        "p_hcp_home_25": round(p_hcp_h[2.5] * 100, 1),
        "p_hcp_home_35": round(p_hcp_h[3.5] * 100, 1),
        "p_hcp_home_45": round(p_hcp_h[4.5] * 100, 1),
        "fair_hcp_home_05": _to_odd(p_hcp_h[0.5]),
        "fair_hcp_home_15": _to_odd(p_hcp_h[1.5]),
        "fair_hcp_home_25": _to_odd(p_hcp_h[2.5]),
        "fair_hcp_home_35": _to_odd(p_hcp_h[3.5]),
        "fair_hcp_home_45": _to_odd(p_hcp_h[4.5]),
        # Handicap away
        "p_hcp_away_05": round(p_hcp_a[0.5] * 100, 1),
        "p_hcp_away_15": round(p_hcp_a[1.5] * 100, 1),
        "p_hcp_away_25": round(p_hcp_a[2.5] * 100, 1),
        "p_hcp_away_35": round(p_hcp_a[3.5] * 100, 1),
        "p_hcp_away_45": round(p_hcp_a[4.5] * 100, 1),
        "fair_hcp_away_05": _to_odd(p_hcp_a[0.5]),
        "fair_hcp_away_15": _to_odd(p_hcp_a[1.5]),
        "fair_hcp_away_25": _to_odd(p_hcp_a[2.5]),
        "fair_hcp_away_35": _to_odd(p_hcp_a[3.5]),
        "fair_hcp_away_45": _to_odd(p_hcp_a[4.5]),
    }


def compute_event_probability(ms_dict: dict, scenario: dict,
                                target_side: str,
                                league_name: str = "") -> dict:
    """Calcula probabilidade do TARGET_SIDE ganhar o jogo.

    Args:
      ms_dict: estado atual (placar acumulado, xG acumulado, minute)
      scenario: dict retornado por detect_scenario
      target_side: "home" ou "away" — quem queremos que ganhe

    Returns:
      {
        prob_home_win, prob_draw, prob_away_win,
        prob_target,
        fair_odd, min_recommended_odd,
        lambda_home, lambda_away,
        minutes_left,
      }
    """
    minute = int(ms_dict.get("minute", 0) or 0)
    h_g = int(ms_dict.get("home_score", 0) or 0)
    a_g = int(ms_dict.get("away_score", 0) or 0)
    h_xg = float(ms_dict.get("home_xg", 0.0) or 0.0)
    a_xg = float(ms_dict.get("away_xg", 0.0) or 0.0)

    lam_h = estimate_xg_remaining(h_xg, minute, scenario, "home",
                                     ms_dict=ms_dict, league_name=league_name)
    lam_a = estimate_xg_remaining(a_xg, minute, scenario, "away",
                                     ms_dict=ms_dict, league_name=league_name)
    minutes_left = max(0, GAME_END_MIN - minute)

    # Matriz Poisson independente truncada em MAX_GOALS_REMAINING
    p_h_win = 0.0
    p_draw = 0.0
    p_a_win = 0.0
    p_h_cache = [_poisson_pmf(k, lam_h) for k in range(MAX_GOALS_REMAINING + 1)]
    p_a_cache = [_poisson_pmf(k, lam_a) for k in range(MAX_GOALS_REMAINING + 1)]

    for h_extra in range(MAX_GOALS_REMAINING + 1):
        for a_extra in range(MAX_GOALS_REMAINING + 1):
            p = p_h_cache[h_extra] * p_a_cache[a_extra]
            final_h = h_g + h_extra
            final_a = a_g + a_extra
            if final_h > final_a:
                p_h_win += p
            elif final_h == final_a:
                p_draw += p
            else:
                p_a_win += p

    # Normaliza (truncamento pode somar <1)
    total = p_h_win + p_draw + p_a_win
    if total > 0:
        p_h_win /= total
        p_draw /= total
        p_a_win /= total

    prob_target = p_h_win if target_side == "home" else p_a_win
    fair_odd = (1.0 / prob_target) if prob_target > 0 else 999.0
    min_odd = fair_odd * SAFETY_MARGIN

    return {
        "schema_version": __version__,
        "minute": minute,
        "score": f"{h_g}-{a_g}",
        "target_side": target_side,
        "prob_home_win": round(p_h_win * 100, 1),     # em %
        "prob_draw":     round(p_draw  * 100, 1),
        "prob_away_win": round(p_a_win * 100, 1),
        "prob_target":   round(prob_target * 100, 1),
        "fair_odd":      round(fair_odd, 2),
        "min_recommended_odd": round(min_odd, 2),
        "lambda_home":   round(lam_h, 2),
        "lambda_away":   round(lam_a, 2),
        "minutes_left":  minutes_left,
    }
