"""
Back entry rules — Sections 8, 9, 10 of V1.2.
Also includes mixed zone resolution (Section 18.1).
"""
from .models import MatchState, DerivedVars, Decision


def evaluate_back(ms: MatchState, d: DerivedVars, decision: Decision, cfg: dict) -> bool:
    """Evaluate all Back entry rules. Returns True if a Back signal is found."""

    profile = decision.game_profile

    if profile == "UNILATERAL_BACK":
        return _evaluate_unilateral(ms, d, decision, cfg)
    elif profile == "MIXED":
        return _evaluate_mixed(ms, d, decision, cfg)

    return False


def _evaluate_unilateral(ms: MatchState, d: DerivedVars, decision: Decision, cfg: dict) -> bool:
    """Evaluate Back rules for UNILATERAL_BACK profile (Sections 8-9)."""

    # --- Back T1 Early (Section 8.1) ---
    t1e = cfg.get("back", {}).get("tier_1_early", {})
    if (t1e.get("min_minute", 20) <= ms.minute <= t1e.get("max_minute", 35)
        and d.dominant_bc >= t1e.get("min_bc", 2)
        and d.team_bc_rate <= t1e.get("max_bc_rate", 15)
        and d.opponent_bc <= t1e.get("max_opponent_bc", 0)
        and d.dominant_xgot >= t1e.get("min_xgot", 0.5)
        and not d.red_card_against_dominant
        and d.score_allows_attack is True):

        decision.recommended_action = "ENTER_BACK_T1_EARLY"
        decision.market_target = "BACK_DOMINANT_TEAM"
        decision.confidence_tier = "A-"
        decision.add_trace(f"Rule: BACK_T1_EARLY (bc={d.dominant_bc}, rate={d.team_bc_rate:.1f}, xgot={d.dominant_xgot})")
        return True

    elif t1e.get("min_minute", 20) <= ms.minute <= t1e.get("max_minute", 35):
        reasons = _back_rejection_reasons(d, t1e, require_rate=True)
        if reasons:
            decision.add_rejected("BACK_T1_EARLY", "; ".join(reasons))

    # --- Back T1 Main (Section 8.2) ---
    t1m = cfg.get("back", {}).get("tier_1_main", {})
    if (t1m.get("min_minute", 36) <= ms.minute <= t1m.get("max_minute", 50)
        and d.dominant_bc >= t1m.get("min_bc", 3)
        and d.opponent_bc <= t1m.get("max_opponent_bc", 0)
        and d.dominant_xgot >= t1m.get("min_xgot", 0.5)
        and not d.red_card_against_dominant
        and d.score_allows_attack is True):

        decision.recommended_action = "ENTER_BACK_T1_MAIN"
        decision.market_target = "BACK_DOMINANT_TEAM"
        decision.confidence_tier = "A"
        decision.add_trace(f"Rule: BACK_T1_MAIN (bc={d.dominant_bc}, xgot={d.dominant_xgot})")
        return True

    elif t1m.get("min_minute", 36) <= ms.minute <= t1m.get("max_minute", 50):
        reasons = _back_rejection_reasons(d, t1m, require_rate=False)
        if reasons:
            decision.add_rejected("BACK_T1_MAIN", "; ".join(reasons))

    # --- Back T1 Late (Section 8.3) ---
    t1l = cfg.get("back", {}).get("tier_1_late", {})
    if (t1l.get("min_minute", 51) <= ms.minute <= t1l.get("max_minute", 65)
        and d.dominant_bc >= t1l.get("min_bc", 3)
        and d.opponent_bc <= t1l.get("max_opponent_bc", 0)
        and d.dominant_xgot >= t1l.get("min_xgot", 0.5)
        and not d.red_card_against_dominant
        and d.score_allows_attack in (True, "CAUTION")
        and d.total_goals <= t1l.get("max_total_goals", 2)):

        decision.recommended_action = "ENTER_BACK_T1_LATE"
        decision.market_target = "BACK_DOMINANT_TEAM"
        decision.confidence_tier = "B+" if d.score_allows_attack is True else "B"
        decision.add_trace(f"Rule: BACK_T1_LATE (bc={d.dominant_bc}, attack={d.score_allows_attack})")
        return True

    elif t1l.get("min_minute", 51) <= ms.minute <= t1l.get("max_minute", 65):
        reasons = _back_rejection_reasons(d, t1l, require_rate=False)
        if d.total_goals > t1l.get("max_total_goals", 2):
            reasons.append(f"total_goals={d.total_goals} > {t1l.get('max_total_goals', 2)}")
        if reasons:
            decision.add_rejected("BACK_T1_LATE", "; ".join(reasons))

    # --- Back T2 (Section 9) ---
    t2 = cfg.get("back", {}).get("tier_2", {})
    if (t2.get("min_minute", 36) <= ms.minute <= t2.get("max_minute", 55)
        and d.dominant_bc == t2.get("exact_bc", 2)
        and d.opponent_bc <= t2.get("max_opponent_bc", 0)
        and d.dominant_xgot >= t2.get("min_xgot", 0.5)
        and not d.red_card_against_dominant
        and d.score_allows_attack is True):

        decision.recommended_action = "ENTER_BACK_T2"
        decision.market_target = "BACK_DOMINANT_TEAM"
        decision.confidence_tier = "B"
        decision.add_trace(f"Rule: BACK_T2 (bc={d.dominant_bc}, xgot={d.dominant_xgot})")
        return True

    elif t2.get("min_minute", 36) <= ms.minute <= t2.get("max_minute", 55):
        if d.dominant_bc == t2.get("exact_bc", 2):
            reasons = _back_rejection_reasons(d, t2, require_rate=False)
            if reasons:
                decision.add_rejected("BACK_T2", "; ".join(reasons))

    # --- Watch Back Late (Section 9 extension) ---
    if (56 <= ms.minute <= 65
        and d.dominant_bc == 2
        and d.opponent_bc == 0
        and d.dominant_xgot >= 0.5):

        decision.recommended_action = "WATCH_BACK_LATE"
        decision.market_target = "BACK_DOMINANT_TEAM"
        decision.confidence_tier = "C"
        decision.add_trace("Rule: WATCH_BACK_LATE (2 CC, 56-65 min, watch only)")
        return True

    return False


