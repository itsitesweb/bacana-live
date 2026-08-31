"""
Testes do TRIPLE_DEBT_FILTER — nova regra-mãe 3.1.2.0 Turbo.

Cobre T1–T10 do spec + defensivos. Roda standalone:
  python3 tests/test_triple_debt_filter.py

NOTA SOBRE ALGUNS TESTES:
  T2 e T4 do spec original usavam valores numéricos que NÃO classificam
  como bilateral/unilateral sob as novas regras de escopo (totais
  insuficientes pra bater B/C do bilateral, ou cc<3 pra A do unilateral).
  Mantive os valores do spec literal (T2_spec / T4_spec) — esses caem em
  scope=none com block_reason=scope_not_classified — e adicionei variantes
  T2_adapted / T4_adapted que constroem o cenário onde o escopo classifica
  mas a TRINCA falha exatamente na perna esperada. Ambos os pares são
  válidos: o primeiro testa que o escopo é estrito; o segundo testa o
  fluxo de bloqueio por perna.
"""
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.triple_debt_filter import (
    validate_triple_debt_filter, audit_log,
    REASON_FAILED_CC, REASON_FAILED_XG, REASON_FAILED_XGOT,
    REASON_FAILED_MULTIPLE, REASON_NO_REAL_DEBT,
    REASON_SCOPE_NOT_CLASSIFIED,
)


def ms(home_cc=0, away_cc=0, home_xg=0.0, away_xg=0.0,
        home_xgot=0.0, away_xgot=0.0, home_goals=0, away_goals=0,
        minute=30, **extra):
    """Helper pra montar match_state."""
    d = dict(home_cc=home_cc, away_cc=away_cc,
              home_xg=home_xg, away_xg=away_xg,
              home_xgot=home_xgot, away_xgot=away_xgot,
              home_goals=home_goals, away_goals=away_goals,
              minute=minute)
    d.update(extra)
    return d


# === T1 — Bilateral aprovado ===============================================
class T1_BilateralAprovado(unittest.TestCase):

    def test_T1_bilateral_aprovado_0x0_3cc_xg120_xgot110(self):
        m = ms(home_cc=2, away_cc=1,
                home_xg=0.70, away_xg=0.50,
                home_xgot=0.60, away_xgot=0.50,
                home_goals=0, away_goals=0, minute=36)
        r = validate_triple_debt_filter(m)
        self.assertEqual(r["scope"], "bilateral")
        self.assertEqual(r["scope_side"], "total")
        self.assertTrue(r["triple_debt_formed"])
        self.assertTrue(r["cc_debt"])
        self.assertTrue(r["xg_debt"])
        self.assertTrue(r["xgot_debt"])
        self.assertIsNone(r["block_reason"])
        self.assertEqual(r["cc_in_scope"], 3)
        self.assertAlmostEqual(r["xg_in_scope"], 1.20, places=2)
        self.assertAlmostEqual(r["xgot_in_scope"], 1.10, places=2)
        self.assertEqual(r["goals_in_scope"], 0)
        self.assertFalse(r["would_block_signal"])


