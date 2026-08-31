"""
Testes do filtro is_live_match() do live_daemon.

Cobertura do ajuste cirúrgico pós-v1.1:
  - Jogos FT/Finished/Encerrado/TERMINADO/AET/Penalties → NÃO live
  - Jogos em injury time (90+3, status com minuto explícito) → LIVE
  - Jogos 1st Half / 2nd Half / Half Time → LIVE
  - Jogos scheduled/agendados/programados → NÃO live
  - Jogos suspended/cancelled/postponed/abandoned → NÃO live
  - Heartbeat registra games_finished_or_not_live
  - Watchlist (catalog) compatível com filtro
"""
import json
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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
import live_daemon
from live_daemon import is_live_match


def make_ms(*, minute=45, status_raw="", home="Time A", away="Time B",
            home_bc=1, away_bc=1, home_score=0, away_score=0):
    return MatchState(
        match_id="FS_test",
        home=home, away=away,
        minute=minute,
        status_raw=status_raw,
        home_bc=home_bc, away_bc=away_bc,
        home_score=home_score, away_score=away_score,
    )


# ──────────────────────────────────────────────────────────────────────


class TestFinishedMatches(unittest.TestCase):
    """Jogos finalizados NUNCA podem entrar no scan."""

    def test_F1_TERMINADO(self):
        live, reason = is_live_match(make_ms(minute=90, status_raw="TERMINADO"))
        self.assertFalse(live)
        self.assertEqual(reason, "FINISHED_MATCH")

    def test_F2_FINISHED(self):
        live, reason = is_live_match(make_ms(minute=90, status_raw="Finished"))
        self.assertFalse(live)
        self.assertEqual(reason, "FINISHED_MATCH")

    def test_F3_FT_isolated(self):
        live, reason = is_live_match(make_ms(minute=90, status_raw="FT"))
        self.assertFalse(live)
        self.assertEqual(reason, "FINISHED_MATCH")

    def test_F4_FT_in_phrase(self):
        live, reason = is_live_match(make_ms(minute=90, status_raw="Full Time"))
        self.assertFalse(live)
        self.assertEqual(reason, "FINISHED_MATCH")

    def test_F5_AET(self):
        live, reason = is_live_match(make_ms(minute=120, status_raw="AET"))
        self.assertFalse(live)
        self.assertEqual(reason, "FINISHED_MATCH")

    def test_F6_after_penalties(self):
        live, reason = is_live_match(make_ms(minute=120, status_raw="Após pen."))
        self.assertFalse(live)
        self.assertEqual(reason, "FINISHED_MATCH")

    def test_F7_ENCERRADO(self):
        live, reason = is_live_match(make_ms(minute=90, status_raw="ENCERRADO"))
        self.assertFalse(live)
        self.assertEqual(reason, "FINISHED_MATCH")

    def test_F8_FT_not_matched_in_1st_half(self):
        # "1st Half" contém "ST" mas não pode ser confundido com FT
        live, reason = is_live_match(make_ms(minute=23, status_raw="1st Half 23:45"))
        self.assertTrue(live, f"'1st Half' deve ser live, não FT. Reason: {reason}")


class TestLiveMatches(unittest.TestCase):
    """Jogos ao vivo (incluindo injury time) DEVEM entrar."""

    def test_L1_1st_half_with_time(self):
        live, _ = is_live_match(make_ms(minute=23, status_raw="1º tempo23:45"))
        self.assertTrue(live)

    def test_L2_2nd_half_with_time(self):
        live, _ = is_live_match(make_ms(minute=56, status_raw="2º tempo56:21"))
        self.assertTrue(live)

    def test_L3_injury_time(self):
        live, _ = is_live_match(make_ms(minute=90, status_raw="90+3'"))
        self.assertTrue(live)

    def test_L4_halftime(self):
        live, _ = is_live_match(make_ms(minute=45, status_raw="INTERVALO"))
        self.assertTrue(live)

    def test_L5_HT(self):
        live, _ = is_live_match(make_ms(minute=45, status_raw="HT"))
        self.assertTrue(live)

    def test_L6_plain_minute_only(self):
        # Flashscore às vezes só mostra o número
        live, _ = is_live_match(make_ms(minute=67, status_raw="67"))
        self.assertTrue(live)

    def test_L7_status_empty_but_minute_valid(self):
        # Tolerância: se status veio vazio mas minuto está no range válido,
        # consideramos live (fallback otimista).
        live, _ = is_live_match(make_ms(minute=45, status_raw=""))
        self.assertTrue(live)


