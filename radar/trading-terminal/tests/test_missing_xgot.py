"""
Testes do bug "xGOT=0.00 indevido" — distinguir ausente do feed vs zero real.

T1. Parser do Flashscore retorna None quando o label não existe nos stats.
T2. Parser retorna 0.0 (não None) quando o label existe e valor é "0".
T3. MatchState propaga None até o TRINCA via campos _raw.
T4. TRINCA bloqueia com triple_debt_missing_xgot quando xgot_raw=None.
T5. TRINCA distingue missing_xgot de failed_xgot (não confunde).
T6. Daemon NÃO transforma None em 0.00 no display (mostra N/A).
T7. Near miss registra near_miss_type=missing_xgot quando dado ausente.
T8. Nenhum sinal Telegram quando xGOT obrigatório está ausente.

Roda: python3 tests/test_missing_xgot.py
"""
import io
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy_token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "dummy_chat")

if "playwright" not in sys.modules:
    _pw = types.ModuleType("playwright")
    _pws = types.ModuleType("playwright.sync_api")
    class _Dummy: pass
    _pws.sync_playwright = lambda: _Dummy()
    _pws.Page = _Dummy
    _pws.BrowserContext = _Dummy
    sys.modules["playwright"] = _pw
    sys.modules["playwright.sync_api"] = _pws

import live_daemon  # noqa: E402
from src.models import MatchState, Decision  # noqa: E402
from src.flashscore_adapter import FlashscoreReader  # noqa: E402
from src.triple_debt_filter import (  # noqa: E402
    validate_triple_debt_filter,
    REASON_MISSING_XGOT, REASON_FAILED_XGOT, REASON_FAILED_MULTIPLE,
)
from src import turbo_enforcement as TE  # noqa: E402
from src import triple_debt_filter as TDF  # noqa: E402


# === T1, T2 — Parser =====================================================
class T1_T2_ParserDistingueAusenteDeZero(unittest.TestCase):

    def setUp(self):
        # Não precisa do playwright real — instanciar com cfg mínimo
        self.r = FlashscoreReader(headless=True)

    def test_T1_get_stat_float_or_none_retorna_None_quando_ausente(self):
        # Label não existe nos stats → None
        stats = {"Possessão": {"h": "55%", "a": "45%"}}
        v = self.r._get_stat_float_or_none(
            stats, ["xG on target (xGOT)", "xGOT"], "h")
        self.assertIsNone(v, "Label ausente deveria retornar None, não 0.0")

    def test_T1b_get_stat_float_or_none_retorna_None_quando_valor_vazio(self):
        stats = {"xGOT": {"h": "", "a": "  "}}
        self.assertIsNone(self.r._get_stat_float_or_none(stats, ["xGOT"], "h"))
        self.assertIsNone(self.r._get_stat_float_or_none(stats, ["xGOT"], "a"))

    def test_T2_get_stat_float_or_none_retorna_zero_real(self):
        # Label existe e valor é "0" ou "0.00" → 0.0 (zero real)
        stats = {"xGOT": {"h": "0.00", "a": "0"}}
        self.assertEqual(self.r._get_stat_float_or_none(stats, ["xGOT"], "h"), 0.0)
        self.assertEqual(self.r._get_stat_float_or_none(stats, ["xGOT"], "a"), 0.0)

    def test_T2b_get_stat_float_or_none_retorna_valor_positivo(self):
        stats = {"xGOT": {"h": "1.23", "a": "0.45"}}
        self.assertAlmostEqual(self.r._get_stat_float_or_none(stats, ["xGOT"], "h"), 1.23)
        self.assertAlmostEqual(self.r._get_stat_float_or_none(stats, ["xGOT"], "a"), 0.45)

    def test_T2c_get_stat_int_or_none_caso_int(self):
        stats = {"Big chances": {"h": "3", "a": "1"}}
        self.assertEqual(self.r._get_stat_int_or_none(stats, ["Big chances"], "h"), 3)
        self.assertEqual(self.r._get_stat_int_or_none(stats, ["Big chances"], "a"), 1)
        stats2 = {}
        self.assertIsNone(self.r._get_stat_int_or_none(stats2, ["Big chances"], "h"))

    def test_T2d_legacy_get_stat_float_ainda_retorna_zero_quando_ausente(self):
        """Backward compat: o método antigo continua retornando 0.0 pra não
        quebrar a regra legacy."""
        stats = {}
        self.assertEqual(self.r._get_stat_float(stats, ["xGOT"], "h"), 0.0)


# === T3 — MatchState propaga None =========================================
class T3_MatchStatePropaga(unittest.TestCase):

    def test_T3_match_state_aceita_None_em_raw(self):
        ms = MatchState(match_id="X", home="A", away="B",
                          home_xgot=0.0, away_xgot=0.0,
                          home_xgot_raw=None, away_xgot_raw=None)
        self.assertIsNone(ms.home_xgot_raw)
        self.assertIsNone(ms.away_xgot_raw)
        # Legacy continua sendo 0.0 (não None)
        self.assertEqual(ms.home_xgot, 0.0)