def _evaluate_mixed(ms: MatchState, d: DerivedVars, decision: Decision, cfg: dict) -> bool:
    """Evaluate Back rules for MIXED profile (Section 10 + 18.1)."""

    threshold = cfg.get("score", {}).get("mixed_zone_opponent_xgot_threshold", 0.4)
    small_cfg = cfg.get("back", {}).get("small", {})

    # Section 18.1: Resolução da Zona Mista (3x1 e 4x1)
    if d.gap_bc >= 2 and d.opponent_bc == 1 and d.dominant_bc >= 3:

        # --- 4x1 CC (Section 18.1) ---
        if d.dominant_bc >= 4:
            if d.dominant_xgot >= 0.7 and d.opponent_xgot < threshold:
                # BACK_SMALL_STRONG — dominância muito forte
                decision.recommended_action = "ENTER_BACK_SMALL"
                decision.market_target = "BACK_DOMINANT_TEAM"
                decision.confidence_tier = "B+"
                decision.add_trace(
                    f"Rule: BACK_SMALL_STRONG 4x1 (dom_xgot={d.dominant_xgot:.2f} >= 0.7, "
                    f"opp_xgot={d.opponent_xgot:.2f} < {threshold})"
                )
                return True
            elif d.opponent_xgot >= threshold:
                # 4x1 com adversário perigoso → Over ou Manual Review
                decision.add_trace(
                    f"Mixed 4x1: opp_xgot={d.opponent_xgot:.2f} >= {threshold} → Over/MANUAL_REVIEW"
                )
                decision.add_rejected("BACK_SMALL", f"4x1 opponent_xgot={d.opponent_xgot} >= {threshold}")
                return False  # Will be picked up by Over rules
            else:
                # 4x1, xgot < 0.7 mas opp < 0.4 → Back Small normal
                if (ms.minute <= small_cfg.get("max_minute", 55)
                    and d.dominant_xgot >= small_cfg.get("min_xgot", 0.5)
                    and d.dominant_xgot > d.opponent_xgot
                    and not d.red_card_against_dominant
                    and d.score_allows_attack is True):
                    decision.recommended_action = "ENTER_BACK_SMALL"
                    decision.market_target = "BACK_DOMINANT_TEAM"
                    decision.confidence_tier = "B"
                    decision.add_trace(f"Rule: BACK_SMALL 4x1 (dom={d.dominant_bc}, opp_xgot={d.opponent_xgot:.2f})")
                    return True

        # --- 3x1 CC (Section 18.1) ---
        else:  # dominant_bc == 3
            if (d.dominant_xgot >= small_cfg.get("min_xgot", 0.5)
                and d.dominant_xgot > d.opponent_xgot
                and d.opponent_xgot < threshold
                and ms.minute <= small_cfg.get("max_minute", 55)
                and not d.red_card_against_dominant
                and d.score_allows_attack is True):
                # 3x1 com opp_xgot < 0.4 → BACK_SMALL (87.5% vitória)
                decision.recommended_action = "ENTER_BACK_SMALL"
                decision.market_target = "BACK_DOMINANT_TEAM"
                decision.confidence_tier = "B"
                decision.add_trace(f"Rule: BACK_SMALL 3x1 (opp_xgot={d.opponent_xgot:.2f} < {threshold})")
                return True
            elif d.opponent_xgot >= threshold:
                # 3x1 com opp_xgot >= 0.4 → Over direction (77.8% Over 2.5)
                decision.add_trace(
                    f"Mixed 3x1: opp_xgot={d.opponent_xgot:.2f} >= {threshold} → Over direction"
                )
                decision.add_rejected("BACK_SMALL", f"opponent_xgot={d.opponent_xgot} >= {threshold}")
                return False  # Will be picked up by Over rules
            else:
                # 3x1 mas falta xgot dominante → MANUAL_REVIEW
                decision.recommended_action = "MANUAL_REVIEW"
                decision.blocked_reason = "zona mista 3x1 com xGOT ambíguo"
                decision.add_trace(f"Mixed 3x1: xgot ambíguo (dom={d.dominant_xgot:.2f}) → MANUAL_REVIEW")
                return True

    # --- gap <= 1 com min_bc >= 1 → deixar Over avaliar (Table 18: 2x1 = Over Premium) ---
    if d.gap_bc <= 1 and d.min_bc >= 1:
        decision.add_trace(f"Mixed zone gap={d.gap_bc}, min_bc={d.min_bc} → Over direction")
        return False  # Over rules will handle 2x1, 2x2, etc.

    return False


def _back_rejection_reasons(d: DerivedVars, rule_cfg: dict, require_rate: bool = False) -> list:
    """Common rejection reasons for Back rules."""
    reasons = []
    min_bc = rule_cfg.get("min_bc", rule_cfg.get("exact_bc", 2))
    if d.dominant_bc < min_bc:
        reasons.append(f"bc={d.dominant_bc} < {min_bc}")
    if d.opponent_bc > rule_cfg.get("max_opponent_bc", 0):
        reasons.append(f"opp_bc={d.opponent_bc} > {rule_cfg.get('max_opponent_bc', 0)}")
    if d.dominant_xgot < rule_cfg.get("min_xgot", 0.5):
        reasons.append(f"xgot={d.dominant_xgot} < {rule_cfg.get('min_xgot', 0.5)}")
    if d.red_card_against_dominant:
        reasons.append("red_card_against_dominant")
    if d.score_allows_attack is False:
        reasons.append("score_allows_attack=False")
    if require_rate and d.team_bc_rate > rule_cfg.get("max_bc_rate", 15):
        reasons.append(f"rate={d.team_bc_rate:.1f} > {rule_cfg.get('max_bc_rate', 15)}")
    return reasons