class TestScheduledMatches(unittest.TestCase):
    """Jogos agendados NÃO podem entrar no scan."""

    def test_S1_scheduled(self):
        live, reason = is_live_match(make_ms(minute=0, status_raw="Scheduled"))
        self.assertFalse(live)
        self.assertEqual(reason, "NOT_LIVE_STATUS")

    def test_S2_aguardando(self):
        live, reason = is_live_match(make_ms(minute=0, status_raw="Aguardando início"))
        self.assertFalse(live)
        self.assertEqual(reason, "NOT_LIVE_STATUS")

    def test_S3_not_started(self):
        live, reason = is_live_match(make_ms(minute=0, status_raw="Not Started"))
        self.assertFalse(live)
        self.assertEqual(reason, "NOT_LIVE_STATUS")


class TestSuspendedMatches(unittest.TestCase):
    """Jogos suspensos/cancelados/postponed/abandoned NÃO podem entrar."""

    def test_X1_postponed(self):
        live, reason = is_live_match(make_ms(minute=0, status_raw="Postponed"))
        self.assertFalse(live)
        self.assertEqual(reason, "NOT_LIVE_STATUS")

    def test_X2_adiado(self):
        live, reason = is_live_match(make_ms(minute=0, status_raw="Adiado"))
        self.assertFalse(live)
        self.assertEqual(reason, "NOT_LIVE_STATUS")

    def test_X3_cancelled(self):
        live, reason = is_live_match(make_ms(minute=0, status_raw="Cancelled"))
        self.assertFalse(live)
        self.assertEqual(reason, "NOT_LIVE_STATUS")

    def test_X4_suspended(self):
        live, reason = is_live_match(make_ms(minute=23, status_raw="Suspended"))
        self.assertFalse(live)
        self.assertEqual(reason, "NOT_LIVE_STATUS")

    def test_X5_abandoned(self):
        live, reason = is_live_match(make_ms(minute=45, status_raw="Abandoned"))
        self.assertFalse(live)
        self.assertEqual(reason, "NOT_LIVE_STATUS")

    def test_X6_walkover(self):
        live, reason = is_live_match(make_ms(minute=0, status_raw="W.O."))
        self.assertFalse(live)
        self.assertEqual(reason, "NOT_LIVE_STATUS")


