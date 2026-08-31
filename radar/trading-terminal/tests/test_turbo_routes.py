"""
Testes obrigatórios da reforma v3.1 — 2 rotas + 3 tiers.

T1.  Rota A WATCH (CC rate 15min, xG 0.80) → tier=WATCH, route=A
T2.  Rota A FORTE (CC rate 12min, xG 1.00, xGOT 0.70) → tier=FORTE
T3.  Rota A PREMIUM (CC rate 10min, xG 1.00, xGOT 1.00) → tier=PREMIUM
T4.  Rota B WATCH (shot rate 4min, SOT 35%) → tier=WATCH, route=B
T5.  Rota B FORTE (shot rate 3.5min, SOT 35%, xGOT 0.70) → tier=FORTE
T6.  Rota B PREMIUM (shot rate 3min, SOT 35%, xGOT 1.00) → tier=PREMIUM
T7.  Jogo bate as 2 rotas em tiers diferentes → vence o maior
T8.  WATCH não chama DT e final_decision = radar_watch
T9.  FORTE/PREMIUM chamam DT
T10. legacy v2.0 (evaluate_turbo_legacy_trinca) ainda funciona
"""
import os, sys, unittest, types
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TELEGRAM_BOT_TOKEN","dummy")
os.environ.setdefault("TELEGRAM_CHAT_ID","dummy")

if "playwright" not in sys.modules:
    _pw = types.ModuleType("playwright")
    _pws = types.ModuleType("playwright.sync_api")
    class _D: pass
    _pws.sync_playwright = lambda: _D()
    _pws.Page = _D; _pws.BrowserContext = _D
    sys.modules["playwright"] = _pw
    sys.modules["playwright.sync_api"] = _pws

from src import turbo_routes as TR  # noqa
from src.turbo_enforcement import evaluate_turbo  # noqa


def _ms(**kw):
    """match_state default. Sobrescreve campos pelo kw."""
    base = dict(
        match_id="X", home="A", away="B",
        minute=30, home_score=0, away_score=0,
        home_cc=0, away_cc=0,
        home_xg=0.0, away_xg=0.0,
        home_xgot=0.0, away_xgot=0.0,
        home_shots=0, away_shots=0,
        home_sot=0, away_sot=0,
        home_goals=0, away_goals=0,
    )
    base.update(kw)
    return base


def _dec(action="ENTER_OVER", sev="ACTION"):
    return {"recommended_action": action, "message_severity": sev,
            "market_target": "Over 2.5"}


# === Rota A — 3 tiers =====================================================
class TestRotaA(unittest.TestCase):

    def test_T1_rota_A_WATCH(self):
        # CC rate 15min: minute=45, cc=3 → 15min/cc ✓
        # xG debt 0.80: xg=0.85, gols=0 → 0.85 ≥ 0.80 ✓
        # xGOT não exige no WATCH
        ms = _ms(minute=45, home_cc=3, away_cc=0,
                  home_xg=0.85, away_xg=0.10,
                  home_xgot=0.30, away_xgot=0.05)
        r = TR.classify_routes(ms)
        self.assertEqual(r["tier"], "WATCH")
        self.assertEqual(r["route"], "rota_a_chances_claras")

    def test_T2_rota_A_FORTE(self):
        # CC rate 12min: minute=36, cc=3
        # xG 1.00, xGOT 0.70
        ms = _ms(minute=36, home_cc=3, away_cc=0,
                  home_xg=1.10, away_xg=0.10,
                  home_xgot=0.75, away_xgot=0.05)
        r = TR.classify_routes(ms)
        self.assertEqual(r["tier"], "FORTE")
        self.assertEqual(r["route"], "rota_a_chances_claras")

    def test_T3_rota_A_PREMIUM(self):
        # CC rate 10min: minute=30, cc=3
        # xG 1.00, xGOT 1.00
        ms = _ms(minute=30, home_cc=3, away_cc=0,
                  home_xg=1.10, away_xg=0.10,
                  home_xgot=1.05, away_xgot=0.05)
        r = TR.classify_routes(ms)
        self.assertEqual(r["tier"], "PREMIUM")
        self.assertEqual(r["route"], "rota_a_chances_claras")


