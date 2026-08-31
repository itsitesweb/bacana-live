"""
Automated tests for the V1.2 Decision Engine.
Tests all 12 scenarios against expected outcomes.

Run: python -m pytest tests/ -v
  or: python tests/test_decision_engine.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from src.decision_engine import run_scan, load_config
from examples.sample_matches import (
    back_t1_main, back_t2, back_small,
    over_premium, over_bilateral_forte, over_small, over_gol_limite,
    exit_back, reduce_over, signal_turned_against,
    blocked_draw_gol_limite, no_trade_1x1_cc,
    # Post-position scenarios
    post_back_hold, post_back_yellow_alert, post_back_reduce,
    post_back_exit_gap_inverted, post_back_exit_adv2cc_dom_stopped,
    post_over_hold, post_over_yellow_alert, post_over_exit_no_cc_20min,
    post_over_lock_profit,
    # Classifier edge cases
    cc_tied_2x2_bilateral, gol_limite_blocked_old_cc,
)


class TestDecisionEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.cfg = load_config()

    # ===================== BACK ENTRIES =====================

    def test_back_t1_main(self):
        ms = back_t1_main()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.game_profile, "UNILATERAL_BACK")
        self.assertEqual(dec.recommended_action, "ENTER_BACK_T1_MAIN")
        self.assertEqual(dec.market_target, "BACK_DOMINANT_TEAM")
        self.assertEqual(dec.confidence_tier, "A")
        self.assertEqual(dec.message_severity, "ACTION")
        self.assertEqual(dec.telegram_priority, "HIGH")
        self.assertTrue(dec.operator_action_required)
        self.assertGreater(dec.signal_valid_until, ms.minute)

    def test_back_t2(self):
        ms = back_t2()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.game_profile, "UNILATERAL_BACK")
        self.assertEqual(dec.recommended_action, "ENTER_BACK_T2")
        self.assertEqual(dec.market_target, "BACK_DOMINANT_TEAM")
        self.assertEqual(dec.confidence_tier, "B")
        self.assertEqual(dec.message_severity, "ACTION")
        self.assertTrue(dec.operator_action_required)

    def test_back_small(self):
        ms = back_small()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.game_profile, "MIXED")
        self.assertEqual(dec.recommended_action, "ENTER_BACK_SMALL")
        self.assertEqual(dec.market_target, "BACK_DOMINANT_TEAM")
        self.assertEqual(dec.confidence_tier, "B+")  # 4x1 BACK_SMALL_STRONG (xgot>=0.7)
        self.assertEqual(dec.message_severity, "ACTION")
        self.assertTrue(dec.operator_action_required)

    # ===================== OVER ENTRIES =====================

    def test_over_premium(self):
        ms = over_premium()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.game_profile, "BILATERAL_OVER")
        self.assertEqual(dec.recommended_action, "ENTER_OVER_PREMIUM")
        self.assertEqual(dec.market_target, "OVER_2_5")
        self.assertEqual(dec.confidence_tier, "A-")
        self.assertEqual(dec.message_severity, "ACTION")
        self.assertTrue(dec.operator_action_required)

    def test_over_bilateral_forte(self):
        ms = over_bilateral_forte()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.game_profile, "BILATERAL_OVER")
        self.assertEqual(dec.recommended_action, "ENTER_OVER_BILATERAL_FORTE")
        self.assertEqual(dec.market_target, "OVER_2_5")
        self.assertEqual(dec.confidence_tier, "B+")
        self.assertEqual(dec.message_severity, "ACTION")
        self.assertTrue(dec.operator_action_required)

    def test_over_small(self):
        ms = over_small()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.game_profile, "BILATERAL_OVER")
        self.assertEqual(dec.recommended_action, "ENTER_OVER_SMALL")
        self.assertIn("OVER", dec.market_target)
        self.assertEqual(dec.confidence_tier, "C+")
        self.assertEqual(dec.message_severity, "ACTION")
        self.assertTrue(dec.operator_action_required)

    def test_over_gol_limite(self):
        ms = over_gol_limite()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.game_profile, "LATE_LIMIT")
        self.assertEqual(dec.recommended_action, "ENTER_OVER_GOL_LIMITE")
        self.assertEqual(dec.market_target, "NEXT_GOAL")
        self.assertEqual(dec.alternative_market, "OVER_5_5")
        self.assertEqual(dec.confidence_tier, "Especial")
        self.assertIn("ENTRAR RÁPIDO", dec.operator_instruction)
        # Signal validity: 2 min (gol limite rule)
        self.assertEqual(dec.signal_valid_until, ms.minute + 2)

    # ===================== POST-POSITION =====================

    def test_exit_back(self):
        ms = exit_back()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.recommended_action, "EXIT_BACK")
        self.assertEqual(dec.message_severity, "URGENT")
        self.assertEqual(dec.telegram_priority, "CRITICAL")
        self.assertTrue(dec.operator_action_required)
        self.assertIn("FECHAR POSIÇÃO", dec.operator_instruction)

    def test_reduce_over(self):
        ms = reduce_over()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.recommended_action, "REDUCE_OVER")
        self.assertEqual(dec.message_severity, "ACTION")
        self.assertEqual(dec.telegram_priority, "HIGH")
        self.assertTrue(dec.operator_action_required)
        self.assertIn("REDUZIR", dec.operator_instruction)

    # ===================== BLOCKERS =====================

    def test_signal_turned_against(self):
        ms = signal_turned_against()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.recommended_action, "MANUAL_REVIEW")
        self.assertEqual(dec.blocked_reason, "SIGNAL_TURNED_AGAINST")
        self.assertEqual(dec.message_severity, "ACTION")
        self.assertTrue(dec.operator_action_required)

    def test_blocked_draw_gol_limite(self):
        ms = blocked_draw_gol_limite()
        dec, d = run_scan(ms, self.cfg)
        # Empate (score_diff=0) blocks LATE_LIMIT → falls to BILATERAL_OVER → no Over rule matches at min 79
        self.assertIn(dec.recommended_action, ("NO_ACTION", "BLOCKED"))
        self.assertNotEqual(dec.recommended_action, "ENTER_OVER_GOL_LIMITE")

    def test_no_trade_1x1_cc(self):
        ms = no_trade_1x1_cc()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.game_profile, "NO_TRADE")
        self.assertEqual(dec.recommended_action, "NO_ACTION")
        self.assertFalse(dec.operator_action_required)

    # ===================== DERIVED VARS =====================

    def test_derived_dominant_team(self):
        ms = back_t1_main()
        from src.utils import compute_derived
        d = compute_derived(ms)
        self.assertEqual(d.dominant_team, "home")
        self.assertEqual(d.dominant_bc, 3)
        self.assertEqual(d.opponent_bc, 0)
        self.assertTrue(d.score_allows_attack)
        self.assertFalse(d.cc_tied)

    def test_derived_cc_tied(self):
        ms = no_trade_1x1_cc()
        from src.utils import compute_derived
        d = compute_derived(ms)
        self.assertTrue(d.cc_tied)
        self.assertIsNone(d.dominant_team)

    def test_derived_score_allows_late_goal_limit(self):
        ms = over_gol_limite()
        from src.utils import compute_derived
        d = compute_derived(ms)
        self.assertTrue(d.bts)
        self.assertEqual(d.score_diff, 1)
        self.assertTrue(d.score_allows_late_goal_limit)

    def test_derived_score_blocks_late_goal_limit_on_draw(self):
        ms = blocked_draw_gol_limite()
        from src.utils import compute_derived
        d = compute_derived(ms)
        self.assertEqual(d.score_diff, 0)
        self.assertFalse(d.score_allows_late_goal_limit)

    def test_derived_delta_detection_no_prev(self):
        """Without previous scan data (prev=-1), delta should be False."""
        ms = back_t1_main()  # prev_bc defaults to -1
        from src.utils import compute_derived
        d = compute_derived(ms)
        self.assertFalse(d.opponent_bc_changed_since_last_scan)

    def test_derived_delta_detection_with_change(self):
        """With prev data showing opponent CC increased, delta should be True."""
        ms = signal_turned_against()
        from src.utils import compute_derived
        d = compute_derived(ms)
        self.assertTrue(d.opponent_bc_changed_since_last_scan)

    # ===================== POST-BACK (Section 15) =====================

    def test_post_back_hold(self):
        """HOLD_BACK: dom respondeu (team_bc_since=1), opp≤2, CC recent."""
        ms = post_back_hold()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.recommended_action, "HOLD_BACK")
        self.assertFalse(dec.operator_action_required)

    def test_post_back_yellow_alert(self):
        """YELLOW_ALERT_BACK: dom sem CC há 18 min (> 15 threshold)."""
        ms = post_back_yellow_alert()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.recommended_action, "YELLOW_ALERT_BACK")
        self.assertTrue(dec.operator_action_required)
        self.assertIn("NÃO AUMENTAR", dec.operator_instruction)

    def test_post_back_reduce(self):
        """REDUCE_BACK: dom sem CC há 25 min (> 20) + no xGOT new."""
        ms = post_back_reduce()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.recommended_action, "REDUCE_BACK")
        self.assertIn("REDUZIR", dec.operator_instruction)

    def test_post_back_exit_gap_inverted(self):
        """EXIT_BACK: gap inverted (CC tied after back entry)."""
        ms = post_back_exit_gap_inverted()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.recommended_action, "EXIT_BACK")
        self.assertEqual(dec.message_severity, "URGENT")

    def test_post_back_exit_adv2cc_dom_stopped(self):
        """EXIT_BACK: adv 2 CC since entry + dom stopped (0 new CC, 20 min)."""
        ms = post_back_exit_adv2cc_dom_stopped()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.recommended_action, "EXIT_BACK")
        self.assertEqual(dec.telegram_priority, "CRITICAL")
        self.assertIn("FECHAR POSIÇÃO", dec.operator_instruction)

    # ===================== POST-OVER (Section 16) =====================

    def test_post_over_hold(self):
        """HOLD_OVER: CC recent (5 min), score alive."""
        ms = post_over_hold()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.recommended_action, "HOLD_OVER")
        self.assertFalse(dec.operator_action_required)

    def test_post_over_yellow_alert(self):
        """YELLOW_ALERT_OVER: sem CC há 12 min (> 10 threshold)."""
        ms = post_over_yellow_alert()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.recommended_action, "YELLOW_ALERT_OVER")
        self.assertTrue(dec.operator_action_required)
        self.assertIn("NÃO AUMENTAR", dec.operator_instruction)

    def test_post_over_exit_no_cc_20min(self):
        """EXIT_OVER: sem CC há 22 min (>= 20 threshold)."""
        ms = post_over_exit_no_cc_20min()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.recommended_action, "EXIT_OVER")
        self.assertEqual(dec.message_severity, "URGENT")
        self.assertEqual(dec.telegram_priority, "CRITICAL")

    def test_post_over_lock_profit(self):
        """LOCK_PROFIT: total goals (3) > over line (2.5)."""
        ms = post_over_lock_profit()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.recommended_action, "LOCK_PROFIT")
        self.assertEqual(dec.message_severity, "URGENT")
        self.assertIn("TRAVAR LUCRO", dec.operator_instruction)

    # ===================== CLASSIFIER EDGE CASES =====================

    def test_cc_tied_2x2_bilateral_over(self):
        """CC tied 2x2 → BILATERAL_OVER (min_bc=2 >= 2)."""
        ms = cc_tied_2x2_bilateral()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.game_profile, "BILATERAL_OVER")
        self.assertTrue(d.cc_tied)
        self.assertEqual(d.min_bc, 2)

    def test_gol_limite_blocked_old_cc(self):
        """Gol Limite conditions met BUT last CC > 12 min ago → BLOCKED."""
        ms = gol_limite_blocked_old_cc()
        dec, d = run_scan(ms, self.cfg)
        self.assertEqual(dec.recommended_action, "BLOCKED")
        self.assertEqual(dec.blocked_reason, "LAST_BC_TOO_OLD")

    # ===================== score_allows_attack (Section 3.3) =====================

    def test_score_allows_attack_before_70(self):
        """Dom leading by 1 before min 70 → True."""
        from src.utils import _score_allows_attack
        result = _score_allows_attack(dom_score=1, opp_score=0, minute=65)
        self.assertTrue(result is True)

    def test_score_allows_attack_after_70(self):
        """Dom leading by 1 after min 70 → CAUTION."""
        from src.utils import _score_allows_attack
        result = _score_allows_attack(dom_score=1, opp_score=0, minute=75)
        self.assertEqual(result, "CAUTION")


if __name__ == "__main__":
    unittest.main(verbosity=2)