class TestInvalidMinute(unittest.TestCase):
    """Minuto inválido — distinguir AMBÍGUO (status vazio, retry) vs INVÁLIDO
    forte (status presente mas não-reconhecido, ou minute > 130)."""

    # ─── AMBÍGUO: status_raw vazio + minute<=0 ───────────────────────
    # Esse é o caso do bug Nacional × Coquimbo: DOM em kickoff, parser
    # leu minute=0 antes do Flashscore preencher. NÃO pode marcar finished.

    def test_I1_minute_zero_empty_status_eh_AMBIGUOUS(self):
        """v2.3: minute=0 + status_raw vazio → AMBIGUOUS (não INVALID)."""
        live, reason = is_live_match(make_ms(minute=0, status_raw=""))
        self.assertFalse(live)
        self.assertEqual(reason, "AMBIGUOUS_MINUTE_STATUS")

    def test_I2_minute_negative_empty_status_eh_AMBIGUOUS(self):
        live, reason = is_live_match(make_ms(minute=-1, status_raw=""))
        self.assertFalse(live)
        self.assertEqual(reason, "AMBIGUOUS_MINUTE_STATUS")

    def test_I1b_minute_zero_status_None_eh_AMBIGUOUS(self):
        """status_raw=None também é tratado como vazio."""
        live, reason = is_live_match(make_ms(minute=0, status_raw=None))
        self.assertFalse(live)
        self.assertEqual(reason, "AMBIGUOUS_MINUTE_STATUS")

    # ─── INVÁLIDO forte: minute > 130 ──────────────────────────────

    def test_I3_minute_above_130(self):
        live, reason = is_live_match(make_ms(minute=999, status_raw=""))
        self.assertFalse(live)
        self.assertEqual(reason, "INVALID_MINUTE_STATUS")

    # ─── INVÁLIDO forte: minute<=0 + status_raw presente mas não-keyword ──

    def test_I4_minute_zero_status_unrecognized_eh_INVALID(self):
        """Status presente (mas não bate nenhuma keyword) + minute<=0 →
        INVALID (não AMBIGUOUS). Esse caso justifica marcação finished."""
        live, reason = is_live_match(make_ms(minute=0, status_raw="???"))
        self.assertFalse(live)
        self.assertEqual(reason, "INVALID_MINUTE_STATUS")

    # ─── Confirmação: status forte ainda casa as branches certas ───

    def test_I5_status_Encerrado_continua_FINISHED(self):
        live, reason = is_live_match(make_ms(minute=0, status_raw="Encerrado"))
        self.assertFalse(live)
        self.assertEqual(reason, "FINISHED_MATCH")

    def test_I6_status_Apos_Penaltis_continua_FINISHED(self):
        live, reason = is_live_match(
            make_ms(minute=120, status_raw="Após Pênaltis"))
        self.assertFalse(live)
        self.assertEqual(reason, "FINISHED_MATCH")

    def test_I7_status_Suspenso_continua_NOT_LIVE(self):
        live, reason = is_live_match(
            make_ms(minute=0, status_raw="Suspenso"))
        self.assertFalse(live)
        self.assertEqual(reason, "NOT_LIVE_STATUS")


class TestAmbiguousBehaviorInCatalog(unittest.TestCase):
    """v2.3 — Comportamento do caller ao ver AMBIGUOUS_MINUTE_STATUS.

    Simula o cenário do bug Nacional × Coquimbo:
      - jogo premium A
      - first_seen_at recente
      - read_match retorna ms com status_raw='' e minute=0
      - ever_loaded_stats=False
      → NÃO deve marcar finished_or_not_live por 12h
      → DEVE usar mark_no_stats (backoff curto)
    """

    def setUp(self):
        from src.catalog import Catalog
        import tempfile
        from pathlib import Path
        self.tmp = tempfile.mkdtemp()
        self.path = Path(self.tmp) / "catalog.json"
        self.cat = Catalog(self.path)
        # Premium A descoberto agora
        self.mid = "FS_kickoff_test"
        url = ("https://www.flashscore.com.br/jogo/futebol/"
               "club-nacional-AAAAAA1/coquimbo-BBBBBB1/?mid=kickoff_test")
        self.cat.upsert_discovered(self.mid, url, league_meta={
            "league_name": "Copa Libertadores - Fase de Grupos",
            "country": "América do sul",
            "css_classes": ["headerLeague--has-star"],
        })

    def test_J1_premium_A_kickoff_ambiguo_nao_marca_finished(self):
        """Jogo premium A com leitura ambígua não pode ser bloqueado 12h."""
        ms_kickoff = make_ms(minute=0, status_raw="",
                              home="Club Nacional", away="Coquimbo Unido")
        live, reason = is_live_match(ms_kickoff)
        self.assertFalse(live)
        self.assertEqual(reason, "AMBIGUOUS_MINUTE_STATUS")

        # Simula o caller: AMBIGUOUS → mark_no_stats, NÃO finished
        self.cat.mark_no_stats(self.mid)
        entry = self.cat.get(self.mid)

        # ASSERTS críticos
        self.assertFalse(entry.get("finished_or_not_live", False),
                          "AMBIGUOUS NÃO pode marcar finished_or_not_live")
        self.assertGreater(entry.get("no_stats_count", 0), 0,
                            "mark_no_stats deveria ter incrementado contador")
        self.assertIsNotNone(entry.get("no_stats_until"),
                              "no_stats_until deve estar setado (backoff curto)")
        # is_finished_or_not_live_active deve retornar False — jogo ainda vivo
        self.assertFalse(self.cat.is_finished_or_not_live_active(self.mid))

    def test_J2_premium_A_volta_ao_ser_escaneado_com_sucesso(self):
        """Após o backoff, próximo scan retorna stats reais. Premium A volta
        a ser elegível pra watchlist normalmente."""
        # 1ª leitura ambígua → mark_no_stats
        self.cat.mark_no_stats(self.mid)
        # 2ª leitura: agora o DOM completou — scan retorna minuto e stats reais
        self.cat.mark_scanned(self.mid, minute=23, score="1-0", bc_sum=2)
        e = self.cat.get(self.mid)
        self.assertEqual(e["last_minute"], 23)
        self.assertEqual(e["last_score"], "1-0")
        self.assertTrue(e["ever_loaded_stats"])
        # mark_scanned reseta no_stats
        self.assertEqual(e["no_stats_count"], 0)
        self.assertIsNone(e["no_stats_until"])
        # Premium e is_premium preservados
        self.assertTrue(e["is_premium"])
        self.assertEqual(e["premium_level"], "A")


