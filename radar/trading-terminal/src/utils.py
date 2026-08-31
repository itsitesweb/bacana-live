"""
Utility functions for variable derivation.
Maps directly to V1.2 Sections 3.2, 3.3, 3.3a.
"""
from .models import MatchState, DerivedVars


# Sentinela: minute_of_last_match_bc desconhecido (jogo recém-carregado,
# state nunca inicializado, ou dado faltando). NUNCA deve disparar EXIT.
UNKNOWN_LAST_BC = 999


def compute_derived(ms: MatchState) -> DerivedVars:
    """Compute all derived variables from raw match state."""
    d = DerivedVars()

    # --- Dominant team ---
    d.cc_tied = (ms.home_bc == ms.away_bc)

    if ms.home_bc > ms.away_bc:
        d.dominant_team = "home"
        d.dominant_bc = ms.home_bc
        d.opponent_bc = ms.away_bc
        d.dominant_xgot = ms.home_xgot
        d.opponent_xgot = ms.away_xgot
        d.dominant_score = ms.home_score
        d.opponent_score = ms.away_score
    elif ms.away_bc > ms.home_bc:
        d.dominant_team = "away"
        d.dominant_bc = ms.away_bc
        d.opponent_bc = ms.home_bc
        d.dominant_xgot = ms.away_xgot
        d.opponent_xgot = ms.home_xgot
        d.dominant_score = ms.away_score
        d.opponent_score = ms.home_score
    else:
        d.dominant_team = None
        d.dominant_bc = ms.home_bc
        d.opponent_bc = ms.away_bc
        d.dominant_xgot = max(ms.home_xgot, ms.away_xgot)
        d.opponent_xgot = min(ms.home_xgot, ms.away_xgot)
        d.dominant_score = ms.home_score
        d.opponent_score = ms.away_score

    # --- Aggregates ---
    d.total_bc = ms.home_bc + ms.away_bc
    d.min_bc = min(ms.home_bc, ms.away_bc)
    d.max_bc = max(ms.home_bc, ms.away_bc)
    d.gap_bc = d.max_bc - d.min_bc

    # --- Rates ---
    d.team_bc_rate = ms.minute / d.dominant_bc if d.dominant_bc > 0 else 999.0
    d.match_bc_rate = ms.minute / d.total_bc if d.total_bc > 0 else 999.0

    # --- Score ---
    d.score_diff = abs(ms.home_score - ms.away_score)
    d.total_goals = ms.home_score + ms.away_score
    d.bts = ms.home_score >= 1 and ms.away_score >= 1

    # --- score_allows_attack (Section 3.3) ---
    d.score_allows_attack = _score_allows_attack(
        d.dominant_score, d.opponent_score, ms.minute
    )

    # --- score_allows_goals (Section 3.2) ---
    d.score_allows_goals = (
        d.score_diff <= 2
        and not (ms.home_score == 0 and ms.away_score == 0 and ms.minute > 80)
    )

    # --- Red cards (V1.2 standardized booleans) ---
    d.red_card_against_dominant = _red_card_against_dominant(ms, d)
    d.red_card_against_backed_team = _red_card_against_backed_team(ms)
    d.game_killing_red_card = _game_killing_red_card(ms, d)

    # --- score_allows_late_goal_limit (Section 3.3a) ---
    d.score_allows_late_goal_limit = (
        d.bts
        and 1 <= d.score_diff <= 2
        and not d.game_killing_red_card
    )

    # --- CC timing ---
    d.minutes_since_team_last_bc = _minutes_since_team_last_bc(ms, d)
    d.minutes_since_last_match_bc = ms.minute - ms.minute_of_last_match_bc if ms.minute_of_last_match_bc > 0 else 999

    # --- Delta detection (V1.2 Ajuste 7) ---
    d.opponent_bc_changed_since_last_scan = _opponent_bc_changed(ms, d)

    # --- Post-position ---
    if ms.position_type == "BACK" and ms.position_team:
        d.team_bc_since_entry, d.opponent_bc_since_entry = _bc_since_entry(ms, d)
        d.team_xgot_since_entry = _xgot_since_entry(ms, d)

    if ms.position_type == "OVER" and ms.target_over_line > 0:
        d.over_already_won = d.total_goals > ms.target_over_line

    return d


def _score_allows_attack(dom_score: int, opp_score: int, minute: int):
    """Section 3.3: score_allows_attack — sensitive to minute."""
    if dom_score < opp_score:
        return True
    if dom_score == opp_score:
        return True
    if dom_score == opp_score + 1:
        if minute <= 70:
            return True
        else:
            return "CAUTION"
    return False


def _red_card_against_dominant(ms: MatchState, d: DerivedVars) -> bool:
    if d.dominant_team == "home":
        return ms.home_red_cards > 0
    elif d.dominant_team == "away":
        return ms.away_red_cards > 0
    return False


def _red_card_against_backed_team(ms: MatchState) -> bool:
    if ms.position_type != "BACK" or not ms.position_team:
        return False
    if ms.position_team == "home":
        return ms.home_red_cards > 0
    return ms.away_red_cards > 0


def _game_killing_red_card(ms: MatchState, d: DerivedVars) -> bool:
    """A red card that kills competitiveness (e.g., trailing team gets red)."""
    # Simplified: any red card in a game with score_diff >= 2
    if ms.home_red_cards > 0 or ms.away_red_cards > 0:
        if d.score_diff >= 2:
            return True
    return False


def _minutes_since_team_last_bc(ms: MatchState, d: DerivedVars) -> int:
    if d.dominant_team == "home" and ms.minute_of_last_home_bc > 0:
        return ms.minute - ms.minute_of_last_home_bc
    elif d.dominant_team == "away" and ms.minute_of_last_away_bc > 0:
        return ms.minute - ms.minute_of_last_away_bc
    return 999


def _opponent_bc_changed(ms: MatchState, d: DerivedVars) -> bool:
    """V1.2 Ajuste 7: detect if opponent created CC in this scan.
    Returns False if no previous scan data (-1 = no data)."""
    if ms.prev_home_bc < 0 or ms.prev_away_bc < 0:
        return False  # No previous scan data, can't detect delta
    if d.dominant_team == "home":
        return ms.away_bc > ms.prev_away_bc
    elif d.dominant_team == "away":
        return ms.home_bc > ms.prev_home_bc
    return False


def _bc_since_entry(ms: MatchState, d: DerivedVars) -> tuple:
    if ms.position_team == "home":
        team_since = ms.home_bc - ms.team_bc_at_entry
        opp_since = ms.away_bc - ms.opponent_bc_at_entry
    else:
        team_since = ms.away_bc - ms.team_bc_at_entry
        opp_since = ms.home_bc - ms.opponent_bc_at_entry
    return max(0, team_since), max(0, opp_since)


def _xgot_since_entry(ms: MatchState, d: DerivedVars) -> float:
    if ms.position_team == "home":
        return max(0.0, ms.home_xgot - ms.team_xgot_at_entry)
    else:
        return max(0.0, ms.away_xgot - ms.team_xgot_at_entry)


def compute_signal_valid_until(action: str, current_minute: int, rule_max_minute: int,
                                gol_limite_minutes: int = 2,
                                default_minutes: int = 5) -> int:
    """Section 3.9: signal validity window."""
    if "GOL_LIMITE" in action:
        return current_minute + gol_limite_minutes
    return min(current_minute + default_minutes, rule_max_minute)
