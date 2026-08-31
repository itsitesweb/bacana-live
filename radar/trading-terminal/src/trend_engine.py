"""
TREND_ENGINE — Detecta TENDÊNCIA tática e recomenda MERCADO correto.

Filosofia (trader profissional):
  Não basta olhar quem domina agora. Tem que ler como o jogo TENDE a evoluir
  baseado em padrões consagrados do futebol:

  - Perdedor que precisa virar → se lança → abre espaços → contra-ataques
    → MAIS GOLS → OVER 2.5 ou BTS
  - Líder com 2+ gols min 60+ → administra → ritmo cai → UNDER tardio
  - Empate min 75+ → desespero ofensivo → NEXT GOAL ou OVER
  - Time pressionando empate → vai marcar → BACK valor

Cada tendência:
  - Vem com um MERCADO sugerido (não só BACK time)
  - Tem nível de confiança baseado em quantos sinais batem
  - Pode ser VALIDADA com dados dos próximos blocos

Função pura. Lê estado + cenário + histórico, retorna tese estruturada.
"""
__version__ = "1.0.0"


# ─── Catálogo de mercados ───
MARKET_BACK_HOME       = "BACK_HOME"
MARKET_BACK_AWAY       = "BACK_AWAY"
MARKET_LAY_HOME        = "LAY_HOME"
MARKET_LAY_AWAY        = "LAY_AWAY"
MARKET_OVER_25         = "OVER_2_5"
MARKET_OVER_35         = "OVER_3_5"
MARKET_UNDER_25        = "UNDER_2_5"
MARKET_BTS_YES         = "BTS_SIM"
MARKET_BTS_NO          = "BTS_NAO"
MARKET_NEXT_GOAL_HOME  = "NEXT_GOAL_HOME"
MARKET_NEXT_GOAL_AWAY  = "NEXT_GOAL_AWAY"
# Handicap (líder vence por mais)
MARKET_HCP_HOME_15 = "HCP_HOME_-1.5"
MARKET_HCP_HOME_25 = "HCP_HOME_-2.5"
MARKET_HCP_HOME_35 = "HCP_HOME_-3.5"
MARKET_HCP_HOME_45 = "HCP_HOME_-4.5"
MARKET_HCP_AWAY_15 = "HCP_AWAY_-1.5"
MARKET_HCP_AWAY_25 = "HCP_AWAY_-2.5"
MARKET_HCP_AWAY_35 = "HCP_AWAY_-3.5"
MARKET_HCP_AWAY_45 = "HCP_AWAY_-4.5"


# ─── Padrões de tendência ───
TREND_BUSCA_EMPATE          = "BUSCA_EMPATE"
TREND_BUSCA_VIRADA          = "BUSCA_VIRADA"
TREND_ADMINISTRACAO_TOTAL   = "ADMINISTRACAO_TOTAL"
TREND_PRESSAO_PRE_GOL       = "PRESSAO_PRE_GOL"
TREND_LIDER_BUSCA_MAIS      = "LIDER_BUSCA_MAIS_GOLS"
TREND_PERDEDOR_REAGINDO     = "PERDEDOR_REAGINDO"
TREND_CONTRA_ATAQUE_ABERTO  = "CONTRA_ATAQUE_ABERTO"
TREND_FINAL_DESESPERO       = "FINAL_DESESPERO"
TREND_JOGO_FECHADO          = "JOGO_FECHADO"
TREND_INDEF                 = "INDEF"


