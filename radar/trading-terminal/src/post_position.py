"""
Post-position management — Sections 15, 16 of V1.2.
Checks run in fatal order (stop at first match).
"""
from .models import MatchState, DerivedVars, Decision
from .utils import UNKNOWN_LAST_BC


def manage_position(ms: MatchState, d: DerivedVars, decision: Decision, cfg: dict):
    """Manage existing position. Mutates decision in place."""

    if ms.position_type == "BACK":
        _manage_back(ms, d, decision, cfg)
    elif ms.position_type == "OVER":
        _manage_over(ms, d, decision, cfg)


def _manage_back(ms: MatchState, d: DerivedVars, decision: Decision, cfg: dict):
    """Section 15: Post-Back management — fatal order checks."""

    pc = cfg.get("post_back", {})

    # 1. Red card against backed team
    if d.red_card_against_backed_team:
        decision.recommended_action = "EXIT_BACK"
        decision.blocked_reason = "RED_CARD"  # token interno — formatter traduz
        decision.add_trace("Post-Back: EXIT — red card against backed team")
        return

    # 2. Opponent 3+ CC since entry
    if d.opponent_bc_since_entry >= pc.get("exit_opponent_bc", 3):
        decision.recommended_action = "EXIT_BACK"
        decision.blocked_reason = (
            f"Adversário acumulou {d.opponent_bc_since_entry} big chances desde a entrada "
            f"(limite: {pc.get('exit_opponent_bc', 3)})"
        )
        decision.add_trace(f"Post-Back: EXIT — adv {d.opponent_bc_since_entry} CC")
        return

    # 3. Gap inverted
    if d.gap_bc <= 0:
        decision.recommended_action = "EXIT_BACK"
        decision.blocked_reason = (
            f"Vantagem de big chances inverteu (gap={d.gap_bc}) — adversário equilibrou ou virou"
        )
        decision.add_trace(f"Post-Back: EXIT — gap inverted (gap={d.gap_bc})")
        return

    # 4. Adv 2 CC + Dom stopped
    if (d.opponent_bc_since_entry >= 2
        and d.team_bc_since_entry == 0
        and d.minutes_since_team_last_bc > pc.get("alert_minutes_no_team_bc", 15)):

        decision.recommended_action = "EXIT_BACK"
        decision.blocked_reason = (
            f"Adversário criou {d.opponent_bc_since_entry} chances e dominante parado há "
            f"{d.minutes_since_team_last_bc} min sem big chance"
        )
        decision.add_trace(
            f"Post-Back: EXIT — adv 2+ CC + dom stopped "
            f"(opp={d.opponent_bc_since_entry}, no_bc={d.minutes_since_team_last_bc}min)"
        )
        return

    # 5. Dom no CC for 20+ min and no xGOT
    if (d.minutes_since_team_last_bc > pc.get("reduce_minutes_no_team_bc", 20)
        and d.team_xgot_since_entry == 0):

        decision.recommended_action = "REDUCE_BACK"
        decision.blocked_reason = (
            f"Dominante há {d.minutes_since_team_last_bc} min sem big chance e sem xGOT desde a entrada"
        )
        decision.add_trace(f"Post-Back: REDUCE — no CC {d.minutes_since_team_last_bc}min, no xGOT")
        return

    # 6. Yellow alert
    if (d.minutes_since_team_last_bc > pc.get("alert_minutes_no_team_bc", 15)
        or (d.opponent_bc_since_entry >= 1 and d.team_bc_since_entry == 0)):

        decision.recommended_action = "YELLOW_ALERT_BACK"
        if d.opponent_bc_since_entry >= 1 and d.team_bc_since_entry == 0:
            decision.blocked_reason = (
                f"Adversário criou chance e dominante ainda não respondeu "
                f"({d.minutes_since_team_last_bc} min sem big chance)"
            )
        else:
            decision.blocked_reason = (
                f"Dominante há {d.minutes_since_team_last_bc} min sem big chance — monitorar"
            )
        decision.add_trace(
            f"Post-Back: YELLOW ALERT (no_bc={d.minutes_since_team_last_bc}min, "
            f"opp={d.opponent_bc_since_entry})"
        )
        return

    # 7. Hold
    if (d.team_bc_since_entry >= 1
        and d.minutes_since_team_last_bc <= pc.get("alert_minutes_no_team_bc", 15)
        and d.opponent_bc_since_entry <= 2):

        decision.recommended_action = "HOLD_BACK"
        decision.blocked_reason = "Dominante respondeu — tese viva"
        decision.add_trace("Post-Back: HOLD — dominante respondeu, tese viva")
        return

    # 8. Hold with caution (fallback)
    decision.recommended_action = "HOLD_BACK_WITH_CAUTION"
    decision.blocked_reason = "Sem mudanças significativas — manter com cautela"
    decision.add_trace("Post-Back: HOLD_WITH_CAUTION (fallback)")