# === T4, T5 — TRINCA bloqueia missing_xgot e distingue de failed_xgot =====
class T4_T5_TrincaMissingVsFailed(unittest.TestCase):

    def test_T4_TRINCA_bloqueia_missing_xgot_quando_raw_None(self):
        match_state = {
            "home_cc": 3, "away_cc": 0,
            "home_xg": 1.20, "away_xg": 0.20,
            "home_xgot": 0.0, "away_xgot": 0.0,    # legacy fallback
            "home_xgot_raw": None,                   # AUSENTE
            "away_xgot_raw": None,                   # AUSENTE
            "home_goals": 0, "away_goals": 0,
        }
        r = validate_triple_debt_filter(match_state)
        self.assertEqual(r["block_reason"], REASON_MISSING_XGOT)
        self.assertTrue(r["would_block_signal"])
        self.assertFalse(r["triple_debt_formed"])

    def test_T5_TRINCA_distingue_missing_de_failed(self):
        # Caso A: dado ausente → missing_xgot
        ms_missing = {
            "home_cc": 3, "away_cc": 0,
            "home_xg": 1.20, "away_xg": 0.20,
            "home_xgot": 0.0, "away_xgot": 0.0,
            "home_xgot_raw": None, "away_xgot_raw": None,
            "home_goals": 0, "away_goals": 0,
        }
        r_missing = validate_triple_debt_filter(ms_missing)
        self.assertEqual(r_missing["block_reason"], REASON_MISSING_XGOT)

        # Caso B: dado real, mas xGOT real 0.45 < 1.00 → failed_xgot
        ms_failed = {
            "home_cc": 3, "away_cc": 0,
            "home_xg": 1.20, "away_xg": 0.20,
            "home_xgot": 0.45, "away_xgot": 0.05,
            "home_xgot_raw": 0.45, "away_xgot_raw": 0.05,
            "home_goals": 0, "away_goals": 0,
        }
        r_failed = validate_triple_debt_filter(ms_failed)
        self.assertEqual(r_failed["block_reason"], REASON_FAILED_XGOT)

        # Os dois NÃO podem coincidir
        self.assertNotEqual(r_missing["block_reason"], r_failed["block_reason"])

    def test_T5b_TRINCA_zero_real_xgot_nao_eh_missing(self):
        """Quando o feed informa explicitamente xgot=0.0 (raw=0.0, não None),
        TRINCA usa o valor como zero real — pode falhar como failed_xgot,
        mas NUNCA como missing_xgot."""
        match_state = {
            "home_cc": 3, "away_cc": 0,
            "home_xg": 1.20, "away_xg": 0.20,
            "home_xgot": 0.0, "away_xgot": 0.0,
            "home_xgot_raw": 0.0, "away_xgot_raw": 0.0,    # zero REAL
            "home_goals": 0, "away_goals": 0,
        }
        r = validate_triple_debt_filter(match_state)
        self.assertNotEqual(r["block_reason"], REASON_MISSING_XGOT,
            "Zero real foi confundido com ausência")
        # Deve falhar como failed_xgot (ou multiple, dependendo de outras pernas)
        self.assertIn(r["block_reason"],
            (REASON_FAILED_XGOT, REASON_FAILED_MULTIPLE,
              "triple_debt_no_real_debt"))


# === T6 — Daemon não transforma None em 0.00 (display) ====================
class T6_DaemonDisplay(unittest.TestCase):

    def test_T6a_fmt_metric_retorna_NA_quando_raw_None(self):
        ms = MatchState(home="H", away="A",
                          home_xgot=0.0, away_xgot=0.0,
                          home_xgot_raw=None, away_xgot_raw=None)
        self.assertEqual(live_daemon._fmt_metric(ms, "home_xgot_raw", "home_xgot"),
                          "N/A")

    def test_T6b_fmt_metric_retorna_zero_quando_raw_zero_real(self):
        ms = MatchState(home="H", away="A",
                          home_xgot=0.0, away_xgot=0.0,
                          home_xgot_raw=0.0, away_xgot_raw=0.0)
        self.assertEqual(live_daemon._fmt_metric(ms, "home_xgot_raw", "home_xgot"),
                          "0.00")

    def test_T6c_fmt_metric_retorna_valor_real_quando_presente(self):
        ms = MatchState(home="H", away="A",
                          home_xgot=1.23, away_xgot=0.45,
                          home_xgot_raw=1.23, away_xgot_raw=0.45)
        self.assertEqual(live_daemon._fmt_metric(ms, "home_xgot_raw", "home_xgot"),
                          "1.23")


