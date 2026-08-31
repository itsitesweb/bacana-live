"""
Testes do Código 3:1 — A Matriz das Chances Claras (src/codigo_3_1.py).

17 testes cobrindo TODOS os casos da especificação (docs/current/
Codigo_3_1_Matriz_das_Chances_Claras.md, Seção 16).

  T1.  Min 45, CC 1x2, placar 0-0                → ALERTA principal (bucket 1)
  T2.  Min 45, CC 1x2, placar 1-0                → NÃO alerta (placar = expected)
  T3.  Min 60, CC 2x1, placar 0-0                → NÃO alerta (rate 20 > 15)
  T4.  Min 60, CC 4x2, placar 1-0                → ALERTA principal (bucket 2)
  T5.  Min 60, CC 4x2, placar 2-0                → NÃO alerta (placar = expected)
  T6.  Min 65, CC 3x0, placar 0-0                → ALERTA unilateral (bucket 1)
  T7.  Min 70, CC 6x0, placar 1-0                → ALERTA unilateral (bucket 2)
  T8.  Min 70, CC 6x0, placar 2-0                → NÃO alerta (dom_score acompanhou)
  T9.  Min 70, CC 3x1, placar 0-0, rate>15       → NÃO alerta (min_team_cc != 0)
  T10. Mesmo bucket → não repete
  T11. Novo bucket → dispara
  T12. Min 30 bilateral 2x1, placar 0-0          → ALERTA principal
  T13. Min 80 CC 9x0, placar 1-0                 → ALERTA unilateral (rate>15)
  T14. Min 70 CC 6x0, placar 2-0                 → NÃO alerta (proporcional)
  T15. home_bc=0 AND away_bc=0                   → NÃO alerta (CC<3)
  T16. Log JSONL contém todos os campos exigidos
  T17. send_alert só envia quando should_alert=True
"""
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub Playwright pra evitar import error
if "playwright" not in sys.modules:
    pw = types.ModuleType("playwright")
    pwsa = types.ModuleType("playwright.sync_api")
    pwsa.sync_playwright = lambda: None
    pwsa.Page = type("Page", (), {})
    pwsa.BrowserContext = type("BC", (), {})
    sys.modules["playwright"] = pw
    sys.modules["playwright.sync_api"] = pwsa

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy")
os.environ.setdefault("TELEGRAM_CHAT_ID", "dummy")

from src.models import MatchState
from src import codigo_3_1


# ──────────────────────────────────────────────────────────────────────
# Helper: cria MatchState pronto
# ──────────────────────────────────────────────────────────────────────

def make_ms(*, minute, home_bc, away_bc, home_score=0, away_score=0,
            home="Time A", away="Time B"):
    return MatchState(
        match_id=f"FS_test_{minute}_{home_bc}_{away_bc}",
        home=home, away=away,
        minute=minute,
        home_bc=home_bc, away_bc=away_bc,
        home_score=home_score, away_score=away_score,
    )


def evaluate(ms, prev=None):
    return codigo_3_1.evaluate_codigo_3_1(ms, prev or {})


# ──────────────────────────────────────────────────────────────────────


