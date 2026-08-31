"""
Testes do banco estruturado da Regra 3.1.2.0 (src/signals_persistence.py).

Cobertura dos critérios A-O exigidos pelo dossiê v2.7:

  A. WATCH repetido no mesmo match+type+bucket salva só 1 vez
  B. WATCH em bucket novo gera registro separado
  C. WATCH e FORTE no mesmo bucket coexistem como registros diferentes
  D. FORTE/PREMIUM continuam salvando normalmente
  E. Política Telegram preservada (WATCH=False, FORTE/PREMIUM=True)
  F. Registro contém league_name/country/premium_level
  G. Registro contém minuto/placar/CC/rate/xG
  H. Novo scan posterior atualiza last_seen_score
  I. Gol posterior é detectado corretamente
  J. Gol em 10/20/30min é detectado corretamente
  K. BACK detecta dominant_scored / dominant_improved
  L. Jogo finalizado preenche placar final + result_finalized
  M. Coverage Guard não escreve aqui (separação de módulo)
  N. V1.2 não escreve aqui
  O. Script de análise lê o JSONL e gera relatório sem duplicidade
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.signals_persistence import (
    build_signal_record, record_signal, update_signal_observations,
    finalize_signals_for_match, load_all, has_signal, signal_key,
    LEVEL_BY_TYPE, MARKET_BY_TYPE, WATCH_TYPES,
)


def _mk_record(**overrides):
    base = dict(
        match_id="FS_test", url="http://x/jogo/futebol/a-AAAAAA/b-BBBBBB/?mid=test",
        home="Casa", away="Visitante",
        alert_type="over_watch", bucket=1,
        minute_at_alert=30, status_raw="",
        home_score=0, away_score=0,
        home_bc=1, away_bc=2,
        total_cc=3, cc_rate=10.0,
        expected_goals_by_cc=1,
        home_xgot=0.5, away_xgot=0.8,
        league_name="Brasileirão Betano", country="Brasil",
        premium_level="A",
        premium_reason="flashscore_highlighted_league",
        telegram_sent=False,
    )
    base.update(overrides)
    return build_signal_record(**base)


def _tmp_jsonl():
    return Path(tempfile.mkdtemp()) / "signals.jsonl"


# ──────────────────────────────────────────────────────────────────────
# A — Dedup: WATCH repetido no mesmo match+type+bucket → 1 registro
# ──────────────────────────────────────────────────────────────────────

class TestA_DedupWatch(unittest.TestCase):

    def test_A1_mesmo_watch_mesmo_bucket_grava_uma_vez(self):
        p = _tmp_jsonl()
        # 14 ciclos como o caso Libertad × Universidad Central
        for minute in range(30, 58, 2):
            rec = _mk_record(match_id="FS_libcen",
                              alert_type="over_watch", bucket=1,
                              minute_at_alert=minute)
            record_signal(rec, p)
        all_recs = load_all(p)
        self.assertEqual(len(all_recs), 1,
                          f"Esperado 1 registro, achei {len(all_recs)}")
        # E o ÚNICO gravado deve ser o primeiro (minuto 30)
        self.assertEqual(all_recs[0]["minute_at_alert"], 30)


# ──────────────────────────────────────────────────────────────────────
# B — Bucket novo gera novo registro
# ──────────────────────────────────────────────────────────────────────

class TestB_NewBucket(unittest.TestCase):

    def test_B1_watch_bucket_1_e_bucket_2_geram_2_registros(self):
        p = _tmp_jsonl()
        record_signal(_mk_record(match_id="FS_x", alert_type="over_watch", bucket=1), p)
        record_signal(_mk_record(match_id="FS_x", alert_type="over_watch", bucket=2,
                                   minute_at_alert=60, home_bc=2, away_bc=4, total_cc=6), p)
        self.assertEqual(len(load_all(p)), 2)


# ──────────────────────────────────────────────────────────────────────
# C — WATCH + FORTE no mesmo bucket coexistem
# ──────────────────────────────────────────────────────────────────────

class TestC_WatchAndForteCoexist(unittest.TestCase):

    def test_C1_watch_e_forte_mesmo_bucket(self):
        p = _tmp_jsonl()
        record_signal(_mk_record(match_id="FS_x", alert_type="over_watch", bucket=1), p)
        record_signal(_mk_record(match_id="FS_x", alert_type="over_forte", bucket=1,
                                   minute_at_alert=45), p)
        recs = load_all(p)
        types = sorted(r["alert_type"] for r in recs)
        self.assertEqual(types, ["over_forte", "over_watch"])


# ──────────────────────────────────────────────────────────────────────
# D — FORTE/PREMIUM continuam salvando
# ──────────────────────────────────────────────────────────────────────

class TestD_FortePremiumGravam(unittest.TestCase):

    def test_D1_todos_os_8_tipos_gravam(self):
        p = _tmp_jsonl()
        for at in ("over_watch","back_watch","over_forte","back_forte",
                   "over_premium","back_premium","over_premium_xg",
                   "over_bilateral_premium"):
            record_signal(_mk_record(match_id=f"FS_{at}", alert_type=at,
                                       home_bc=3, away_bc=1), p)
        self.assertEqual(len(load_all(p)), 8)


# ──────────────────────────────────────────────────────────────────────
# E — Política Telegram preservada
# ──────────────────────────────────────────────────────────────────────

class TestE_TelegramPolicy(unittest.TestCase):

    def test_E1_watch_eh_is_watch_only_true_telegram_false(self):
        rec = _mk_record(alert_type="over_watch", telegram_sent=False)
        self.assertTrue(rec["is_watch_only"])
        self.assertFalse(rec["telegram_sent"])
        # E o módulo não envia TG — não importa telegram_client
        import src.signals_persistence as sp
        import inspect
        src = inspect.getsource(sp)
        self.assertNotIn("telegram_client", src)
        self.assertNotIn("send_text", src)
        self.assertNotIn("_send_raw", src)

    def test_E2_forte_eh_is_watch_only_false_telegram_pode_True(self):
        rec = _mk_record(alert_type="over_forte", telegram_sent=True)
        self.assertFalse(rec["is_watch_only"])
        self.assertTrue(rec["telegram_sent"])


# ──────────────────────────────────────────────────────────────────────
# F — Campos identificação/liga
# ──────────────────────────────────────────────────────────────────────

class TestF_CamposIdentificacao(unittest.TestCase):

    def test_F1_record_tem_league_country_premium_level(self):
        rec = _mk_record(league_name="Premier League", country="Inglaterra",
                          premium_level="A")
        self.assertEqual(rec["league_name"], "Premier League")
        self.assertEqual(rec["country"], "Inglaterra")
        self.assertEqual(rec["premium_level"], "A")
        self.assertIn("signal_id", rec)
        self.assertIn("timestamp_alert_utc", rec)
        self.assertIn("url", rec)


# ──────────────────────────────────────────────────────────────────────
# G — Estado do jogo no alerta
# ──────────────────────────────────────────────────────────────────────

class TestG_EstadoNoAlerta(unittest.TestCase):

    def test_G1_record_tem_minuto_placar_cc_rate_xg(self):
        rec = _mk_record(minute_at_alert=58, home_score=1, away_score=0,
                          home_bc=2, away_bc=3, total_cc=5,
                          cc_rate=11.6, expected_goals_by_cc=1,
                          home_xgot=0.7, away_xgot=1.2)
        self.assertEqual(rec["minute_at_alert"], 58)
        self.assertEqual(rec["home_score_at_alert"], 1)
        self.assertEqual(rec["away_score_at_alert"], 0)
        self.assertEqual(rec["total_goals_at_alert"], 1)
        self.assertEqual(rec["home_bc_at_alert"], 2)
        self.assertEqual(rec["away_bc_at_alert"], 3)
        self.assertEqual(rec["total_bc_at_alert"], 5)
        self.assertAlmostEqual(rec["cc_rate_at_alert"], 11.6)
        self.assertEqual(rec["expected_goals_by_cc_at_alert"], 1)
        self.assertAlmostEqual(rec["home_xgot_at_alert"], 0.7)
        self.assertAlmostEqual(rec["away_xgot_at_alert"], 1.2)


# ──────────────────────────────────────────────────────────────────────
# H — Updates de last_seen
# ──────────────────────────────────────────────────────────────────────

class TestH_UpdateLastSeen(unittest.TestCase):

    def test_H1_update_atualiza_last_seen(self):
        p = _tmp_jsonl()
        record_signal(_mk_record(match_id="FS_h", minute_at_alert=30,
                                   home_score=0, away_score=0), p)
        update_signal_observations("FS_h", current_minute=45,
                                     current_home_score=0, current_away_score=1,
                                     persist_path=p)
        rec = load_all(p)[0]
        self.assertEqual(rec["last_seen_minute"], 45)
        self.assertEqual(rec["last_seen_score"], "0-1")


# ──────────────────────────────────────────────────────────────────────
# I — Gol posterior detectado
# ──────────────────────────────────────────────────────────────────────

class TestI_GolPosterior(unittest.TestCase):

    def test_I1_gol_after_alert_detectado(self):
        p = _tmp_jsonl()
        record_signal(_mk_record(match_id="FS_i", minute_at_alert=30,
                                   home_score=0, away_score=0), p)
        # Nenhum gol ainda
        update_signal_observations("FS_i", current_minute=40,
                                     current_home_score=0, current_away_score=0,
                                     persist_path=p)
        self.assertFalse(load_all(p)[0]["goal_after_alert"])
        # Gol entra
        update_signal_observations("FS_i", current_minute=55,
                                     current_home_score=1, current_away_score=0,
                                     persist_path=p)
        self.assertTrue(load_all(p)[0]["goal_after_alert"])


# ──────────────────────────────────────────────────────────────────────
# J — Janelas 10/20/30min
# ──────────────────────────────────────────────────────────────────────

class TestJ_JanelasTemporais(unittest.TestCase):

    def test_J1_gol_dentro_de_10_min(self):
        p = _tmp_jsonl()
        record_signal(_mk_record(match_id="FS_j1", minute_at_alert=30), p)
        # Gol no min 38 (+8min)
        update_signal_observations("FS_j1", current_minute=38,
                                     current_home_score=1, current_away_score=0,
                                     persist_path=p)
        r = load_all(p)[0]
        self.assertTrue(r["goal_within_10m"])
        self.assertTrue(r["goal_within_20m"])
        self.assertTrue(r["goal_within_30m"])

    def test_J2_gol_apenas_em_25_min(self):
        p = _tmp_jsonl()
        record_signal(_mk_record(match_id="FS_j2", minute_at_alert=30), p)
        update_signal_observations("FS_j2", current_minute=55,
                                     current_home_score=1, current_away_score=0,
                                     persist_path=p)
        r = load_all(p)[0]
        self.assertFalse(r["goal_within_10m"])
        self.assertFalse(r["goal_within_20m"])
        self.assertTrue(r["goal_within_30m"])


# ──────────────────────────────────────────────────────────────────────
# K — BACK: dominante marcou / melhorou
# ──────────────────────────────────────────────────────────────────────

class TestK_BackDominante(unittest.TestCase):

    def test_K1_dominante_home_marca_apos(self):
        p = _tmp_jsonl()
        record_signal(_mk_record(match_id="FS_k1", alert_type="back_watch",
                                   home_bc=4, away_bc=0, minute_at_alert=60,
                                   home_score=0, away_score=0), p)
        update_signal_observations("FS_k1", current_minute=75,
                                     current_home_score=1, current_away_score=0,
                                     persist_path=p)
        r = load_all(p)[0]
        self.assertEqual(r["dominant_side"], "home")
        self.assertTrue(r["dominant_scored_after_alert"])
        self.assertTrue(r["dominant_improved_score"])

    def test_K2_dominante_away_marca_apos(self):
        p = _tmp_jsonl()
        record_signal(_mk_record(match_id="FS_k2", alert_type="back_watch",
                                   home_bc=1, away_bc=5, minute_at_alert=60,
                                   home_score=0, away_score=0), p)
        update_signal_observations("FS_k2", current_minute=85,
                                     current_home_score=0, current_away_score=1,
                                     persist_path=p)
        r = load_all(p)[0]
        self.assertEqual(r["dominant_side"], "away")
        self.assertTrue(r["dominant_scored_after_alert"])
        self.assertTrue(r["dominant_improved_score"])

    def test_K3_oponente_marcou_dominante_nao_melhorou(self):
        p = _tmp_jsonl()
        record_signal(_mk_record(match_id="FS_k3", alert_type="back_watch",
                                   home_bc=4, away_bc=0, minute_at_alert=60), p)
        update_signal_observations("FS_k3", current_minute=80,
                                     current_home_score=0, current_away_score=1,
                                     persist_path=p)
        r = load_all(p)[0]
        self.assertFalse(r["dominant_scored_after_alert"])
        self.assertFalse(r["dominant_improved_score"])


# ──────────────────────────────────────────────────────────────────────
# L — Finalização: placar final + result_finalized
# ──────────────────────────────────────────────────────────────────────

class TestL_Finalize(unittest.TestCase):

    def test_L1_finalize_seta_placar_final_over_15_25(self):
        p = _tmp_jsonl()
        record_signal(_mk_record(match_id="FS_l", minute_at_alert=30,
                                   home_score=0, away_score=0), p)
        finalize_signals_for_match("FS_l", final_home_score=2, final_away_score=1,
                                     final_minute=92, reason="FINISHED_MATCH",
                                     persist_path=p)
        r = load_all(p)[0]
        self.assertEqual(r["final_total_goals"], 3)
        self.assertTrue(r["over_1_5_result"])
        self.assertTrue(r["over_2_5_result"])
        self.assertTrue(r["result_finalized"])
        self.assertTrue(r["result_auditable"])

    def test_L2_finalize_back_dominante_won(self):
        p = _tmp_jsonl()
        record_signal(_mk_record(match_id="FS_l2", alert_type="back_watch",
                                   home_bc=4, away_bc=0, minute_at_alert=60), p)
        finalize_signals_for_match("FS_l2", final_home_score=2, final_away_score=0,
                                     final_minute=92, reason="FINISHED_MATCH",
                                     persist_path=p)
        r = load_all(p)[0]
        self.assertTrue(r["dominant_won"])
        self.assertTrue(r["dominant_not_lost"])

    def test_L3_finalize_back_dominante_perdeu(self):
        p = _tmp_jsonl()
        record_signal(_mk_record(match_id="FS_l3", alert_type="back_watch",
                                   home_bc=4, away_bc=0, minute_at_alert=60), p)
        finalize_signals_for_match("FS_l3", final_home_score=0, final_away_score=2,
                                     final_minute=92, reason="FINISHED_MATCH",
                                     persist_path=p)
        r = load_all(p)[0]
        self.assertFalse(r["dominant_won"])
        self.assertFalse(r["dominant_not_lost"])


# ──────────────────────────────────────────────────────────────────────
# M — Coverage Guard não escreve aqui
# ──────────────────────────────────────────────────────────────────────

class TestM_CoverageGuardSeparate(unittest.TestCase):

    def test_M1_signals_persistence_nao_eh_chamado_por_coverage_guard(self):
        import src.coverage_guard as cg
        import inspect
        src = inspect.getsource(cg)
        self.assertNotIn("signals_persistence", src)
        self.assertNotIn("rule_3_1_2_signals", src)

    def test_M2_signals_persistence_nao_importa_coverage_guard(self):
        import src.signals_persistence as sp
        import inspect
        src = inspect.getsource(sp)
        self.assertNotIn("coverage_guard", src)


# ──────────────────────────────────────────────────────────────────────
# N — V1.2 não entra nesse banco
# ──────────────────────────────────────────────────────────────────────

class TestN_NoV12(unittest.TestCase):

    def test_N1_apenas_tipos_da_regra_3_1_2_sao_aceitos(self):
        # LEVEL_BY_TYPE só tem os 8 tipos oficiais da Regra 3.1.2.0
        valid_types = {"over_watch","back_watch","over_forte","back_forte",
                       "over_premium","back_premium","over_premium_xg",
                       "over_bilateral_premium"}
        self.assertEqual(set(LEVEL_BY_TYPE.keys()), valid_types)
        # Tipos V1.2 ("main","unilateral") não estão
        self.assertNotIn("main", LEVEL_BY_TYPE)
        self.assertNotIn("unilateral", LEVEL_BY_TYPE)


# ──────────────────────────────────────────────────────────────────────
# O — Script de análise lê sem duplicidade
# ──────────────────────────────────────────────────────────────────────

class TestO_AnalysisScript(unittest.TestCase):

    def test_O1_script_le_jsonl_e_conta_sem_duplicidade(self):
        p = _tmp_jsonl()
        # 5 jogos, vários ciclos por jogo: 1 sinal único cada
        for mid in ("FS_o1","FS_o2","FS_o3","FS_o4","FS_o5"):
            # 10 tentativas de gravar o mesmo WATCH
            for _ in range(10):
                record_signal(_mk_record(match_id=mid, alert_type="over_watch",
                                          bucket=1), p)
        recs = load_all(p)
        self.assertEqual(len(recs), 5)
        # has_signal funciona
        self.assertTrue(has_signal("FS_o1", "over_watch", 1, p))
        self.assertFalse(has_signal("FS_o1", "back_watch", 1, p))


class TestV28_TelegramDedupPolicy(unittest.TestCase):
    """v2.8 — Política integrada Telegram + dedup pelo banco limpo.

    Reproduz a lógica exata do hook em live_daemon.py:
      1. has_signal(match_id, alert_type, bucket) decide se envia TG
      2. Se já gravado → não envia + não regrava
      3. Se novo → envia + grava

    Critérios A-J do dossiê v2.8.
    """

    def setUp(self):
        from unittest.mock import MagicMock
        self.db = _tmp_jsonl()
        self.tg = MagicMock()
        self.tg.is_ready = MagicMock(return_value=True)
        self.tg._send_raw = MagicMock(return_value=True)

    def _dispatch(self, *, match_id, alert_type, bucket, **rec_kwargs):
        """Reproduz o caminho live_daemon: has_signal → send_alert → record."""
        from src.signals_persistence import has_signal, record_signal
        # Mock de codigo_3_1.send_alert (não precisa importar real aqui pra esses testes)
        already = has_signal(match_id, alert_type, bucket, self.db)
        sent = False
        if not already:
            # Simula codigo_3_1.send_alert chamando tg._send_raw
            self.tg._send_raw(f"[{alert_type}] mensagem")
            sent = True
            rec = _mk_record(match_id=match_id, alert_type=alert_type,
                              bucket=bucket, **rec_kwargs)
            record_signal(rec, self.db)
        return already, sent

    # ─── A: over_watch primeira vez no bucket 1 ─────────────────────

    def test_A_over_watch_first_envia(self):
        already, sent = self._dispatch(match_id="FS_a", alert_type="over_watch",
                                        bucket=1)
        self.assertFalse(already)
        self.assertTrue(sent)
        self.assertEqual(self.tg._send_raw.call_count, 1)

    # ─── B: over_watch repetido mesmo bucket → NÃO envia ────────────

    def test_B_over_watch_repetido_nao_envia(self):
        self._dispatch(match_id="FS_b", alert_type="over_watch", bucket=1)
        self.tg._send_raw.reset_mock()
        # 5 repetições
        for _ in range(5):
            already, sent = self._dispatch(match_id="FS_b",
                                            alert_type="over_watch", bucket=1)
            self.assertTrue(already)
            self.assertFalse(sent)
        self.tg._send_raw.assert_not_called()
        # Banco continua com 1 só
        self.assertEqual(len(load_all(self.db)), 1)

    # ─── C: back_watch primeira vez ─────────────────────────────────

    def test_C_back_watch_first_envia(self):
        already, sent = self._dispatch(match_id="FS_c", alert_type="back_watch",
                                        bucket=1, home_bc=3, away_bc=0)
        self.assertTrue(sent)
        self.tg._send_raw.assert_called_once()

    # ─── D: back_watch repetido mesmo bucket → NÃO envia ────────────

    def test_D_back_watch_repetido_nao_envia(self):
        self._dispatch(match_id="FS_d", alert_type="back_watch", bucket=1,
                        home_bc=3, away_bc=0)
        self.tg._send_raw.reset_mock()
        already, sent = self._dispatch(match_id="FS_d",
                                        alert_type="back_watch", bucket=1,
                                        home_bc=3, away_bc=0)
        self.assertTrue(already)
        self.assertFalse(sent)
        self.tg._send_raw.assert_not_called()

    # ─── E: WATCH em bucket NOVO → envia ────────────────────────────

    def test_E_watch_bucket_novo_envia_novamente(self):
        self._dispatch(match_id="FS_e", alert_type="over_watch", bucket=1)
        self.tg._send_raw.reset_mock()
        # Bucket 2 — nova chave
        already, sent = self._dispatch(match_id="FS_e",
                                        alert_type="over_watch", bucket=2,
                                        minute_at_alert=60, home_bc=2, away_bc=4)
        self.assertFalse(already)
        self.assertTrue(sent)
        self.tg._send_raw.assert_called_once()
        self.assertEqual(len(load_all(self.db)), 2)

    # ─── F: WATCH seguido de FORTE mesmo bucket → ambos enviam ──────

    def test_F_watch_then_forte_mesmo_bucket(self):
        a1, s1 = self._dispatch(match_id="FS_f", alert_type="over_watch",
                                 bucket=1)
        self.assertTrue(s1)
        # Evolui pra FORTE no mesmo bucket — alert_type diferente, chave nova
        a2, s2 = self._dispatch(match_id="FS_f", alert_type="over_forte",
                                 bucket=1, home_bc=3, away_bc=1)
        self.assertFalse(a2)
        self.assertTrue(s2)
        # 2 envios totais (1 WATCH + 1 FORTE)
        self.assertEqual(self.tg._send_raw.call_count, 2)
        # 2 registros
        recs = load_all(self.db)
        self.assertEqual(len(recs), 2)
        types = sorted(r["alert_type"] for r in recs)
        self.assertEqual(types, ["over_forte", "over_watch"])

    # ─── G: WATCH seguido de PREMIUM → ambos enviam ─────────────────

    def test_G_watch_then_premium_mesmo_bucket(self):
        self._dispatch(match_id="FS_g", alert_type="over_watch", bucket=2)
        self._dispatch(match_id="FS_g", alert_type="over_bilateral_premium",
                        bucket=2, home_bc=3, away_bc=3, minute_at_alert=85)
        self.assertEqual(self.tg._send_raw.call_count, 2)
        self.assertEqual(len(load_all(self.db)), 2)

    # ─── H: Coverage Guard continua sem Telegram ────────────────────

    def test_H_coverage_guard_continua_sem_telegram(self):
        from src.operational_config import coverage_guard_telegram_enabled
        os.environ.pop("TECHNICAL_TELEGRAM_ENABLED", None)
        self.assertFalse(coverage_guard_telegram_enabled())

    # ─── I: Supervisor técnico continua sem Telegram ────────────────

    def test_I_supervisor_tecnico_continua_sem_telegram(self):
        from src.operational_config import supervisor_telegram_enabled
        os.environ.pop("TECHNICAL_TELEGRAM_ENABLED", None)
        self.assertFalse(supervisor_telegram_enabled())

    # ─── J: Banco limpo NÃO duplica WATCH ───────────────────────────

    def test_J_banco_limpo_nao_duplica(self):
        # 14 repetições do mesmo WATCH em diferentes minutos
        for minute in range(30, 58, 2):
            self._dispatch(match_id="FS_j", alert_type="over_watch", bucket=1,
                            minute_at_alert=minute)
        # 1 envio + 1 registro
        self.assertEqual(self.tg._send_raw.call_count, 1)
        self.assertEqual(len(load_all(self.db)), 1)


def _run():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (TestA_DedupWatch, TestB_NewBucket, TestC_WatchAndForteCoexist,
                TestD_FortePremiumGravam, TestE_TelegramPolicy,
                TestF_CamposIdentificacao, TestG_EstadoNoAlerta,
                TestH_UpdateLastSeen, TestI_GolPosterior,
                TestJ_JanelasTemporais, TestK_BackDominante,
                TestL_Finalize, TestM_CoverageGuardSeparate,
                TestN_NoV12, TestO_AnalysisScript,
                TestV28_TelegramDedupPolicy):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    return 0 if runner.run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run())