# === T7, T8 — Near miss + Telegram bloqueado ==============================
class T7_T8_NearMissEBloqueio(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (TE.NEAR_MISS_LOG_PATH,
                       TE.APPROVED_SIGNALS_LOG_PATH,
                       TDF.AUDIT_LOG_PATH)
        TE.NEAR_MISS_LOG_PATH = self.tmp / "near.jsonl"
        TE.APPROVED_SIGNALS_LOG_PATH = self.tmp / "approved.jsonl"
        TDF.AUDIT_LOG_PATH = self.tmp / "tdf.jsonl"

    def tearDown(self):
        (TE.NEAR_MISS_LOG_PATH,
         TE.APPROVED_SIGNALS_LOG_PATH,
         TDF.AUDIT_LOG_PATH) = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_T7_near_miss_marca_near_miss_type_missing_xgot(self):
        ms = MatchState(match_id="FS_X", home="H", away="A",
                          minute=40, home_score=0, away_score=0,
                          home_bc=3, away_bc=0,
                          home_xg=1.20, away_xg=0.20,
                          home_xgot=0.0, away_xgot=0.0,
                          home_xgot_raw=None, away_xgot_raw=None,
                          home_xg_raw=1.20, away_xg_raw=0.20,
                          home_bc_raw=3, away_bc_raw=0)
        d = Decision(recommended_action="ENTER_OVER_PREMIUM",
                       message_severity="URGENT",
                       market_target="Over 2.5")
        allowed, reason = live_daemon._turbo_enforce_or_block(ms, d)
        self.assertFalse(allowed)
        self.assertEqual(reason, "TURBO_BLOCKED_MISSING_XGOT")
        rec = json.loads(TE.NEAR_MISS_LOG_PATH.read_text().splitlines()[0])
        self.assertEqual(rec["near_miss_type"], "missing_xgot")
        self.assertEqual(rec["final_decision"], "blocked_missing_data")
        self.assertFalse(rec["telegram_sent"])
        self.assertEqual(rec["block_reason"], "triple_debt_missing_xgot")

    def test_T8_nenhum_sinal_Telegram_quando_xGOT_ausente(self):
        ms = MatchState(match_id="FS_Y", home="H", away="A",
                          minute=42, home_score=0, away_score=0,
                          home_bc=3, away_bc=0,
                          home_xg=1.20, away_xg=0.20,
                          home_xgot=0.0, away_xgot=0.0,
                          home_xgot_raw=None, away_xgot_raw=None)
        d = Decision(recommended_action="ENTER_OVER_PREMIUM",
                       message_severity="URGENT")
        allowed, _ = live_daemon._turbo_enforce_or_block(ms, d)
        # Telegram NÃO pode ser autorizado
        self.assertFalse(allowed)
        # E não há linha no approved sidecar
        self.assertFalse(TE.APPROVED_SIGNALS_LOG_PATH.exists() and
                          TE.APPROVED_SIGNALS_LOG_PATH.read_text().strip())


# === T9 — _ensure_stats_url constrói path correto (Flashscore V3) =========
class T9_EnsureStatsUrl(unittest.TestCase):
    """Verificado contra DOM real do Flashscore em 30/mai/2026:
    a aba estatísticas completa fica em '.../resumo/estatisticas/total/?mid=...',
    NÃO no hash legacy '#/match-summary/match-statistics/0'."""

    def setUp(self):
        self.r = FlashscoreReader(headless=True)

    def test_T9a_constroi_url_nova_a_partir_de_url_com_mid(self):
        url = ("https://www.flashscore.com.br/jogo/futebol/"
                "bahia-UeD7XtzM/botafogo-jXzWoWa5/?mid=ptnOMDbs")
        out = self.r._ensure_stats_url(url)
        self.assertIn("/resumo/estatisticas/total/", out)
        self.assertIn("?mid=ptnOMDbs", out)
        self.assertNotIn("#/", out, "hash legacy NÃO pode estar presente")

    def test_T9b_remove_hash_legacy(self):
        url = ("https://www.flashscore.com.br/jogo/futebol/"
                "a-X/b-Y/?mid=Z#/match-summary/match-statistics/0")
        out = self.r._ensure_stats_url(url)
        self.assertNotIn("#", out)
        self.assertIn("/resumo/estatisticas/total/", out)
        self.assertIn("?mid=Z", out)

    def test_T9c_idempotente_url_ja_correta(self):
        url = ("https://www.flashscore.com.br/jogo/futebol/"
                "a-X/b-Y/resumo/estatisticas/total/?mid=Z")
        out = self.r._ensure_stats_url(url)
        self.assertEqual(out, url, "deveria ser idempotente")

    def test_T9d_url_sem_mid_aceita(self):
        url = "https://www.flashscore.com.br/jogo/futebol/a-X/b-Y/"
        out = self.r._ensure_stats_url(url)
        self.assertIn("/resumo/estatisticas/total/", out)

    def test_T9e_path_segments_intactos(self):
        url = ("https://www.flashscore.com.br/jogo/futebol/"
                "bahia-UeD7XtzM/botafogo-jXzWoWa5/?mid=ptnOMDbs")
        out = self.r._ensure_stats_url(url)
        # Times preservados na ordem original
        self.assertIn("bahia-UeD7XtzM", out)
        self.assertIn("botafogo-jXzWoWa5", out)
        # Domínio preservado
        self.assertTrue(out.startswith("https://www.flashscore.com.br/"))


def _run():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (T1_T2_ParserDistingueAusenteDeZero, T3_MatchStatePropaga,
                T4_T5_TrincaMissingVsFailed, T6_DaemonDisplay,
                T7_T8_NearMissEBloqueio, T9_EnsureStatsUrl):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    r = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run())