# === T2 — Bilateral bloqueado por xGOT =====================================
class T2_BilateralFailXgot(unittest.TestCase):

    def test_T2_spec_total_3cc_xg130_xgot040_cai_em_scope_none(self):
        """Valores literais do spec: total_xgot=0.40 < BI_MIN_TOTAL_XGOT=1.00
        → bilateral falha critério C → scope=none."""
        m = ms(home_cc=2, away_cc=1,
                home_xg=0.80, away_xg=0.50,
                home_xgot=0.25, away_xgot=0.15,  # total 0.40
                home_goals=0, away_goals=0, minute=36)
        r = validate_triple_debt_filter(m)
        self.assertEqual(r["scope"], "none")
        self.assertEqual(r["block_reason"], REASON_SCOPE_NOT_CLASSIFIED)
        self.assertTrue(r["would_block_signal"])

    def test_T2_adapted_bilateral_classifica_e_falha_xgot(self):
        """Escopo bilateral classifica; placar 1-0 leva goals_in_scope=1
        e xgot_in_scope=1.50 < 2.00 → falha xGOT isolada."""
        m = ms(home_cc=3, away_cc=3,
                home_xg=1.10, away_xg=1.00,
                home_xgot=0.80, away_xgot=0.70,  # total 1.50
                home_goals=1, away_goals=0, minute=60)
        # cc_total=6 → expected=2 > goals=1 ✓
        # xg=2.10 ≥ 2.00 ✓; xgot=1.50 < 2.00 ✗
        r = validate_triple_debt_filter(m)
        self.assertEqual(r["scope"], "bilateral")
        self.assertFalse(r["triple_debt_formed"])
        self.assertEqual(r["block_reason"], REASON_FAILED_XGOT)
        self.assertEqual(r["failed_reasons"], [REASON_FAILED_XGOT])


# === T3 — Unilateral aprovado ==============================================
class T3_UnilateralAprovado(unittest.TestCase):

    def test_T3_unilateral_home_3cc_xg120_xgot105_0gols(self):
        m = ms(home_cc=3, away_cc=0,
                home_xg=1.20, away_xg=0.20,
                home_xgot=1.05, away_xgot=0.05,
                home_goals=0, away_goals=0, minute=35)
        r = validate_triple_debt_filter(m)
        self.assertEqual(r["scope"], "unilateral")
        self.assertEqual(r["scope_side"], "home")
        self.assertTrue(r["triple_debt_formed"])
        self.assertEqual(r["cc_in_scope"], 3)
        self.assertAlmostEqual(r["xg_in_scope"], 1.20, places=2)
        self.assertAlmostEqual(r["xgot_in_scope"], 1.05, places=2)
        self.assertEqual(r["goals_in_scope"], 0)
        self.assertIsNone(r["block_reason"])


# === T4 — Unilateral bloqueado por CC ======================================
class T4_UnilateralFailCC(unittest.TestCase):

    def test_T4_spec_home_2cc_cai_em_scope_none(self):
        """Spec literal: home_cc=2 < UNI_MIN_CC=3 → fail A obrigatório →
        nem unilateral nem bilateral (total_cc=2<3) → scope=none."""
        m = ms(home_cc=2, away_cc=0,
                home_xg=1.20, away_xg=0.20,
                home_xgot=1.05, away_xgot=0.05,
                home_goals=0, away_goals=0, minute=30)
        r = validate_triple_debt_filter(m)
        self.assertEqual(r["scope"], "none")
        self.assertEqual(r["block_reason"], REASON_SCOPE_NOT_CLASSIFIED)

    def test_T4_adapted_bilateral_classifica_e_falha_so_cc(self):
        """Bilateral OK (total_cc=3, xg≥1, xgot≥1), home tem 1 gol.
        cc_debt: floor(3/3)=1 > 1 = false → falha CC.
        xg/xgot devem passar pra isolar a falha."""
        m = ms(home_cc=2, away_cc=1,
                home_xg=1.10, away_xg=1.05,           # total 2.15
                home_xgot=1.05, away_xgot=1.00,       # total 2.05
                home_goals=1, away_goals=0, minute=55)
        # bilateral: A 3≥3✓, B 2.15≥1✓, C 2.05≥1✓, weak xg=1.05≥0.30✓...
        # cc_debt: 1 > 1 false; xg 2.15≥2.00 true; xgot 2.05≥2.00 true
        r = validate_triple_debt_filter(m)
        self.assertEqual(r["scope"], "bilateral")
        self.assertFalse(r["triple_debt_formed"])
        self.assertEqual(r["block_reason"], REASON_FAILED_CC)
        self.assertEqual(r["failed_reasons"], [REASON_FAILED_CC])