def _detect_loser_reacting(ms_dict: dict, block_data: dict = None):
    """Detecta se o perdedor REAGIU no bloco atual.

    Sinais de reação:
      - Perdedor marcou no bloco
      - xGOT do perdedor no bloco >= xGOT do líder no bloco (e >= 0.4)
      - xG do perdedor no bloco >= xG do líder no bloco (e >= 0.5)

    Returns (is_reacting: bool, loser_side: str, signals: list[str])
    """
    h_g = int(ms_dict.get("home_score", 0) or 0)
    a_g = int(ms_dict.get("away_score", 0) or 0)
    diff = h_g - a_g
    if diff == 0:
        return False, None, []
    loser_side = "away" if diff > 0 else "home"
    leader_side = "home" if diff > 0 else "away"

    signals = []
    # Block data exists?
    if block_data:
        l_g_block = block_data.get(f"{loser_side}_score_block", 0)
        ld_g_block = block_data.get(f"{leader_side}_score_block", 0)
        l_xg_block = block_data.get(f"{loser_side}_xg", 0)
        ld_xg_block = block_data.get(f"{leader_side}_xg", 0)
        l_xgot_block = block_data.get(f"{loser_side}_xgot", 0)
        ld_xgot_block = block_data.get(f"{leader_side}_xgot", 0)

        if l_g_block >= 1:
            signals.append(
                f"{loser_side} marcou {l_g_block} gol(s) no bloco")
        if l_xgot_block >= 0.4 and l_xgot_block > ld_xgot_block:
            signals.append(
                f"{loser_side} xGOT bloco {l_xgot_block:.2f} > líder {ld_xgot_block:.2f}")
        if l_xg_block >= 0.5 and l_xg_block > ld_xg_block:
            signals.append(
                f"{loser_side} xG bloco {l_xg_block:.2f} > líder {ld_xg_block:.2f}")

        is_reacting = len(signals) >= 1
        return is_reacting, loser_side, signals
    return False, loser_side, []


