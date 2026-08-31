"""
Testes obrigatórios do DOMINANT_TRAILING_PROTECTION.

Os 7 cenários do spec:
  T1. Dominante com 3 CC no 1º tempo, perdendo 1x0, sem CC após = bloqueia.
  T2. Dominante com 3 CC, perdendo 1x0, nova CC + xG 0.50 após = passa.
  T3. Dominante perdendo 2x0 = bloqueia sempre, salvo pressão brutal.
  T4. Alerta 1º tempo sem confirmação até min 55 = expira.
  T5. Adversário amplia após alerta = tese cancelada.
  T6. WATCH_INTERNAL não envia Telegram.
  T7. FORTE/PREMIUM só sai com dominant_reaction_status="confirmed".

Roda direto: python3 tests/test_dominant_trailing_protection.py
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.dominant_trailing_protection import (
    validate, audit_log, compute_dominant_side,
    ALERT_TIER_WATCH_INTERNAL,
    STATUS_DOMINANT_TRAILING_TRAP, STATUS_DOMINANT_REACTION_CONF,
    STATUS_GOAL_DEBT_DEAD, STATUS_GOAL_DEBT_ALIVE,
    PRESSURE_BRUTAL, PRESSURE_DEAD, PRESSURE_FORTE,
)


def _snap(minute, hs, as_, hbc=0, abc=0, hxg=0.0, axg=0.0,
            hsot=0, asot=0, hsh=0, ash=0):
    return {"minute":minute,"home_score":hs,"away_score":as_,
            "home_bc":hbc,"away_bc":abc,"home_xg":hxg,"away_xg":axg,
            "home_sot":hsot,"away_sot":asot,"home_shots":hsh,"away_shots":ash}


# === T1 ====================================================================
class T1_TrailingSemReacao(unittest.TestCase):

    def test_T1_bloqueia_3cc_1h_perdendo_1x0_sem_cc_apos(self):
        """Home dominante: 3 CC home, 0 CC away. Após 1x0 (away marcou min 18),
        home não gera CC nova até min 38 (alerta). Tem que bloquear."""
        history = [
            _snap(10, 0, 0, hbc=1, abc=0, hxg=0.20),
            _snap(15, 0, 0, hbc=2, abc=0, hxg=0.30),
            _snap(18, 0, 1, hbc=2, abc=0, hxg=0.30),  # away marca
            _snap(25, 0, 1, hbc=3, abc=0, hxg=0.35),  # +1 CC mas TEVE ela ANTES de trailing
            _snap(38, 0, 1, hbc=3, abc=0, hxg=0.36),  # alerta — nada novo
        ]
        # Importante: o snapshot 25 conta como "after trailing" no nosso modelo
        # Pra testar "sem CC após", garantir histórico SEM nova CC após min 18
        history = [
            _snap(10, 0, 0, hbc=1, abc=0, hxg=0.20),
            _snap(15, 0, 0, hbc=3, abc=0, hxg=0.30),  # toda CC antes
            _snap(18, 0, 1, hbc=3, abc=0, hxg=0.30),  # away marca
            _snap(38, 0, 1, hbc=3, abc=0, hxg=0.30),  # ZERO ganho desde trailing
        ]
        payload = {"signal_id":"sigT1","match_id":"M1","home":"H","away":"A",
                   "level":"FORTE","alert_type":"over_forte",
                   "minute_at_alert":38,
                   "home_score_at_alert":0,"away_score_at_alert":1,
                   "home_bc_at_alert":3,"away_bc_at_alert":0}
        d = validate(payload, match_history=history)
        self.assertEqual(d["dominant_side"], "home")
        self.assertTrue(d["dominant_is_trailing"])
        self.assertEqual(d["dominant_trailing_by"], 1)
        self.assertEqual(d["minute_when_dominant_started_trailing"], 18)
        self.assertEqual(d["dominant_big_chances_after_trailing"], 0)
        self.assertEqual(d["dominant_reaction_status"], "not_confirmed")
        self.assertFalse(d["entry_allowed"])
        self.assertEqual(d["block_reason"],
                          "dominant_trailing_without_confirmed_reaction")
        self.assertEqual(d["alert_tier"], ALERT_TIER_WATCH_INTERNAL)
        self.assertFalse(d["telegram_sent_recommended"])


# === T2 ====================================================================
class T2_TrailingComReacao(unittest.TestCase):

    def test_T2_passa_com_nova_cc_e_xg_0_50_apos_trailing(self):
        """Home dominante: 3 CC antes do gol away. Após away marcar (min 18),
        home gera nova CC + xG 0.50 + 2 SOT. Bate 3 critérios → passa."""
        history = [
            _snap(10, 0, 0, hbc=2, abc=0, hxg=0.25, hsot=1, hsh=3),
            _snap(15, 0, 0, hbc=3, abc=0, hxg=0.30, hsot=1, hsh=4),
            _snap(18, 0, 1, hbc=3, abc=0, hxg=0.30, hsot=1, hsh=4),
            _snap(30, 0, 1, hbc=4, abc=0, hxg=0.60, hsot=2, hsh=6),
            _snap(40, 0, 1, hbc=5, abc=0, hxg=0.85, hsot=3, hsh=8),
        ]
        payload = {"signal_id":"sigT2","match_id":"M2","home":"H","away":"A",
                   "level":"FORTE","alert_type":"over_forte",
                   "minute_at_alert":40,
                   "home_score_at_alert":0,"away_score_at_alert":1,
                   "home_bc_at_alert":5,"away_bc_at_alert":0}
        d = validate(payload, match_history=history)
        self.assertEqual(d["dominant_side"], "home")
        self.assertTrue(d["dominant_is_trailing"])
        # nova CC após min 18: snapshots 18 (bc=3), 30 (bc=4), 40 (bc=5) → ganho = 2
        self.assertGreaterEqual(d["dominant_big_chances_after_trailing"], 1)
        self.assertGreaterEqual(d["dominant_xg_after_trailing"], 0.45)
        self.assertEqual(d["dominant_reaction_status"], "confirmed")
        self.assertTrue(d["entry_allowed"])
        self.assertEqual(d["block_reason"], "")
        self.assertEqual(d["status"], STATUS_DOMINANT_REACTION_CONF)


# === T3 ====================================================================
class T3_TrailingByTwo(unittest.TestCase):

    def test_T3a_bloqueia_2x0_sem_pressao_brutal(self):
        history = [
            _snap(10, 0, 1, hbc=1, abc=0, hxg=0.20),
            _snap(25, 0, 2, hbc=2, abc=0, hxg=0.30),
            _snap(35, 0, 2, hbc=2, abc=0, hxg=0.32),
        ]
        payload = {"signal_id":"sigT3a","match_id":"M3a","home":"H","away":"A",
                   "level":"FORTE","alert_type":"over_forte",
                   "minute_at_alert":35,
                   "home_score_at_alert":0,"away_score_at_alert":2,
                   "home_bc_at_alert":2,"away_bc_at_alert":0}
        d = validate(payload, match_history=history)
        self.assertEqual(d["dominant_trailing_by"], 2)
        self.assertFalse(d["entry_allowed"])
        self.assertEqual(d["block_reason"], "dominant_trailing_by_two_or_more")

    def test_T3b_excecao_pressao_brutal_mas_exige_reacao(self):
        """2x0, mas últimos 10 min têm 3 SOT do home (brutal).
        Mesmo assim exige reação confirmada — se reação OK, libera."""
        # Snapshots em janela last 10 (min 25-35): SOT cresce de 0→3, xG 0.30→0.85
        history = [
            _snap(10, 0, 1, hbc=0, abc=0, hxg=0.10, hsot=0, hsh=1),
            _snap(20, 0, 2, hbc=1, abc=0, hxg=0.30, hsot=0, hsh=3),
            _snap(25, 0, 2, hbc=2, abc=0, hxg=0.40, hsot=1, hsh=4),
            _snap(30, 0, 2, hbc=3, abc=0, hxg=0.70, hsot=2, hsh=6),
            _snap(35, 0, 2, hbc=4, abc=0, hxg=0.95, hsot=3, hsh=8),
        ]
        payload = {"signal_id":"sigT3b","match_id":"M3b","home":"H","away":"A",
                   "level":"FORTE","alert_type":"over_forte",
                   "minute_at_alert":35,
                   "home_score_at_alert":0,"away_score_at_alert":2,
                   "home_bc_at_alert":4,"away_bc_at_alert":0}
        d = validate(payload, match_history=history)
        # primeiro trailing começou em min 10 (já estava perdendo)
        # após trailing: tudo do histórico conta → muita reação
        self.assertEqual(d["dominant_reaction_status"], "confirmed")
        self.assertTrue(d["entry_allowed"])


# === T4 ====================================================================
class T4_HalftimeExpira(unittest.TestCase):

    def test_T4_alerta_1H_sem_confirmacao_ate_min55_expira(self):
        """Alerta no min 40 (1H). Histórico vai até min 56, dominante
        não gera nada novo após min 40 (zero BC, xG≈0, SOT 0)."""
        history = [
            _snap(15, 0, 0, hbc=2, abc=0, hxg=0.25, hsot=1, hsh=3),
            _snap(20, 0, 1, hbc=2, abc=0, hxg=0.25, hsot=1, hsh=3),
            _snap(40, 0, 1, hbc=3, abc=0, hxg=0.40, hsot=2, hsh=5),  # alerta
            _snap(46, 0, 1, hbc=3, abc=0, hxg=0.40, hsot=2, hsh=5),
            _snap(56, 0, 1, hbc=3, abc=0, hxg=0.40, hsot=2, hsh=5),
        ]
        payload = {"signal_id":"sigT4","match_id":"M4","home":"H","away":"A",
                   "level":"FORTE","alert_type":"over_forte",
                   "minute_at_alert":40,
                   "home_score_at_alert":0,"away_score_at_alert":1,
                   "home_bc_at_alert":3,"away_bc_at_alert":0}
        d = validate(payload, match_history=history)
        self.assertFalse(d["entry_allowed"])
        self.assertEqual(d["block_reason"],
                          "first_half_alert_not_confirmed_after_halftime")
        self.assertEqual(d["status"], STATUS_GOAL_DEBT_DEAD)
        self.assertEqual(d["live_pressure_status"], PRESSURE_DEAD)


# === T5 ====================================================================
class T5_AdversarioAmplia(unittest.TestCase):

    def test_T5_opponent_extends_lead_after_alert_cancela(self):
        """Alerta min 40, placar 0-1. Min 55 placar 0-2 (away marcou).
        Tem que cancelar com block_reason='opponent_extended_lead_after_alert'."""
        history = [
            _snap(20, 0, 1, hbc=2, abc=0, hxg=0.30),
            _snap(40, 0, 1, hbc=3, abc=0, hxg=0.50, hsot=2, hsh=5),  # alerta
            _snap(55, 0, 2, hbc=3, abc=0, hxg=0.50, hsot=2, hsh=5),  # away amplia
        ]
        payload = {"signal_id":"sigT5","match_id":"M5","home":"H","away":"A",
                   "level":"PREMIUM","alert_type":"over_premium",
                   "minute_at_alert":40,
                   "home_score_at_alert":0,"away_score_at_alert":1,
                   "home_bc_at_alert":3,"away_bc_at_alert":0}
        d = validate(payload, match_history=history)
        self.assertEqual(d["opponent_goals_after_alert"], 1)
        self.assertFalse(d["entry_allowed"])
        self.assertEqual(d["block_reason"], "opponent_extended_lead_after_alert")
        self.assertEqual(d["status"], STATUS_GOAL_DEBT_DEAD)


# === T6 ====================================================================
class T6_WatchInternalNaoTelegrama(unittest.TestCase):

    def test_T6_qualquer_bloqueio_seta_watch_internal_e_telegram_false(self):
        payload = {"signal_id":"sigT6","match_id":"M6","home":"H","away":"A",
                   "level":"FORTE","alert_type":"over_forte",
                   "minute_at_alert":50,
                   "home_score_at_alert":0,"away_score_at_alert":1,
                   "home_bc_at_alert":3,"away_bc_at_alert":0}
        # sem history → modo degradado, sem reação confirmada
        d = validate(payload, match_history=None)
        self.assertEqual(d["alert_tier"], ALERT_TIER_WATCH_INTERNAL)
        self.assertFalse(d["telegram_sent_recommended"])
        self.assertIn("BLOQUEADO", d["block_message"])


# === T7 ====================================================================
class T7_FortePremiumPrecisaReacaoConfirmada(unittest.TestCase):

    def test_T7_forte_passa_apenas_com_reacao_confirmada(self):
        # Caso 1: trailing sem reação → FORTE bloqueado
        history_neg = [
            _snap(10, 0, 0, hbc=2, abc=0, hxg=0.25),
            _snap(20, 0, 1, hbc=3, abc=0, hxg=0.30),
            _snap(40, 0, 1, hbc=3, abc=0, hxg=0.30),
        ]
        p_neg = {"signal_id":"sigT7n","match_id":"M7n","home":"H","away":"A",
                 "level":"FORTE","alert_type":"over_forte",
                 "minute_at_alert":40,
                 "home_score_at_alert":0,"away_score_at_alert":1,
                 "home_bc_at_alert":3,"away_bc_at_alert":0}
        d = validate(p_neg, match_history=history_neg)
        self.assertEqual(d["alert_tier"], ALERT_TIER_WATCH_INTERNAL)
        self.assertFalse(d["entry_allowed"])

        # Caso 2: PREMIUM com reação CONFIRMADA → passa, tier preservado
        history_pos = [
            _snap(10, 0, 0, hbc=2, abc=0, hxg=0.25),
            _snap(15, 0, 1, hbc=2, abc=0, hxg=0.25),
            _snap(25, 0, 1, hbc=3, abc=0, hxg=0.55, hsot=2, hsh=6),
            _snap(38, 0, 1, hbc=4, abc=0, hxg=0.80, hsot=3, hsh=8),
        ]
        p_pos = {"signal_id":"sigT7p","match_id":"M7p","home":"H","away":"A",
                 "level":"PREMIUM","alert_type":"over_premium",
                 "minute_at_alert":38,
                 "home_score_at_alert":0,"away_score_at_alert":1,
                 "home_bc_at_alert":4,"away_bc_at_alert":0}
        d2 = validate(p_pos, match_history=history_pos)
        self.assertEqual(d2["dominant_reaction_status"], "confirmed")
        self.assertTrue(d2["entry_allowed"])
        self.assertEqual(d2["alert_tier"], "PREMIUM")


# === Testes adicionais defensivos ==========================================
class TX_Defensivos(unittest.TestCase):

    def test_X1_nao_trailing_passa_direto(self):
        p = {"level":"FORTE","alert_type":"over_forte","minute_at_alert":30,
             "home_score_at_alert":1,"away_score_at_alert":0,
             "home_bc_at_alert":3,"away_bc_at_alert":0}
        d = validate(p)
        self.assertTrue(d["entry_allowed"])
        self.assertFalse(d["dominant_is_trailing"])
        self.assertEqual(d["dominant_reaction_status"], "not_trailing")

    def test_X2_sem_dominante_empate_total_passa(self):
        p = {"level":"WATCH","minute_at_alert":30,
             "home_score_at_alert":0,"away_score_at_alert":0,
             "home_bc_at_alert":2,"away_bc_at_alert":2,
             "home_xg_at_alert":0.4,"away_xg_at_alert":0.4,
             "home_sot_at_alert":1,"away_sot_at_alert":1,
             "home_shots_at_alert":3,"away_shots_at_alert":3}
        d = validate(p)
        self.assertIsNone(d["dominant_side"])
        self.assertTrue(d["entry_allowed"])

    def test_X3_audit_log_appenda_sem_tocar_outros(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            p = {"signal_id":"sigX3","match_id":"MX3","home":"H","away":"A",
                 "level":"FORTE","alert_type":"over_forte","minute_at_alert":40,
                 "home_score_at_alert":0,"away_score_at_alert":1,
                 "home_bc_at_alert":3,"away_bc_at_alert":0}
            d = validate(p)
            log_path = tmp / "audit.jsonl"
            audit_log(p, d, path=log_path)
            audit_log(p, d, path=log_path)  # 2 linhas
            lines = log_path.read_text().splitlines()
            self.assertEqual(len(lines), 2)
            rec = json.loads(lines[0])
            self.assertEqual(rec["match_id"], "MX3")
            self.assertIn("decision", rec)
            self.assertIn("entry_allowed", rec["decision"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_X4_compute_dominant_side_hierarquia(self):
        # home tem mais BC
        self.assertEqual(compute_dominant_side({"home_bc_at_alert":3,
                                                  "away_bc_at_alert":1}), "home")
        # empate BC → desempate xG (home)
        self.assertEqual(compute_dominant_side({"home_bc_at_alert":2,
                                                  "away_bc_at_alert":2,
                                                  "home_xg_at_alert":1.0,
                                                  "away_xg_at_alert":0.3}), "home")
        # empate BC+xG → desempate SOT (away)
        self.assertEqual(compute_dominant_side({"home_bc_at_alert":2,
                                                  "away_bc_at_alert":2,
                                                  "home_xg_at_alert":0.5,
                                                  "away_xg_at_alert":0.5,
                                                  "home_sot_at_alert":1,
                                                  "away_sot_at_alert":4}), "away")
        # explicit override
        self.assertEqual(compute_dominant_side({"dominant_side":"away",
                                                  "home_bc_at_alert":5,
                                                  "away_bc_at_alert":1}), "away")


def _run():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (T1_TrailingSemReacao, T2_TrailingComReacao,
                T3_TrailingByTwo, T4_HalftimeExpira, T5_AdversarioAmplia,
                T6_WatchInternalNaoTelegrama, T7_FortePremiumPrecisaReacaoConfirmada,
                TX_Defensivos):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    r = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run())