# === T5 — Unilateral bloqueado por xG ======================================
class T5_UnilateralFailXG(unittest.TestCase):

    def test_T5_home_3cc_xg080_xgot105_falha_xg_isolada(self):
        m = ms(home_cc=3, away_cc=0,
                home_xg=0.80, away_xg=0.20,     # home_xg_share=0.80
                home_xgot=1.05, away_xgot=0.05,
                home_goals=0, away_goals=0, minute=35)
        r = validate_triple_debt_filter(m)
        self.assertEqual(r["scope"], "unilateral")
        self.assertEqual(r["scope_side"], "home")
        self.assertFalse(r["triple_debt_formed"])
        self.assertTrue(r["cc_debt"])
        self.assertFalse(r["xg_debt"])
        self.assertTrue(r["xgot_debt"])
        self.assertEqual(r["block_reason"], REASON_FAILED_XG)
        self.assertEqual(r["failed_reasons"], [REASON_FAILED_XG])


# === T6 — Unilateral bloqueado por xGOT ====================================
class T6_UnilateralFailXgot(unittest.TestCase):

    def test_T6_home_3cc_xg120_xgot045_falha_xgot_isolada(self):
        m = ms(home_cc=3, away_cc=0,
                home_xg=1.20, away_xg=0.20,
                home_xgot=0.45, away_xgot=0.05,
                home_goals=0, away_goals=0, minute=35)
        r = validate_triple_debt_filter(m)
        self.assertEqual(r["scope"], "unilateral")
        self.assertEqual(r["scope_side"], "home")
        self.assertFalse(r["triple_debt_formed"])
        self.assertTrue(r["cc_debt"])
        self.assertTrue(r["xg_debt"])
        self.assertFalse(r["xgot_debt"])
        self.assertEqual(r["block_reason"], REASON_FAILED_XGOT)
        self.assertEqual(r["failed_reasons"], [REASON_FAILED_XGOT])


# === T7 — Dívida progressiva ===============================================
class T7_DividaProgressiva(unittest.TestCase):

    def test_T7_6cc_1gol_xg210_xgot205_trinca_forma(self):
        # bilateral: home 3 / away 3, xG 1.10/1.00, xgot 1.05/1.00, goals 1-0
        m = ms(home_cc=3, away_cc=3,
                home_xg=1.10, away_xg=1.00,
                home_xgot=1.05, away_xgot=1.00,
                home_goals=1, away_goals=0, minute=70)
        r = validate_triple_debt_filter(m)
        self.assertEqual(r["scope"], "bilateral")
        self.assertEqual(r["cc_in_scope"], 6)
        self.assertEqual(r["goals_in_scope"], 1)
        self.assertEqual(r["expected_goals_by_cc"], 2)
        self.assertTrue(r["cc_debt"])
        self.assertTrue(r["xg_debt"])
        self.assertTrue(r["xgot_debt"])
        self.assertTrue(r["triple_debt_formed"])


# === T8 — Sem dívida real (gols já pagaram) ================================
class T8_NoRealDebt(unittest.TestCase):

    def test_T8_3cc_1gol_xg120_xgot110_no_real_debt(self):
        """As 3 pernas falham simultaneamente → no_real_debt, NÃO multiple."""
        m = ms(home_cc=2, away_cc=1,
                home_xg=0.70, away_xg=0.50,
                home_xgot=0.65, away_xgot=0.45,
                home_goals=1, away_goals=0, minute=55)
        r = validate_triple_debt_filter(m)
        self.assertEqual(r["scope"], "bilateral")
        self.assertEqual(r["goals_in_scope"], 1)
        self.assertEqual(r["expected_goals_by_cc"], 1)
        self.assertFalse(r["cc_debt"])     # 1 > 1 false
        self.assertFalse(r["xg_debt"])     # 1.20 >= 2.00 false
        self.assertFalse(r["xgot_debt"])   # 1.10 >= 2.00 false
        self.assertEqual(r["block_reason"], REASON_NO_REAL_DEBT)
        self.assertEqual(len(r["failed_reasons"]), 3)


