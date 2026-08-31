"""
Over entry rules — Sections 11, 12, 13, 14 of V1.2.
"""
from .models import MatchState, DerivedVars, Decision


def evaluate_over(ms: MatchState, d: DerivedVars, decision: Decision, cfg: dict) -> bool:
    """Evaluate all Over entry rules. Returns True if an Over signal is found."""

    profile = decision.game_profile

    if profile == "LATE_LIMIT":
        return _evaluate_gol_limite(ms, d, decision, cfg)

    if profile in ("BILATERAL_OVER", "MIXED"):
        # Section 6: NO_NEW_OVER_AFTER_75 — Over normal bloqueado após 75 min
        max_over = cfg.get("engine", {}).get("max_over_entry_minute", 75)
        if ms.minute > max_over:
            decision.recommended_action = "BLOCKED"
            decision.blocked_reason = "NO_NEW_OVER_AFTER_75"
            decision.add_trace(f"BLOCKED: Over normal, minute {ms.minute} > {max_over}")
            return True

        # Section 18.2: min_bc == 0 bloqueia Over bilateral
        if d.min_bc == 0:
            decision.recommended_action = "BLOCKED"
            decision.blocked_reason = "MIN_BC_ZERO_BLOCKS_OVER"
            decision.add_trace("BLOCKED: min_bc=0, CC unilateral, Over bilateral bloqueado")
            return True

        # Try in order: Premium > Bilateral Forte > Small
        if _evaluate_over_premium(ms, d, decision, cfg):
            return True
        if _evaluate_over_bilateral_forte(ms, d, decision, cfg):
            return True
        if _evaluate_over_small(ms, d, decision, cfg):
            return True

    return False


def _evaluate_over_premium(ms: MatchState, d: DerivedVars, decision: Decision, cfg: dict) -> bool:
    """Section 11: Over Premium."""
    oc = cfg.get("over", {}).get("premium", {})

    if (oc.get("min_minute", 36) <= ms.minute <= oc.get("max_minute", 50)
        and d.total_bc >= oc.get("min_total_bc", 3)
        and d.match_bc_rate <= oc.get("max_match_bc_rate", 15)
        and d.min_bc >= oc.get("min_min_bc", 1)
        and d.score_allows_goals):

        decision.recommended_action = "ENTER_OVER_PREMIUM"
        decision.market_target = "OVER_2_5"
        decision.confidence_tier = "A-"
        decision.target_over_line = 2.5
        decision.add_trace(
            f"Rule: OVER_PREMIUM (total={d.total_bc}, rate={d.match_bc_rate:.1f}, "
            f"min_bc={d.min_bc})"
        )
        return True

    if oc.get("min_minute", 36) <= ms.minute <= oc.get("max_minute", 50):
        reasons = _over_rejection(d, oc)
        if reasons:
            decision.add_rejected("OVER_PREMIUM", "; ".join(reasons))

    return False


def _evaluate_over_bilateral_forte(ms: MatchState, d: DerivedVars, decision: Decision, cfg: dict) -> bool:
    """Section 12: Over Bilateral Forte."""
    oc = cfg.get("over", {}).get("bilateral_forte", {})

    if (oc.get("min_minute", 36) <= ms.minute <= oc.get("max_minute", 65)
        and d.total_bc >= oc.get("min_total_bc", 4)
        and d.match_bc_rate <= oc.get("max_match_bc_rate", 15)
        and d.min_bc >= oc.get("min_min_bc", 2)
        and d.score_allows_goals):

        decision.recommended_action = "ENTER_OVER_BILATERAL_FORTE"
        decision.market_target = "OVER_2_5"
        decision.confidence_tier = "B+"
        decision.target_over_line = 2.5
        decision.add_trace(
            f"Rule: OVER_BILATERAL_FORTE (total={d.total_bc}, min_bc={d.min_bc}, "
            f"rate={d.match_bc_rate:.1f})"
        )
        return True

    if oc.get("min_minute", 36) <= ms.minute <= oc.get("max_minute", 65):
        reasons = _over_rejection(d, oc)
        if reasons:
            decision.add_rejected("OVER_BILATERAL_FORTE", "; ".join(reasons))

    return False


def _evaluate_over_small(ms: MatchState, d: DerivedVars, decision: Decision, cfg: dict) -> bool:
    """Section 13: Over Small (V1.2: total_goals <= 2)."""
    oc = cfg.get("over", {}).get("small", {})

    if (oc.get("min_minute", 66) <= ms.minute <= oc.get("max_minute", 75)
        and d.total_bc >= oc.get("min_total_bc", 5)
        and d.match_bc_rate <= oc.get("max_match_bc_rate", 15)
        and d.min_bc >= oc.get("min_min_bc", 2)
        and d.total_goals <= oc.get("max_total_goals", 2)
        and d.minutes_since_last_match_bc <= oc.get("max_minutes_since_last_bc", 10)
        and d.score_allows_goals):

        decision.recommended_action = "ENTER_OVER_SMALL"
        decision.confidence_tier = "C+"

        # V1.2 Ajuste 5: market_target depends on total_goals
        if d.total_goals <= 1:
            decision.market_target = "OVER_2_5"
        else:  # total_goals == 2
            decision.market_target = "NEXT_GOAL_OR_OVER_2_5"

        decision.target_over_line = 2.5
        decision.add_trace(
            f"Rule: OVER_SMALL (total={d.total_bc}, goals={d.total_goals}, "
            f"last_bc={d.minutes_since_last_match_bc}min)"
        )
        return True

    if oc.get("min_minute", 66) <= ms.minute <= oc.get("max_minute", 75):
        reasons = _over_rejection(d, oc)
        if d.total_goals > oc.get("max_total_goals", 2):
            reasons.append(f"total_goals={d.total_goals} > {oc.get('max_total_goals', 2)}")
        if d.minutes_since_last_match_bc > oc.get("max_minutes_since_last_bc", 10):
            reasons.append(f"last_bc={d.minutes_since_last_match_bc}min > 10")
        if reasons:
            decision.add_rejected("OVER_SMALL", "; ".join(reasons))

    return False