class TestHeartbeatRegistersNotLive(unittest.TestCase):
    """Heartbeat precisa registrar games_finished_or_not_live."""

    def test_HB_field_present(self):
        tmp = Path(tempfile.mkdtemp()) / "heartbeat.json"
        old_hb = live_daemon.HEARTBEAT_FILE
        live_daemon.HEARTBEAT_FILE = tmp
        try:
            live_daemon.save_heartbeat(
                scan_number=1,
                last_scan_at=datetime.now(timezone.utc).isoformat(),
                last_scan_duration_seconds=90.0,
                total_live_games_discovered=20,
                games_discovered=20,
                games_with_cc_available=8,
                games_without_cc_available=5,
                games_scanned=8,
                games_scanned_this_cycle=8,
                games_skipped_this_cycle=0,
                games_finished_or_not_live=7,
                games_excluded_finished_or_not_live=15,
                telegram_ready=True,
                telegram_sent_last_cycle=0,
                errors_last_cycle=0,
            )
        finally:
            live_daemon.HEARTBEAT_FILE = old_hb

        data = json.loads(tmp.read_text())
        self.assertIn("games_finished_or_not_live", data)
        self.assertEqual(data["games_finished_or_not_live"], 7)
        # Novo contador (ajuste pós-cadência v1.1):
        self.assertIn("games_excluded_finished_or_not_live", data)
        self.assertEqual(data["games_excluded_finished_or_not_live"], 15)


class TestWatchlistDoesNotIncludeFinished(unittest.TestCase):
    """A watchlist por si só não filtra status — esse é trabalho do daemon
    APÓS read_match. Mas o filtro is_live_match deve excluir corretamente
    mesmo que o catálogo tenha jogos finalizados marcados."""

    def test_W_filter_excludes_finished_from_scan(self):
        # Cenário: simular jogo finalizado retornado pelo Flashscore
        ms_finished = make_ms(minute=90, status_raw="TERMINADO",
                              home="Tacoma", away="Ventura")
        live, reason = is_live_match(ms_finished)
        self.assertFalse(live)
        self.assertEqual(reason, "FINISHED_MATCH")
        # No daemon real, esse jogo seria descartado antes de chegar ao
        # codigo_3_1.evaluate_codigo_3_1 — então nenhum alerta é gerado.


# ──────────────────────────────────────────────────────────────────────


def _run_all():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (TestFinishedMatches, TestLiveMatches, TestScheduledMatches,
                TestSuspendedMatches, TestInvalidMinute,
                TestHeartbeatRegistersNotLive, TestWatchlistDoesNotIncludeFinished):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run_all())