def detect_trend(ms_dict: dict, ctx: dict, scenario: dict,
                  score_history: list = None,
                  block_data: dict = None) -> dict:
    """Detecta a tendência tática dominante + sugere mercado.

    Args:
      ms_dict: estado (placar acumulado, xG, minute, ...)
      ctx: contexto (posse, toques área, ...)
      scenario: dict de detect_scenario
      score_history: lista de scores Quádrupla por bloco (opcional)

    Returns dict:
      {
        trend: TREND_*,
        market: MARKET_*,
        side: "home"|"away"|None,
        confidence: "alta"|"média"|"baixa",
        reasoning: list[str],
        narrative: str (1-2 frases que explicam a tese),
        validation_signals: list[str] (o que esperar pra confirmar),
        invalidation_signals: list[str] (o que invalida)
      }
    """
    minute = int(ms_dict.get("minute", 0) or 0)
    h_g = int(ms_dict.get("home_score", 0) or 0)
    a_g = int(ms_dict.get("away_score", 0) or 0)
    diff = h_g - a_g
    abs_diff = abs(diff)
    total_g = h_g + a_g

    h_xg = float(ms_dict.get("home_xg", 0.0) or 0.0)
    a_xg = float(ms_dict.get("away_xg", 0.0) or 0.0)
    h_cc = int(ms_dict.get("home_cc", 0) or 0)
    a_cc = int(ms_dict.get("away_cc", 0) or 0)

    posse_h, posse_a = ctx.get("posse", (50, 50))
    toq_h, toq_a = ctx.get("toques_area", (0, 0))

    sc = scenario.get("scenario", "indef")
    sc_side = scenario.get("side")

    reasoning = []

    # ═══════════════════════════════════════════════════
    # ✨ TREND 0 (prioridade): PERDEDOR REAGINDO
    # → Perdedor marcou no bloco OU produziu mais que líder no bloco
    # → Cenário inverte: NEXT GOAL perdedor + OVER ainda mais
    # ═══════════════════════════════════════════════════
    is_reacting, loser_side, reaction_signals = _detect_loser_reacting(
        ms_dict, block_data)
    if is_reacting and abs_diff >= 1 and minute >= 30:
        loser_name = (ms_dict.get("home") if loser_side == "home"
                       else ms_dict.get("away")) or loser_side
        for s in reaction_signals:
            reasoning.append(s)
        reasoning.append(f"Placar {h_g}-{a_g} min {minute} — perdedor reagindo")

        # Mercado: NEXT GOAL perdedor (próxima bola é dele); OVER se total ≤ 4
        if total_g <= 4:
            market = (MARKET_NEXT_GOAL_HOME if loser_side == "home"
                      else MARKET_NEXT_GOAL_AWAY)
            mlabel = f"NEXT GOAL {loser_name} + OVER {(total_g + 1.5):.1f}"
        else:
            market = (MARKET_NEXT_GOAL_HOME if loser_side == "home"
                      else MARKET_NEXT_GOAL_AWAY)
            mlabel = f"NEXT GOAL {loser_name}"

        return {
            "trend": TREND_PERDEDOR_REAGINDO,
            "market": market,
            "market_label": mlabel,
            "side": loser_side,
            "confidence": "média",
            "reasoning": reasoning,
            "narrative": (
                f"{loser_name} reagiu no último bloco — produziu mais que o "
                f"líder, marcou ou criou xGOT superior. Jogo se abriu. "
                f"Líder relaxou (tipico em jogo controlado) e perdedor sentiu "
                f"o cheiro de virada/empate. Próximo gol mais provável do "
                f"{loser_name}."
            ),
            "validation_signals": [
                f"Próximo bloco: {loser_name} mantém xG > 0.3",
                "Líder não responde com mais um gol rápido",
                "Substituições ofensivas do perdedor",
            ],
            "invalidation_signals": [
                "Líder marca rapidamente após",
                f"{loser_name} para de criar (xG bloco volta a < 0.2)",
                "Cartão vermelho do perdedor",
            ],
        }

    # ═══════════════════════════════════════════════════
    # TREND 1: BUSCA EMPATE / VIRADA (time atrás, vai se lançar)
    # → Perdedor precisa atacar → abre espaços → contra-ataques
    # → OVER 2.5 ou BTS
    # ═══════════════════════════════════════════════════
    if abs_diff >= 1 and minute >= 30:
        loser_side = "away" if diff > 0 else "home"
        leader_side = "home" if diff > 0 else "away"
        loser_g = a_g if loser_side == "away" else h_g
        leader_g = h_g if leader_side == "home" else a_g

        # Já tem total de gols suficiente pra OVER?
        # Cenário 1A: placar 0-2, 0-1, 1-2, 1-3 → busca virada com OVER risk
        # NOTE: se perdedor está reagindo, estende janela (já tratado no TREND 0
        # acima, que retorna antes desse bloco)
        is_buscando = (
            (abs_diff == 1) or
            (abs_diff == 2 and minute <= 65)
        )

        if is_buscando:
            reasoning.append(
                f"Placar {h_g}-{a_g} no min {minute} — perdedor precisa atacar"
            )
            # Tendência: jogo abre, mais gols
            confidence = "média"
            if abs_diff == 1:
                confidence = "alta"
                trend_name = TREND_BUSCA_EMPATE
                narrative = (
                    f"Perdedor precisa atacar pra empatar — vai expor a "
                    f"defesa. Líder responde nos contra-ataques. "
                    f"Tendência forte de mais gols."
                )
            else:
                trend_name = TREND_BUSCA_VIRADA
                narrative = (
                    f"Perdedor precisa virar 2 gols — vai se lançar com "
                    f"tudo. Defesa exposta = contra-ataque do líder = gol."
                )

            # Mercado: se total atual ≥ 1, OVER 2.5 é o trade; se já tem 3+ → OVER 3.5
            if total_g >= 3:
                market = MARKET_OVER_35
                market_label = "OVER 3.5"
            elif total_g >= 2:
                market = MARKET_OVER_25
                market_label = "OVER 2.5"
            else:
                market = MARKET_OVER_25
                market_label = "OVER 2.5"

            return {
                "trend": trend_name,
                "market": market,
                "market_label": market_label,
                "side": None,  # sobre o jogo, não sobre um time
                "confidence": confidence,
                "reasoning": reasoning,
                "narrative": narrative,
                "validation_signals": [
                    f"Próximo bloco: xG do perdedor sobe (>{loser_g + 0.4:.1f})",
                    f"Próximo bloco: finalizações totais do bloco >= 5",
                    f"Bloco: ratio toques área aproxima 50/50 (perdedor sai)",
                ],
                "invalidation_signals": [
                    f"Perdedor não aumenta xG do bloco",
                    f"Líder marca novo gol (mata o jogo)",
                    f"Min 75+ sem gol novo (mercado já precificou)",
                ],
            }

    # ═══════════════════════════════════════════════════
    # TREND ✨: LÍDER BUSCA MAIS GOLS (líder ainda cria com qualidade)
    # → Time líder por 2+ continua produzindo no bloco (xG/xGOT alto)
    # → BACK time tem odd morta MAS HANDICAP -X.5 tem prêmio
    # ═══════════════════════════════════════════════════
    if abs_diff >= 2 and 30 <= minute <= 75:
        leader_side = "home" if diff > 0 else "away"
        leader_xg = h_xg if leader_side == "home" else a_xg
        leader_cc = h_cc if leader_side == "home" else a_cc
        leader_posse = posse_h if leader_side == "home" else posse_a
        leader_toq = toq_h if leader_side == "home" else toq_a
        # Líder ainda CRIA: posse alta + toques área + chances claras
        # (xG cumulativo é alto, mas precisamos garantir que o ritmo NÃO caiu)
        if (leader_posse >= 55 and leader_toq >= 10 and
            leader_xg >= 1.0 and leader_cc >= 2 and
            sc in ("pressao_asfixiante", "contra_ataque", "jogo_aberto")):
            reasoning.append(
                f"Líder vence {h_g}-{a_g} mas continua criando: "
                f"xG {leader_xg:.2f}, {leader_cc} CC, posse {leader_posse:.0f}%"
            )
            # Escolhe handicap baseado no diff atual
            # diff=2 → handicap -2.5 (mais 1 gol)
            # diff=3 → handicap -3.5 (mais 1 gol)
            # diff=4 → handicap -4.5 (mais 1 gol)
            target_hcp = abs_diff + 0.5
            if leader_side == "home":
                market_key = f"HCP_HOME_-{target_hcp}"
            else:
                market_key = f"HCP_AWAY_-{target_hcp}"
            leader_name = (ms_dict.get("home") if leader_side == "home"
                            else ms_dict.get("away")) or leader_side

            return {
                "trend": TREND_LIDER_BUSCA_MAIS,
                "market": market_key,
                "market_label": f"HANDICAP -{target_hcp} {leader_name}",
                "side": leader_side,
                "confidence": "média",
                "reasoning": reasoning,
                "narrative": (
                    f"{leader_name} venceria com vantagem maior se mantiver "
                    f"ritmo. Mercado já cravou {leader_name} como vencedor — "
                    f"BACK não paga. HANDICAP -{target_hcp} tem prêmio porque "
                    f"depende da {leader_name} marcar mais."
                ),
                "validation_signals": [
                    f"Próximo bloco: xG {leader_name} continua >= 0.5",
                    f"Próximo bloco: pelo menos 1 finalização perigosa",
                    "Adversário sem reação ofensiva clara",
                ],
                "invalidation_signals": [
                    f"{leader_name} desacelera (substituições defensivas)",
                    "Cartão vermelho do lado líder",
                    "Adversário marca (sobe pressão psicológica)",
                ],
            }

    # ═══════════════════════════════════════════════════
    # TREND 2: ADMINISTRAÇÃO TOTAL (líder fecha jogo)
    # → Quem ganha controla, perdedor desistiu → placar mantém
    # → UNDER ou nenhum trade
    # ═══════════════════════════════════════════════════
    if abs_diff >= 2 and minute >= 65 and sc == "administra_vantagem":
        reasoning.append(
            f"Diff {abs_diff} no min {minute} — líder administra confortável"
        )
        # Perdedor não está reagindo?
        loser_xg = a_xg if diff > 0 else h_xg
        if loser_xg < 0.6:
            reasoning.append(f"Perdedor sem reação (xG {loser_xg:.2f})")
            return {
                "trend": TREND_ADMINISTRACAO_TOTAL,
                "market": MARKET_UNDER_25 if total_g <= 2 else None,
                "market_label": "UNDER 2.5" if total_g <= 2 else "Sem entrada",
                "side": None,
                "confidence": "alta",
                "reasoning": reasoning,
                "narrative": (
                    f"Líder controla o jogo, perdedor desistiu. Ritmo "
                    f"caiu. Placar tende a manter até o final."
                ),
                "validation_signals": [
                    "Próximo bloco: <3 finalizações totais",
                    "Perdedor xG bloco < 0.3",
                ],
                "invalidation_signals": [
                    "Perdedor marca → cenário muda",
                    "Cartão vermelho → cenário muda",
                    "Substituição ofensiva tardia",
                ],
            }

    # ═══════════════════════════════════════════════════
    # TREND 3: PRESSÃO PRÉ-GOL (mesma lógica do pressao_vendavel)
    # → Time pressionando empate ou atrás 1, com qualidade
    # → BACK time
    # ═══════════════════════════════════════════════════
    if 25 <= minute <= 70 and sc == "pressao_asfixiante" and sc_side:
        # candidate é o lado dominante
        cand_diff = (h_g - a_g) if sc_side == "home" else (a_g - h_g)
        cand_xg = h_xg if sc_side == "home" else a_xg
        if cand_diff <= 0 and cand_diff >= -1 and cand_xg >= 1.0:
            team_atual_diff = "empate" if cand_diff == 0 else "perdendo 1"
            reasoning.append(
                f"Pressão asfixiante do {sc_side} com {team_atual_diff}"
            )
            return {
                "trend": TREND_PRESSAO_PRE_GOL,
                "market": MARKET_BACK_HOME if sc_side == "home" else MARKET_BACK_AWAY,
                "market_label": f"BACK {ms_dict.get(sc_side, sc_side)}",
                "side": sc_side,
                "confidence": "alta",
                "reasoning": reasoning,
                "narrative": (
                    f"Lado dominante pressiona empatado/atrás. Mercado "
                    f"ainda tem prêmio — gol vindo despenca a odd."
                ),
                "validation_signals": [
                    "Próximo bloco: xGOT do lado continua subindo",
                    "Adversário continua sem produzir",
                ],
                "invalidation_signals": [
                    "Adversário acorda (xG do bloco > 0.5)",
                    "Cenário muda pra pressão sem qualidade",
                ],
            }

    # ═══════════════════════════════════════════════════
    # TREND 4: CONTRA-ATAQUE ABERTO (líder responde no espaço)
    # → Líder tem xG crescendo mesmo com posse baixa
    # → OVER 2.5 ou Next Goal pro líder
    # ═══════════════════════════════════════════════════
    if sc == "contra_ataque" and sc_side and minute >= 30:
        reasoning.append(
            f"Cenário contra-ataque pro {sc_side} — espaço pros gols"
        )
        market = MARKET_OVER_25 if total_g >= 1 else MARKET_NEXT_GOAL_HOME
        if sc_side == "away":
            market_next = MARKET_NEXT_GOAL_AWAY
        else:
            market_next = MARKET_NEXT_GOAL_HOME
        return {
            "trend": TREND_CONTRA_ATAQUE_ABERTO,
            "market": MARKET_OVER_25,
            "market_label": "OVER 2.5 + NEXT GOAL " + sc_side.upper(),
            "side": sc_side,
            "confidence": "média",
            "reasoning": reasoning,
            "narrative": (
                f"Contra-ataque encaixado. Adversário se expõe atacando, "
                f"líder responde com perigo real. Sai gol logo."
            ),
            "validation_signals": [
                "Próximo bloco: xG do lado contra-atacante sobe",
                "Bloco com pelo menos 1 finalização perigosa",
            ],
            "invalidation_signals": [
                "Adversário recua e fecha contra-ataque",
                "Substituição defensiva mata espaço",
            ],
        }

    # ═══════════════════════════════════════════════════
    # TREND 5: FINAL DESESPERO (empate/diff 1 min 75+)
    # → Tempo curto + necessidade → trocas tudo por gol
    # → NEXT GOAL ou OVER tardio
    # ═══════════════════════════════════════════════════
    if minute >= 75 and abs_diff <= 1:
        reasoning.append(f"Min {minute}, diff {abs_diff} — final aberto")
        market = MARKET_OVER_25 if total_g >= 1 else MARKET_OVER_15
        market_label = "OVER 2.5" if total_g >= 1 else "OVER 1.5"
        return {
            "trend": TREND_FINAL_DESESPERO,
            "market": market,
            "market_label": market_label,
            "side": None,
            "confidence": "média",
            "reasoning": reasoning,
            "narrative": (
                f"Final do jogo aberto. Times trocam segurança por "
                f"vitória/empate. Janela curta de gols rápidos."
            ),
            "validation_signals": [
                "Substituições ofensivas dos 2 lados",
                "Cartões amarelos sobem (jogo abre)",
            ],
            "invalidation_signals": [
                "Min 85+ sem gol e ritmo cai",
            ],
        }

    # ═══════════════════════════════════════════════════
    # TREND 6: JOGO FECHADO (empate min 60+ com posse improdutiva + volume baixo)
    # → Ninguém quer arriscar → UNDER
    # ═══════════════════════════════════════════════════
    # ✨ v4.7 — Threshold rigoroso pra evitar UNDER cedo demais.
    # Caso real Timor 0-0 Brunei min 30 disparou UNDER 99% e terminou 3-1.
    # Critérios endurecidos:
    #   - min >= 60 (era 30) — jogos abrem no 2º tempo, esperar
    #   - cenário posse_improdutiva
    #   - total_g == 0
    #   - total_shots <= 6 (volume realmente baixo, não jogo truncado)
    total_shots = ms_dict.get("home_shots", 0) + ms_dict.get("away_shots", 0)
    if (h_g == a_g and minute >= 60 and sc == "posse_improdutiva"
        and total_g == 0 and total_shots <= 6):
        reasoning.append(
            f"Empate 0-0 min {minute} com posse improdutiva e "
            f"volume baixo ({total_shots} fin)"
        )
        return {
            "trend": TREND_JOGO_FECHADO,
            "market": MARKET_UNDER_25,
            "market_label": "UNDER 2.5",
            "side": None,
            "confidence": "média",
            "reasoning": reasoning,
            "narrative": (
                f"Times trocam passes sem chegar na área. Ritmo morno, "
                f"poucos chutes. Tende a terminar 0-0 ou 1-0."
            ),
            "validation_signals": [
                "Próximo bloco: total finalizações <= 4",
                "xG do bloco <= 0.5 dos 2 lados",
            ],
            "invalidation_signals": [
                "Gol abre o jogo",
                "Pressão acumulada vira xG alto",
            ],
        }

    # ═══════════════════════════════════════════════════
    # INDEF — sem padrão claro
    # ═══════════════════════════════════════════════════
    return {
        "trend": TREND_INDEF,
        "market": None,
        "market_label": "Sem entrada",
        "side": None,
        "confidence": "baixa",
        "reasoning": ["sem padrão tático dominante identificado"],
        "narrative": (
            f"Jogo sem cenário tático claro até agora. Aguardar evolução "
            f"dos próximos blocos pra ter tese sólida."
        ),
        "validation_signals": [],
        "invalidation_signals": [],
    }