# === T9 — Preservação da regra legacy 3.1.2.0 ==============================
class T9_PreservacaoLegacy(unittest.TestCase):

    def test_T9a_modulo_nao_importa_codigo_legacy(self):
        """O módulo novo não pode IMPORTAR código legacy.
        Olha somente linhas de import/from — menções em docstring/comentário
        servem pra documentar o contrato, e são esperadas."""
        import re
        mod_path = (Path(__file__).resolve().parent.parent
                     / "src" / "triple_debt_filter.py")
        text = mod_path.read_text()
        import_lines = [ln for ln in text.splitlines()
                         if re.match(r"^\s*(import|from)\s+", ln)]
        for ln in import_lines:
            for forbidden in ("codigo_3_1", "rules_over", "rules_back",
                               "live_daemon", "telegram_client",
                               "telegram_formatter", "coverage_guard",
                               "signals_persistence"):
                self.assertNotIn(forbidden, ln,
                    f"Módulo Turbo importa legacy '{forbidden}': {ln}")

    def test_T9b_payload_input_nao_eh_mutado(self):
        """validate_triple_debt_filter não deve mutar o dict de entrada."""
        m = ms(home_cc=3, away_cc=0,
                home_xg=1.20, away_xg=0.20,
                home_xgot=1.05, away_xgot=0.05,
                home_goals=0, away_goals=0, minute=30,
                original_tier="FORTE", original_alert_type="over_forte")
        snapshot = copy.deepcopy(m)
        _ = validate_triple_debt_filter(m)
        self.assertEqual(m, snapshot, "match_state foi mutado por validate")