def _manage_over(ms: MatchState, d: DerivedVars, decision: Decision, cfg: dict):
    """Section 16: Post-Over management."""

    pc = cfg.get("post_over", {})

    # 1. Over already won
    if d.over_already_won:
        decision.recommended_action = "LOCK_PROFIT"
        decision.blocked_reason = (
            f"Over batido: {d.total_goals} gols acima da linha {ms.target_over_line} — travar lucro"
        )
        decision.add_trace(f"Post-Over: LOCK PROFIT — goals={d.total_goals} > line={ms.target_over_line}")
        return

    # 2. Score killed game
    if d.score_diff >= pc.get("exit_score_diff", 3) and not d.over_already_won:
        decision.recommended_action = "EXIT_OVER"
        decision.blocked_reason = "SCORE_KILLED_GAME"  # token interno — formatter traduz
        decision.add_trace(f"Post-Over: EXIT — score_diff={d.score_diff} >= 3")
        return

    # ─── GUARD: minutos_since_last_match_bc DESCONHECIDO ──────────────
    # Se vier UNKNOWN_LAST_BC (999, sentinela do utils.compute_derived),
    # significa que minute_of_last_match_bc não foi inicializado (state
    # novo / daemon recém-bootado / dado faltando). NÃO disparar EXIT por
    # "ritmo morto" — usar HOLD_WITH_UNKNOWN_BC e logar diagnóstico.
    last_bc_unknown = (d.minutes_since_last_match_bc >= UNKNOWN_LAST_BC)

    # 3. No CC for 20+ min — só dispara se LAST_BC for conhecido
    if (not last_bc_unknown
        and d.minutes_since_last_match_bc >= pc.get("exit_minutes_no_match_bc", 20)):
        decision.recommended_action = "EXIT_OVER"
        decision.blocked_reason = (
            f"Jogo sem big chance há {d.minutes_since_last_match_bc} min — ritmo morreu"
        )
        decision.add_trace(f"Post-Over: EXIT — no CC {d.minutes_since_last_match_bc}min")
        return

    # 4. Bilaterality lost → REDUCE_OVER + evaluate Back transition (Section 16)
    if d.min_bc == 0 and ms.opponent_bc_at_entry >= 1:
        decision.recommended_action = "REDUCE_OVER"
        decision.blocked_reason = "BILATERALITY_LOST"  # token interno — formatter traduz
        decision.add_trace(
            "Post-Over: REDUCE — bilaterality lost (min_bc caiu para 0). "
            "Avaliar transição para Back se dominante com 3+ CC unilateral."
        )
        return

    # 5. Reduce (15+ min no CC) — só dispara se LAST_BC for conhecido
    if (not last_bc_unknown
        and d.minutes_since_last_match_bc >= pc.get("reduce_minutes_no_match_bc", 15)):
        decision.recommended_action = "REDUCE_OVER"
        decision.blocked_reason = (
            f"Sem big chance há {d.minutes_since_last_match_bc} min — próximo do limite, reduzir exposição"
        )
        decision.add_trace(f"Post-Over: REDUCE — no CC {d.minutes_since_last_match_bc}min")
        return

    # 6. Yellow alert (10+ min no CC) — só dispara se LAST_BC for conhecido
    if (not last_bc_unknown
        and d.minutes_since_last_match_bc > pc.get("alert_minutes_no_match_bc", 10)):
        decision.recommended_action = "YELLOW_ALERT_OVER"
        decision.blocked_reason = (
            f"Sem big chance há {d.minutes_since_last_match_bc} min — atenção"
        )
        decision.add_trace(f"Post-Over: YELLOW ALERT — no CC {d.minutes_since_last_match_bc}min")
        return

    # 7. 0x0 late
    if ms.home_score == 0 and ms.away_score == 0 and ms.minute > 80:
        decision.recommended_action = "EXIT_OVER"
        decision.blocked_reason = f"0x0 após o minuto 80 — chance de over baixa"
        decision.add_trace("Post-Over: EXIT — 0x0 after 80min")
        return

    # 8. Hold
    if d.minutes_since_last_match_bc <= pc.get("alert_minutes_no_match_bc", 10) and d.score_allows_goals:
        decision.recommended_action = "HOLD_OVER"
        decision.blocked_reason = "Big chance recente, jogo vivo — tese mantida"
        decision.add_trace("Post-Over: HOLD — CC recent, score alive")
        return

    # 9. Fallback — inclui caso last_bc_unknown (state recém-carregado)
    decision.recommended_action = "HOLD_OVER_WITH_CAUTION"
    if last_bc_unknown:
        decision.blocked_reason = (
            "Última big chance do jogo desconhecida (state recém-carregado) — manter posição"
        )
        decision.add_trace(
            "Post-Over: HOLD_WITH_UNKNOWN_BC — minutes_since_last_match_bc=UNKNOWN. "
            "EXIT por ritmo morto bloqueado pelo guard."
        )
    else:
        decision.blocked_reason = "Sem mudanças significativas — manter com cautela"
        decision.add_trace("Post-Over: HOLD_WITH_CAUTION (fallback)")