class TestCodigo3_1(unittest.TestCase):

    # ──────── T1 ────────
    def test_T1_main_alert_3cc_0_0(self):
        d = evaluate(make_ms(minute=45, home_bc=1, away_bc=2,
                              home_score=0, away_score=0))
        self.assertTrue(d["should_alert"])
        # Regra 3.1.2.0: total=3, rate=15, gols<expected → WATCH OVER
        self.assertEqual(d["alert_type"], codigo_3_1.ALERT_OVER_WATCH)
        self.assertEqual(d["bucket"], 1)
        self.assertEqual(d["reason"], "OVER_WATCH")
        f = d["telegram_message_fields"]
        self.assertEqual(f["total_cc"], 3)
        self.assertEqual(f["expected_goals_by_cc"], 1)
        self.assertAlmostEqual(f["cc_rate"], 15.0, places=3)

    # ──────── T2 ────────
    def test_T2_no_alert_3cc_score_matched(self):
        d = evaluate(make_ms(minute=45, home_bc=1, away_bc=2,
                              home_score=1, away_score=0))
        self.assertFalse(d["should_alert"])
        self.assertEqual(d["reason"], "goals>=expected")

    # ──────── T3 ────────
    def test_T3_no_alert_rate_too_high(self):
        d = evaluate(make_ms(minute=60, home_bc=2, away_bc=1,
                              home_score=0, away_score=0))
        # cc_rate = 60/3 = 20 > 15
        self.assertFalse(d["should_alert"])
        self.assertEqual(d["reason"], "rate>15")

    # ──────── T4 ────────
    def test_T4_main_alert_6cc_1_0(self):
        d = evaluate(make_ms(minute=60, home_bc=4, away_bc=2,
                              home_score=1, away_score=0))
        # rate = 60/6 = 10; expected = 2; goals = 1
        # Regra 3.1.2.0: total=6 + rate≤12 + abaixo → PREMIUM OVER (prio 3)
        # (NÃO bilateral porque 4x2 não satisfaz home>=3 AND away>=3? Sim, 4>=3 e 2<3 → não bilateral)
        self.assertTrue(d["should_alert"])
        self.assertEqual(d["alert_type"], codigo_3_1.ALERT_OVER_PREMIUM)
        self.assertEqual(d["bucket"], 2)

    # ──────── T5 ────────
    def test_T5_no_alert_6cc_score_matched(self):
        d = evaluate(make_ms(minute=60, home_bc=4, away_bc=2,
                              home_score=2, away_score=0))
        self.assertFalse(d["should_alert"])
        self.assertEqual(d["reason"], "goals>=expected")

    # ──────── T6 ────────
    def test_T6_unilateral_alert_3x0_0_0(self):
        d = evaluate(make_ms(minute=65, home_bc=3, away_bc=0,
                              home_score=0, away_score=0))
        # Regra 3.1.2.0: dom_cc=3, opp=0, diff=3, dom_goals=0<1 → WATCH BACK
        # Também: total_cc=3, rate=65/3=21.6>15 → OVER WATCH bloqueado
        self.assertTrue(d["should_alert"])
        self.assertEqual(d["alert_type"], codigo_3_1.ALERT_BACK_WATCH)
        self.assertEqual(d["bucket"], 1)
        f = d["telegram_message_fields"]
        self.assertEqual(f["dom_cc"], 3)
        self.assertEqual(f["dominant_team"], "home")
        self.assertEqual(f["expected_dominant_goals_by_cc"], 1)

    # ──────── T7 ────────
    def test_T7_unilateral_alert_6x0_1_0(self):
        d = evaluate(make_ms(minute=70, home_bc=6, away_bc=0,
                              home_score=1, away_score=0))
        # Regra 3.1.2.0: dom_cc=6, opp=0, diff=6, dom_goals=1<2 → BACK PREMIUM (prio 4)
        # OVER PREMIUM/FORTE/WATCH também batem (total=6, rate=70/6=11.67≤12, gols=1<2)
        # Prioridade: PREMIUM OVER (prio 3) > BACK PREMIUM (prio 4) → escolhe PREMIUM OVER
        self.assertTrue(d["should_alert"])
        self.assertEqual(d["alert_type"], codigo_3_1.ALERT_OVER_PREMIUM)
        self.assertEqual(d["bucket"], 2)

    # ──────── T8 ────────
    def test_T8_no_alert_unilateral_proportional(self):
        # 6 CC, 2 gols do dominante = exatamente esperado
        d = evaluate(make_ms(minute=70, home_bc=6, away_bc=0,
                              home_score=2, away_score=0))
        self.assertFalse(d["should_alert"])

    # ──────── T9 ────────
    def test_T9_no_alert_not_unilateral_rate_high(self):
        # Min 70, CC 3x1, placar 0-0
        # max=3, min=1 (NÃO unilateral puro)
        # total=4, rate = 70/4 = 17.5 > 15 → regra principal não bate
        d = evaluate(make_ms(minute=70, home_bc=3, away_bc=1,
                              home_score=0, away_score=0))
        self.assertFalse(d["should_alert"])
        self.assertEqual(d["reason"], "rate>15")

    # ──────── T10 ────────
    def test_T10_same_bucket_does_not_repeat(self):
        # Bucket 1 já foi alertado. Min 45 mantém rate=15 (no limite).
        # CC ainda 3, placar 0-0 → bucket 1 mesmo → não repete.
        prev = {"main_bucket": 1, "unilateral_bucket": 0}
        d = evaluate(make_ms(minute=45, home_bc=1, away_bc=2,
                              home_score=0, away_score=0), prev)
        self.assertFalse(d["should_alert"])
        self.assertEqual(d["reason"], "bucket_already_sent")

    # ──────── T11 ────────
    def test_T11_new_bucket_triggers(self):
        # Bucket 1 já foi alertado; agora total_cc=6 → bucket=2
        prev = {"main_bucket": 1, "unilateral_bucket": 0}
        d = evaluate(make_ms(minute=60, home_bc=4, away_bc=2,
                              home_score=1, away_score=0), prev)
        self.assertTrue(d["should_alert"])
        self.assertEqual(d["bucket"], 2)

    # ──────── T12 ────────
    def test_T12_main_bilateral_2x1_0_0(self):
        # Min 30, CC 2x1, placar 0-0 → rate = 10, total=3, ALERTA WATCH OVER
        # (não é PREMIUM porque total<6; não é BILATERAL porque away_bc<3)
        d = evaluate(make_ms(minute=30, home_bc=2, away_bc=1,
                              home_score=0, away_score=0))
        self.assertTrue(d["should_alert"])
        self.assertEqual(d["alert_type"], codigo_3_1.ALERT_OVER_WATCH)

    # ──────── T13 ────────
    def test_T13_unilateral_works_when_rate_above_15(self):
        # Min 100, CC 6x0, placar 1-0
        # rate = 100/6 = 16.66 > 15 → OVER (qualquer nível) bloqueado
        # BACK não usa rate; dom=6, opp=0, diff=6, dom_goals=1<2 → BACK PREMIUM
        d = evaluate(make_ms(minute=100, home_bc=6, away_bc=0,
                              home_score=1, away_score=0))
        self.assertTrue(d["should_alert"])
        self.assertEqual(d["alert_type"], codigo_3_1.ALERT_BACK_PREMIUM,
                         "BACK deve disparar mesmo com rate global > 15")

    # ──────── T14 ────────
    def test_T14_proportional_score_blocks(self):
        # Min 70, CC 6x0, placar 2-0 → dom_score=2 = expected=2 → NÃO
        d = evaluate(make_ms(minute=70, home_bc=6, away_bc=0,
                              home_score=2, away_score=0))
        self.assertFalse(d["should_alert"])

    # ──────── T15 ────────
    def test_T15_no_alert_zero_cc(self):
        d = evaluate(make_ms(minute=50, home_bc=0, away_bc=0,
                              home_score=0, away_score=0))
        self.assertFalse(d["should_alert"])
        self.assertEqual(d["reason"], "CC<3")

    # ──────── T16 ────────
    def test_T16_log_jsonl_has_required_fields(self):
        import live_daemon
        tmp = Path(tempfile.mkdtemp()) / "log.jsonl"
        ms = make_ms(minute=45, home_bc=1, away_bc=2,
                      home_score=0, away_score=0)
        d = evaluate(ms)
        with patch.object(live_daemon, "LOG_FILE", tmp):
            live_daemon._save_codigo_3_1_log(ms, d)
        entries = [json.loads(l) for l in tmp.read_text().splitlines()]
        self.assertEqual(len(entries), 1)
        e = entries[0]
        required = ["timestamp", "mode", "match_id", "home", "away", "minute",
                    "score", "home_bc", "away_bc", "total_cc", "total_goals",
                    "cc_rate", "expected_goals_by_cc", "alert_type", "bucket",
                    "should_alert", "telegram_sent", "filter_reason"]
        for key in required:
            self.assertIn(key, e, f"Log JSONL deve conter '{key}'")
        self.assertEqual(e["mode"], "codigo_3_1")
        self.assertEqual(e["alert_type"], codigo_3_1.ALERT_OVER_WATCH)
        self.assertTrue(e["should_alert"])

    # ──────── T17 ────────
    def test_T17_send_alert_only_when_should_alert(self):
        # Caso A: should_alert=False → send_alert NÃO chama _send_raw
        tg_mock = MagicMock()
        tg_mock.is_ready = MagicMock(return_value=True)
        tg_mock._send_raw = MagicMock(return_value=True)

        no_alert = codigo_3_1._no_alert("CC<3")
        result = codigo_3_1.send_alert(tg_mock, no_alert)
        self.assertFalse(result)
        tg_mock._send_raw.assert_not_called()

        # Caso B (v2.8 — pedido do Tiago): WATCH OVER volta a enviar Telegram.
        # send_alert envia para todos os tipos; dedup é responsabilidade do caller.
        d_watch = evaluate(make_ms(minute=45, home_bc=1, away_bc=2,
                                    home_score=0, away_score=0))
        self.assertEqual(d_watch["alert_type"], codigo_3_1.ALERT_OVER_WATCH)
        self.assertTrue(d_watch["should_alert"])
        result = codigo_3_1.send_alert(tg_mock, d_watch)
        self.assertTrue(result, "v2.8: WATCH envia Telegram (radar)")
        tg_mock._send_raw.assert_called_once()
        msg_watch = tg_mock._send_raw.call_args[0][0]
        self.assertIn("📡 WATCH 3.1.2 — RADAR DE GOL", msg_watch)
        tg_mock._send_raw.reset_mock()

        # Caso C: FORTE OVER envia TG operacional (cc=4, rate=12, min 48)
        tg_mock._send_raw.reset_mock()
        d_forte = evaluate(make_ms(minute=48, home_bc=3, away_bc=1,
                                    home_score=0, away_score=0))
        self.assertEqual(d_forte["alert_type"], codigo_3_1.ALERT_OVER_FORTE)
        result = codigo_3_1.send_alert(tg_mock, d_forte)
        self.assertTrue(result, "FORTE deve enviar Telegram")
        tg_mock._send_raw.assert_called_once()
        msg_forte = tg_mock._send_raw.call_args[0][0]
        self.assertIn("🟠 FORTE 3.1.2 — GOL DEVENDO", msg_forte)

    # ──────── Bonus: anti-spam state round-trip ────────
    def test_state_helpers_roundtrip(self):
        # Atualizado pós-WATCH log-only: WATCH NÃO consome bucket.
        # Usamos FORTE (cc=4, rate=12, min 48) que SIM consome bucket.
        entry = {}
        d = evaluate(make_ms(minute=48, home_bc=3, away_bc=1,
                              home_score=0, away_score=0))
        self.assertEqual(d["alert_type"], codigo_3_1.ALERT_OVER_FORTE)
        codigo_3_1.update_state_after_alert(entry, d)
        self.assertEqual(entry["codigo_3_1"]["main_bucket_last"], 1)
        # Re-leitura
        prev = codigo_3_1.get_previous_alert_state(entry)
        self.assertEqual(prev["main_bucket"], 1)
        self.assertEqual(prev["unilateral_bucket"], 0)

        # WATCH NÃO consome bucket (apenas confirma):
        entry2 = {}
        d_watch = evaluate(make_ms(minute=45, home_bc=1, away_bc=2,
                                    home_score=0, away_score=0))
        codigo_3_1.update_state_after_alert(entry2, d_watch)
        self.assertNotIn("codigo_3_1", entry2,
                          "WATCH NÃO pode escrever bucket no state")


def _run_all():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestCodigo3_1)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run_all())