def _evaluate_gol_limite(ms: MatchState, d: DerivedVars, decision: Decision, cfg: dict) -> bool:
    """Section 14: Over Gol Limite (V1.2: uses score_allows_late_goal_limit + total_goals for market)."""
    oc = cfg.get("over", {}).get("gol_limite", {})

    if (oc.get("min_minute", 76) <= ms.minute <= oc.get("max_minute", 83)
        and d.total_bc >= oc.get("min_total_bc", 7)
        and d.min_bc >= oc.get("min_min_bc", 2)
        and d.score_allows_late_goal_limit
        and d.minutes_since_last_match_bc <= oc.get("max_minutes_since_last_bc", 12)):

        decision.recommended_action = "ENTER_OVER_GOL_LIMITE"
        decision.confidence_tier = "Especial"
        decision.market_target = "NEXT_GOAL"

        # V1.2 Ajuste 4: target depends on total_goals, not just score_diff
        tg = d.total_goals
        if tg <= 2:
            decision.alternative_market = "OVER_2_5"
            decision.target_over_line = 2.5
        elif tg == 3:
            decision.alternative_market = "OVER_3_5"
            decision.target_over_line = 3.5
        elif tg == 4:
            decision.alternative_market = "OVER_4_5"
            decision.target_over_line = 4.5
        else:
            decision.alternative_market = f"OVER_{tg}_5"
            decision.target_over_line = tg + 0.5

        decision.add_trace(
            f"Rule: OVER_GOL_LIMITE (total_bc={d.total_bc}, total_goals={tg}, "
            f"diff={d.score_diff}, last_bc={d.minutes_since_last_match_bc}min, "
            f"alt={decision.alternative_market})"
        )
        return True

    # Log rejection reasons with explicit blocked_reasons (Section 23.10)
    if oc.get("min_minute", 76) <= ms.minute <= oc.get("max_minute", 83):
        if d.total_bc >= oc.get("min_total_bc", 7):
            # Tem CC suficiente mas algo bloqueia — emitir BLOCKED com reason
            if d.score_diff == 0:
                decision.recommended_action = "BLOCKED"
                decision.blocked_reason = "DRAW_BLOCKS_GOL_LIMITE"
                decision.add_trace("BLOCKED: empate invalida Over Gol Limite")
                return True
            if d.minutes_since_last_match_bc > oc.get("max_minutes_since_last_bc", 12):
                decision.recommended_action = "BLOCKED"
                decision.blocked_reason = "LAST_BC_TOO_OLD"
                decision.add_trace(f"BLOCKED: última CC há {d.minutes_since_last_match_bc}min > 12")
                return True

        reasons = []
        if d.total_bc < oc.get("min_total_bc", 7):
            reasons.append(f"total_bc={d.total_bc} < 7")
        if not d.score_allows_late_goal_limit:
            if not d.bts:
                reasons.append("BTS=False")
            if d.score_diff < 1:
                reasons.append(f"score_diff={d.score_diff} < 1 (empate)")
            if d.score_diff > 2:
                reasons.append(f"score_diff={d.score_diff} > 2")
            if d.game_killing_red_card:
                reasons.append("game_killing_red_card")
        if d.minutes_since_last_match_bc > oc.get("max_minutes_since_last_bc", 12):
            reasons.append(f"last_bc={d.minutes_since_last_match_bc}min > 12")
        if reasons:
            decision.add_rejected("OVER_GOL_LIMITE", "; ".join(reasons))

    return False


def _over_rejection(d: DerivedVars, rule_cfg: dict) -> list:
    reasons = []
    if d.total_bc < rule_cfg.get("min_total_bc", 3):
        reasons.append(f"total_bc={d.total_bc} < {rule_cfg.get('min_total_bc', 3)}")
    if d.match_bc_rate > rule_cfg.get("max_match_bc_rate", 15):
        reasons.append(f"rate={d.match_bc_rate:.1f} > {rule_cfg.get('max_match_bc_rate', 15)}")
    if d.min_bc < rule_cfg.get("min_min_bc", 1):
        reasons.append(f"min_bc={d.min_bc} < {rule_cfg.get('min_min_bc', 1)}")
    if not d.score_allows_goals:
        reasons.append("score_allows_goals=False")
    return reasons