# === Rota B — 3 tiers =====================================================
class TestRotaB(unittest.TestCase):

    def test_T4_rota_B_WATCH(self):
        # CC zero → Rota A morre. Volume qualificado pega.
        # shot rate 4min: minute=40, home tem 10 finalizações = rate 4
        ms = _ms(minute=40,
                  home_cc=0, away_cc=0,
                  home_xg=0.90, away_xg=0.10,
                  home_xgot=0.30, away_xgot=0.05,
                  home_shots=10, away_shots=2,
                  home_sot=4, away_sot=0)   # 40%
        r = TR.classify_routes(ms)
        self.assertEqual(r["tier"], "WATCH")
        self.assertEqual(r["route"], "rota_b_volume_qualificado")

    def test_T5_rota_B_FORTE(self):
        # shot rate 3.5min: minute=35, home tem 10 finalizações = rate 3.5
        ms = _ms(minute=35, home_cc=0, away_cc=0,
                  home_xg=1.10, away_xg=0.10,
                  home_xgot=0.75, away_xgot=0.05,
                  home_shots=10, away_shots=2,
                  home_sot=4, away_sot=1)   # 4/10 = 40% home
        r = TR.classify_routes(ms)
        self.assertEqual(r["tier"], "FORTE")
        self.assertEqual(r["route"], "rota_b_volume_qualificado")

    def test_T6_rota_B_PREMIUM(self):
        # shot rate 3min: home tem 10 finalizações em 30 min = rate 3
        # SOT 40%, xG 1.20, xGOT 1.10
        ms = _ms(minute=30, home_cc=0, away_cc=0,
                  home_xg=1.20, away_xg=0.10,
                  home_xgot=1.10, away_xgot=0.05,
                  home_shots=10, away_shots=2,
                  home_sot=4, away_sot=1)   # 4/10 = 40% home
        r = TR.classify_routes(ms)
        self.assertEqual(r["tier"], "PREMIUM")
        self.assertEqual(r["route"], "rota_b_volume_qualificado")


# === Dual route — maior tier vence ========================================
class TestDualRoute(unittest.TestCase):

    def test_T7_bate_as_2_rotas_em_tiers_diferentes_vence_o_maior(self):
        # Rota A none (cc baixa). Rota B → PREMIUM (shot rate 3, SOT 40%)
        ms = _ms(minute=30,
                  home_cc=2, away_cc=0,
                  home_xg=1.30, away_xg=0.10,
                  home_xgot=1.10, away_xgot=0.05,
                  home_shots=10, away_shots=2,
                  home_sot=4, away_sot=1)        # 40% sot
        r = TR.classify_routes(ms)
        self.assertEqual(r["tier"], "PREMIUM")
        self.assertEqual(r["route"], "rota_b_volume_qualificado")

    def test_T7b_ambas_PREMIUM_Rota_A_eh_preferida(self):
        ms = _ms(minute=30,
                  home_cc=3, away_cc=0,
                  home_xg=1.50, away_xg=0.10,
                  home_xgot=1.10, away_xgot=0.05,
                  home_shots=8, away_shots=2,
                  home_sot=3, away_sot=1)
        r = TR.classify_routes(ms)
        self.assertEqual(r["tier"], "PREMIUM")
        # Quando ambas batem o mesmo tier, A tem precedência (rank a>=b)
        self.assertEqual(r["route"], "rota_a_chances_claras")


# === WATCH → radar, FORTE/PREMIUM → DT ====================================
class TestWatchVsForte(unittest.TestCase):

    def test_T8_WATCH_NAO_chama_DT_final_radar(self):
        ms = _ms(minute=45, home_cc=3, away_cc=0,
                  home_xg=0.85, away_xg=0.10,
                  home_xgot=0.30, away_xgot=0.05)
        r = evaluate_turbo(ms, _dec())
        self.assertEqual(r["tier"], "WATCH")
        self.assertEqual(r["final_decision"], "radar_watch")
        self.assertFalse(r["allowed"])
        # DT NÃO foi chamado
        self.assertIsNone(r.get("dominant_trailing_result"))

    def test_T9_FORTE_chama_DT(self):
        # FORTE com dominante NÃO perdendo (score 0-0) → DT aprova → sent
        ms = _ms(minute=36, home_cc=3, away_cc=0,
                  home_xg=1.10, away_xg=0.10,
                  home_xgot=0.75, away_xgot=0.05)
        r = evaluate_turbo(ms, _dec())
        self.assertEqual(r["tier"], "FORTE")
        self.assertTrue(r["allowed"])
        self.assertEqual(r["final_decision"], "sent")
        # DT foi chamado
        self.assertIsNotNone(r.get("dominant_trailing_result"))

    def test_T9b_PREMIUM_perdendo_DT_bloqueia(self):
        # PREMIUM mas dominante perdendo sem reação → DT bloqueia
        ms = _ms(minute=30, home_cc=3, away_cc=0,
                  home_xg=1.20, away_xg=0.10,
                  home_xgot=1.10, away_xgot=0.05,
                  home_score=0, away_score=1)
        r = evaluate_turbo(ms, _dec())
        self.assertEqual(r["tier"], "PREMIUM")
        self.assertFalse(r["allowed"])
        self.assertEqual(r["final_decision"], "blocked_dominant_trailing")


# === Legacy ainda funciona ================================================
class TestLegacy(unittest.TestCase):

    def test_T10_evaluate_turbo_legacy_trinca_funciona(self):
        from src.turbo_enforcement import evaluate_turbo_legacy_trinca
        ms = _ms(minute=35, home_cc=3, away_cc=0,
                  home_xg=1.20, away_xg=0.20,
                  home_xgot=1.05, away_xgot=0.05)
        r = evaluate_turbo_legacy_trinca(ms, _dec())
        # Não checa o resultado específico, só que NÃO LEVANTA exceção
        self.assertIsNotNone(r)
        self.assertIn("final_decision", r)


def _run():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (TestRotaA, TestRotaB, TestDualRoute,
                TestWatchVsForte, TestLegacy):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    r = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run())