def validate_trend_against_blocks(trend: dict, current_block: dict,
                                    previous_block: dict = None) -> dict:
    """Verifica se os dados do bloco atual CONFIRMAM ou REFUTAM a tendência.

    Args:
      trend: dict retornado por detect_trend
      current_block: bloco atual (delta)
      previous_block: bloco anterior (delta), opcional

    Returns:
      {
        status: "confirmou"|"em_andamento"|"refutou",
        evidence: list[str] (o que mudou desde o último bloco)
      }
    """
    if not trend or not previous_block:
        return {"status": "em_andamento", "evidence": []}

    evidence = []
    sigs_pos = 0  # contraditas confirmação
    sigs_neg = 0  # contraditas refutação

    tname = trend.get("trend", "")

    # Helpers
    def _delta(metric: str, side: str = None) -> float:
        key = f"{side}_{metric}" if side else metric
        cur = current_block.get(key, 0) or 0
        prev = previous_block.get(key, 0) or 0
        try:
            return float(cur) - float(prev)
        except: return 0.0

    if tname in (TREND_BUSCA_EMPATE, TREND_BUSCA_VIRADA):
        # Perdedor deveria crescer
        side = trend.get("side")
        # tendência diz: "perdedor cresce". Vamos pegar ambos lados
        d_h_xg = _delta("xg", "home")
        d_a_xg = _delta("xg", "away")
        d_total_shots = _delta("shots", "home") + _delta("shots", "away")
        if d_total_shots >= 3:
            evidence.append(f"Volume cresceu: +{d_total_shots:.0f} chutes")
            sigs_pos += 1
        if d_h_xg > 0.3 or d_a_xg > 0.3:
            evidence.append(f"xG do bloco cresceu: home +{d_h_xg:.2f}, away +{d_a_xg:.2f}")
            sigs_pos += 1
        # Refutação: ritmo caindo
        if d_total_shots <= 1:
            evidence.append(f"Volume estagnou: só +{d_total_shots:.0f} chutes")
            sigs_neg += 1

    elif tname == TREND_ADMINISTRACAO_TOTAL:
        # Volume deveria CAIR
        d_total_shots = _delta("shots", "home") + _delta("shots", "away")
        if d_total_shots <= 3:
            evidence.append(f"Volume baixo confirma controle: +{d_total_shots:.0f} chutes")
            sigs_pos += 1
        if d_total_shots >= 6:
            evidence.append(f"Volume cresceu inesperado: +{d_total_shots:.0f} chutes")
            sigs_neg += 1

    elif tname == TREND_PRESSAO_PRE_GOL:
        side = trend.get("side", "home")
        d_xg = _delta("xg", side)
        d_xgot = _delta("xgot", side)
        if d_xg >= 0.4:
            evidence.append(f"xG do {side} cresceu: +{d_xg:.2f}")
            sigs_pos += 1
        if d_xgot >= 0.3:
            evidence.append(f"xGOT do {side} cresceu: +{d_xgot:.2f}")
            sigs_pos += 1
        # Adversário acordando?
        other = "away" if side == "home" else "home"
        d_other_xg = _delta("xg", other)
        if d_other_xg >= 0.4:
            evidence.append(f"⚠️ Adversário acordou: +{d_other_xg:.2f} xG")
            sigs_neg += 1

    # Status final
    if sigs_pos >= 2 and sigs_neg == 0:
        status = "confirmou"
    elif sigs_neg >= 2 and sigs_pos == 0:
        status = "refutou"
    else:
        status = "em_andamento"

    return {"status": status, "evidence": evidence,
            "pos_signals": sigs_pos, "neg_signals": sigs_neg}