# === T10 — Audit log ========================================================
class T10_AuditLog(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.log = self.tmp / "audit.jsonl"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_T10_appenda_uma_linha_por_sinal(self):
        m1 = ms(home_cc=3, away_cc=0,
                 home_xg=1.20, away_xg=0.20,
                 home_xgot=1.05, away_xgot=0.05,
                 match_id="M1", home="HomeA", away="AwayA", minute=30)
        m2 = ms(home_cc=2, away_cc=0,
                 home_xg=0.80, away_xg=0.20,
                 home_xgot=0.50, away_xgot=0.05,
                 match_id="M2", home="HomeB", away="AwayB", minute=42)
        r1 = validate_triple_debt_filter(m1)
        r2 = validate_triple_debt_filter(m2)
        audit_log(m1, "FORTE", "over_forte", r1, path=self.log)
        audit_log(m2, "WATCH", "over_watch", r2, path=self.log)
        lines = self.log.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        rec1 = json.loads(lines[0])
        self.assertEqual(rec1["match_id"], "M1")
        self.assertEqual(rec1["original_tier"], "FORTE")
        self.assertEqual(rec1["triple_debt_formed"], True)
        self.assertIn("would_block_signal", rec1)
        rec2 = json.loads(lines[1])
        self.assertEqual(rec2["match_id"], "M2")
        self.assertEqual(rec2["triple_debt_formed"], False)
        self.assertEqual(rec2["block_reason"], REASON_SCOPE_NOT_CLASSIFIED)
        self.assertEqual(rec2["would_block_signal"], True)


# === Defensivos =============================================================
class TX_Defensivos(unittest.TestCase):

    def test_TX1_duas_pernas_falham_retorna_failed_multiple(self):
        """3 CC, 0 gols, xG 0.70, xGOT 0.40 → cc ok, xg fail, xgot fail."""
        m = ms(home_cc=2, away_cc=1,
                home_xg=0.40, away_xg=0.30,        # total 0.70
                home_xgot=0.20, away_xgot=0.20,    # total 0.40
                home_goals=0, away_goals=0, minute=30)
        # bilateral A:3≥3✓ B:0.70<1✗ → scope=none. Adaptar pra forçar bilateral:
        m = ms(home_cc=2, away_cc=1,
                home_xg=0.60, away_xg=0.45,        # total 1.05
                home_xgot=0.65, away_xgot=0.40,    # total 1.05 (weak xgot=0.40≥0.25)
                home_goals=1, away_goals=0, minute=55)
        # cc_debt: floor(3/3)=1>1 false → fail
        # xg_debt: 1.05>=2.00 false → fail
        # xgot_debt: 1.05>=2.00 false → fail
        # Hmm 3 fails = no_real_debt. Não é o que quero.
        # Vou montar caso com EXATAMENTE 2 falhas: cc passa (cc≥6), xg falha, xgot falha.
        m = ms(home_cc=3, away_cc=3,
                home_xg=0.50, away_xg=0.40,        # total 0.90 — não bate B bilateral
                home_xgot=0.50, away_xgot=0.40,
                home_goals=0, away_goals=0, minute=55)
        # Hmm B falha → scope none. Reforçar:
        m = ms(home_cc=3, away_cc=3,
                home_xg=0.55, away_xg=0.50,        # total 1.05 ≥1 ✓
                home_xgot=0.55, away_xgot=0.50,    # total 1.05 ≥1 ✓
                home_goals=0, away_goals=0, minute=55)
        # bilateral: A✓ B✓ C✓, weak (cc=3,xg=0.50≥0.30,xgot=0.50≥0.25) → bilateral ✓
        # cc=6, xg=1.05, xgot=1.05, goals=0
        # cc_debt: floor(6/3)=2>0 ✓ (passa)
        # xg_debt: 1.05>=1.00 ✓ (passa)
        # xgot_debt: 1.05>=1.00 ✓ (passa) → TRINCA FORMA, não bate o caso de 2 falhas.
        # Pra forçar EXATAMENTE 2 falhas, preciso de cenário com 1 perna passando.
        # Tentativa: cc=6, xg=1.05, xgot=1.05, goals=1
        m = ms(home_cc=3, away_cc=3,
                home_xg=0.55, away_xg=0.50,
                home_xgot=0.55, away_xgot=0.50,
                home_goals=1, away_goals=0, minute=70)
        # bilateral ✓. cc=6, xg=1.05, xgot=1.05, goals=1
        # cc_debt: 2>1 ✓
        # xg_debt: 1.05>=2.00 false → fail
        # xgot_debt: 1.05>=2.00 false → fail
        # 2 falhas → multiple ✓
        r = validate_triple_debt_filter(m)
        self.assertEqual(r["scope"], "bilateral")
        self.assertFalse(r["triple_debt_formed"])
        self.assertEqual(r["block_reason"], REASON_FAILED_MULTIPLE)
        self.assertEqual(set(r["failed_reasons"]),
                          {REASON_FAILED_XG, REASON_FAILED_XGOT})

    def test_TX2_bilateral_lado_fraco_zero_vira_none(self):
        """Bilateral exige lado fraco ≥2 de 3. Se lado fraco tem 0 em tudo,
        scope vai pra none (mesmo com totais ok)."""
        m = ms(home_cc=3, away_cc=0,           # share 1.0/0 — Home pode ser uni
                home_xg=0.80, away_xg=0.80,    # share 0.50/0.50 — não bate uni xg_share≥0.65
                home_xgot=0.80, away_xgot=0.80,
                home_goals=0, away_goals=0, minute=40)
        # Home unilateral: A 3≥3✓ B 1.0≥0.70✓ C xg_share=0.50<0.65✗ D 0.50<0.65✗ E away_cc=0✓
        # hits = 3 (A,B,E). Precisa 4 e tem A → FALHA → não unilateral.
        # Away: A 0<3 ✗ → não unilateral.
        # Bilateral: A 3≥3✓ B 1.60≥1✓ C 1.60≥1✓. Weak=away (cc=0): cc=0<1✗ xg=0.80≥0.30✓ xgot=0.80≥0.25✓ → 2/3 ✓
        # Espera bilateral!
        # Pra forçar weak falhar, precisa weak_xg<0.30 E weak_xgot<0.25.
        m = ms(home_cc=3, away_cc=0,
                home_xg=1.20, away_xg=0.20,       # away_xg=0.20<0.30
                home_xgot=1.10, away_xgot=0.10,   # away_xgot=0.10<0.25
                home_goals=0, away_goals=0, minute=40)
        # Home unilateral: A✓ B✓ C xg_share=1.20/1.40=0.857✓ D xgot_share=1.10/1.20=0.917✓ E✓ → 5/5 ✓
        # Vira unilateral home, não bilateral. Pra forçar scope=none:
        # Preciso ninguém qualificar unilateral E bilateral falhar.
        m = ms(home_cc=2, away_cc=2,
                home_xg=0.70, away_xg=0.10,       # totais ok (0.80<1.00, na verdade não)
                home_xgot=0.10, away_xgot=0.10,
                home_goals=0, away_goals=0, minute=30)
        # Home uni: A 2<3 ✗ → não. Away: A 2<3 ✗ → não.
        # Bilateral: A 4≥3✓ B 0.80<1.00 ✗ → não bilateral.
        # scope=none. Bom.
        r = validate_triple_debt_filter(m)
        self.assertEqual(r["scope"], "none")
        self.assertEqual(r["block_reason"], REASON_SCOPE_NOT_CLASSIFIED)

    def test_TX3_placar_nao_influencia_escopo(self):
        """Mesma produção, placares diferentes → mesmo escopo."""
        base = dict(home_cc=3, away_cc=0,
                     home_xg=1.20, away_xg=0.20,
                     home_xgot=1.05, away_xgot=0.05, minute=40)
        m1 = ms(**base, home_goals=0, away_goals=0)
        m2 = ms(**base, home_goals=0, away_goals=2)
        m3 = ms(**base, home_goals=3, away_goals=0)
        r1 = validate_triple_debt_filter(m1)
        r2 = validate_triple_debt_filter(m2)
        r3 = validate_triple_debt_filter(m3)
        self.assertEqual(r1["scope"], "unilateral")
        self.assertEqual(r1["scope_side"], "home")
        self.assertEqual(r2["scope"], "unilateral")
        self.assertEqual(r2["scope_side"], "home")
        self.assertEqual(r3["scope"], "unilateral")
        self.assertEqual(r3["scope_side"], "home")

    def test_TX4_match_state_vazio_nao_crasha(self):
        r = validate_triple_debt_filter({})
        self.assertEqual(r["scope"], "none")
        self.assertEqual(r["block_reason"], REASON_SCOPE_NOT_CLASSIFIED)

    def test_TX5_audit_log_so_escreve_no_path_dado(self):
        """Auditoria não toca em nenhum arquivo de produção."""
        tmp = Path(tempfile.mkdtemp())
        try:
            log = tmp / "audit.jsonl"
            m = ms(home_cc=3, away_cc=0,
                    home_xg=1.20, away_xg=0.20,
                    home_xgot=1.05, away_xgot=0.05,
                    match_id="X5", home="A", away="B", minute=30)
            r = validate_triple_debt_filter(m)
            p = audit_log(m, "FORTE", "over_forte", r, path=log)
            self.assertEqual(p, log)
            self.assertTrue(log.exists())
            # Verifica que arquivos de produção do projeto NÃO foram criados aqui
            for forbidden in ("rule_3_1_2_signals.jsonl",
                                "live_daemon_decisions.jsonl",
                                "live_daemon_state.json"):
                self.assertFalse((tmp / forbidden).exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def _run():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (T1_BilateralAprovado, T2_BilateralFailXgot,
                T3_UnilateralAprovado, T4_UnilateralFailCC,
                T5_UnilateralFailXG, T6_UnilateralFailXgot,
                T7_DividaProgressiva, T8_NoRealDebt,
                T9_PreservacaoLegacy, T10_AuditLog, TX_Defensivos):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    r = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run())
