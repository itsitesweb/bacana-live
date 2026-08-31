"""
Game profile classification — Section 7 of V1.2.

Order matters:
  1. LATE_LIMIT first (would be caught by BILATERAL_OVER)
  2. CC tied → BILATERAL_OVER if min_bc >= 2, else NO_TRADE
  3. UNILATERAL_BACK (min_bc == 0)
  4. BILATERAL_OVER (min_bc >= 2)
  5. MIXED (min_bc == 1)
  6. NO_TRADE (fallback)
"""
from .models import MatchState, DerivedVars, Decision


def classify_profile(ms: MatchState, d: DerivedVars, decision: Decision, cfg: dict) -> str:
    """Classify the game profile. Returns profile string and logs trace."""

    gl_cfg = cfg.get("over", {}).get("gol_limite", {})

    # --- 1. LATE_LIMIT first ---
    late_limit_ok = (
        gl_cfg.get("min_minute", 76) <= ms.minute <= gl_cfg.get("max_minute", 83)
        and d.total_bc >= gl_cfg.get("min_total_bc", 7)
        and d.min_bc >= gl_cfg.get("min_min_bc", 2)
        and d.bts
        and gl_cfg.get("min_score_diff", 1) <= d.score_diff <= gl_cfg.get("max_score_diff", 2)
        and d.minutes_since_last_match_bc <= gl_cfg.get("max_minutes_since_last_bc", 12)
        and not d.game_killing_red_card
    )

    if late_limit_ok:
        decision.add_trace("Profile: LATE_LIMIT (76-83 min, CC>=7, BTS, diff 1-2, CC recent)")
        return "LATE_LIMIT"

    # Log why LATE_LIMIT was rejected if in the time window
    if gl_cfg.get("min_minute", 76) <= ms.minute <= gl_cfg.get("max_minute", 83):
        reasons = []
        if d.total_bc < gl_cfg.get("min_total_bc", 7):
            reasons.append(f"total_bc={d.total_bc} < 7")
        if d.min_bc < gl_cfg.get("min_min_bc", 2):
            reasons.append(f"min_bc={d.min_bc} < 2")
        if not d.bts:
            reasons.append("BTS=False")
        if not (gl_cfg.get("min_score_diff", 1) <= d.score_diff <= gl_cfg.get("max_score_diff", 2)):
            reasons.append(f"score_diff={d.score_diff} outside 1-2")
        if d.minutes_since_last_match_bc > gl_cfg.get("max_minutes_since_last_bc", 12):
            reasons.append(f"last_bc={d.minutes_since_last_match_bc}min > 12")
        if d.game_killing_red_card:
            reasons.append("game_killing_red_card")
        if reasons:
            decision.add_rejected("LATE_LIMIT", "; ".join(reasons))

    # --- 2. CC tied (V1.2 Ajuste 1) ---
    if d.cc_tied:
        if d.min_bc >= 2:
            decision.add_trace(f"Profile: BILATERAL_OVER (CC tied {d.min_bc}x{d.min_bc}, both >= 2)")
            return "BILATERAL_OVER"
        else:
            decision.add_trace(f"Profile: NO_TRADE (CC tied {d.min_bc}x{d.min_bc}, insufficient)")
            decision.add_rejected("BILATERAL_OVER", f"CC tied but min_bc={d.min_bc} < 2")
            return "NO_TRADE"

    # --- 3. UNILATERAL_BACK ---
    if d.min_bc == 0:
        decision.add_trace(f"Profile: UNILATERAL_BACK (min_bc=0, gap={d.gap_bc})")
        return "UNILATERAL_BACK"

    # --- 4. BILATERAL_OVER ---
    if d.min_bc >= 2:
        decision.add_trace(f"Profile: BILATERAL_OVER (min_bc={d.min_bc}, total={d.total_bc})")
        return "BILATERAL_OVER"

    # --- 5. MIXED ---
    if d.min_bc == 1:
        tendency = "Back Small" if d.gap_bc >= 2 else "Over Watch"
        decision.add_trace(f"Profile: MIXED (min_bc=1, gap={d.gap_bc}, tendency: {tendency})")
        return "MIXED"

    # --- 6. Fallback ---
    decision.add_trace("Profile: NO_TRADE (fallback)")
    return "NO_TRADE"
