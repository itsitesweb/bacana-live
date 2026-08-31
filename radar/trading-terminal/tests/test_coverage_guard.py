"""
Testes do LIVE COVERAGE GUARD (src/coverage_guard.py).

Cobertura dos casos A-H exigidos pelo dossiê v2.4:

  A. Discovery vê live, catálogo finished por INVALID_MINUTE_STATUS →
     guard limpa finished + jogo elegível + log recovered (TG crítico se A).
  B. Caso real Nacional × Coquimbo: premium A + live + finished_or_not_live=True
     + not_live_reason=INVALID_MINUTE_STATUS + ever_loaded_stats=False →
     recovered_by_coverage_guard=True + finished_or_not_live=False.
  C. Premium A live sem scan > 180s → COVERAGE_ERROR_PREMIUM_A_NOT_SCANNED_FAST.
  D. Não premium sem scan > 8min → WARN apenas.
  E. Jogo encerrado real (status_raw="Encerrado", FINISHED_MATCH) → guard
     NÃO recupera (status forte é confiável).
  F. Premium A em no_stats_backoff longo → cap em 3 min.
  G. Coverage guard não toca Regra 3.1.2.0 (módulo puro, sem importar regra).
  H. V1.2 sem vazamento — guard usa nomenclatura própria.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.catalog import Catalog
from src.coverage_guard import (
    run_coverage_guard,
    CoverageReport, CoverageEvent,
    SEV_INFO, SEV_WARN, SEV_ERROR, SEV_CRITICAL,
    COVERAGE_ERROR_DISCOVERED_NOT_CATALOGED,
    COVERAGE_ERROR_LIVE_MARKED_FINISHED,
    COVERAGE_ERROR_PREMIUM_A_NOT_SCANNED_FAST,
    COVERAGE_WARN_NON_PREMIUM_NOT_SCANNED,
    COVERAGE_AUTO_RECOVERED_LIVE_GAME,
    COVERAGE_PREMIUM_A_BACKOFF_CAPPED,
    format_terminal_summary, format_telegram_message,
    append_to_jsonl,
)


def _make_catalog():
    """Cria um Catalog vazio em arquivo temporário."""
    tmp = Path(tempfile.mkdtemp()) / "c.json"
    return Catalog(tmp)


def _add_entry(cat: Catalog, *, mid: str, url: str = None,
                premium_level: str = "NONE",
                league: str = "", country: str = "",
                finished: bool = False, finished_reason: str = "",
                finished_until: str = None,
                ever_loaded_stats: bool = False,
                last_scanned_at: str = None,
                last_minute=None,
                first_seen_at: str = None,
                no_stats_until: str = None):
    """Helper para popular o catálogo direto (sem passar por upsert)."""
    if url is None:
        url = (f"http://x.com/jogo/futebol/home-AAAAAA{mid[:3]}/"
               f"away-BBBBBB{mid[:3]}/?mid={mid}")
    now = datetime.now(timezone.utc).isoformat()
    cat._games[mid] = {
        "match_id": mid,
        "url": url,
        "first_seen_at": first_seen_at or now,
        "last_seen_at": now,
        "last_scanned_at": last_scanned_at,
        "last_minute": last_minute,
        "last_score": None,
        "ever_loaded_stats": ever_loaded_stats,
        "no_stats_count": 0,
        "no_stats_until": no_stats_until,
        "has_open_position": False,
        "last_signal_action": "",
        "last_signal_minute": 0,
        "last_bc_sum": 0,
        "finished_or_not_live": finished,
        "finished_or_not_live_at": now if finished else None,
        "finished_or_not_live_until": finished_until,
        "not_live_reason": finished_reason,
        "is_premium": premium_level != "NONE",
        "premium_reason": "flashscore_highlighted_league",
        "premium_level": premium_level,
        "premium_league_name": league,
        "premium_country": country,
        "league_meta_raw": {},
        "excluded_duplicate": False,
        "duplicate_of": "",
    }


# ──────────────────────────────────────────────────────────────────────
# A — Discovery vê live, catálogo bloqueou por motivo fraco
# ──────────────────────────────────────────────────────────────────────

class TestA_AutoRecover(unittest.TestCase):

    def test_A1_premium_A_recovered_with_critical_severity(self):
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        future = (now + timedelta(hours=11)).isoformat()
        _add_entry(cat, mid="FS_pA1", premium_level="A",
                    league="Copa Libertadores - Fase de Grupos",
                    country="América do sul",
                    finished=True, finished_reason="INVALID_MINUTE_STATUS",
                    finished_until=future,
                    first_seen_at=(now - timedelta(seconds=120)).isoformat())
        report = run_coverage_guard(
            catalog=cat, discovered_live_ids={"FS_pA1"},
            watchlist_ids=set(), now=now,
        )
        # Estado depois
        e = cat.get("FS_pA1")
        self.assertFalse(e["finished_or_not_live"],
                          "Premium A live + motivo fraco DEVE ser recuperado")
        self.assertTrue(e["recovered_by_coverage_guard"])
        self.assertEqual(report.stats["recovered_live_games"], 1)
        self.assertEqual(report.stats["premium_a_recovered"], 1)
        # Severidade: premium A recuperado = CRITICAL
        recovered_events = [ev for ev in report.events
                             if ev.event_type == COVERAGE_AUTO_RECOVERED_LIVE_GAME]
        self.assertEqual(len(recovered_events), 1)
        self.assertEqual(recovered_events[0].severity, SEV_CRITICAL)
        # Telegram crítico gerado
        self.assertEqual(len(report.telegram_critical), 1)
        self.assertIn("RECUPERADO", report.telegram_critical[0]["title"])

    def test_A2_premium_B_recovered_with_error_severity(self):
        """Premium B recuperado: ERROR (não CRITICAL)."""
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        future = (now + timedelta(hours=11)).isoformat()
        _add_entry(cat, mid="FS_pB1", premium_level="B",
                    finished=True, finished_reason="AMBIGUOUS_MINUTE_STATUS",
                    finished_until=future,
                    first_seen_at=(now - timedelta(seconds=120)).isoformat())
        report = run_coverage_guard(
            catalog=cat, discovered_live_ids={"FS_pB1"},
            watchlist_ids=set(), now=now,
        )
        e = cat.get("FS_pB1")
        self.assertFalse(e["finished_or_not_live"])
        # B é ERROR, não CRITICAL — sem TG crítico
        evs = [ev for ev in report.events
                if ev.event_type == COVERAGE_AUTO_RECOVERED_LIVE_GAME]
        self.assertEqual(evs[0].severity, SEV_ERROR)
        self.assertEqual(report.stats["premium_a_recovered"], 0)


# ──────────────────────────────────────────────────────────────────────
# B — Caso real Nacional × Coquimbo
# ──────────────────────────────────────────────────────────────────────

class TestB_NacionalCoquimboCase(unittest.TestCase):

    def test_B1_caso_real_recovered(self):
        """Cenário 1:1 com o entry FS_Gtk53bn1 capturado em produção."""
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        first_seen = (now - timedelta(minutes=20)).isoformat()
        # +11h no futuro (TTL original era 12h)
        future = (now + timedelta(hours=11)).isoformat()
        _add_entry(
            cat, mid="FS_Gtk53bn1",
            url="https://www.flashscore.com.br/jogo/futebol/"
                 "club-nacional-UaVu2MhA/coquimbo-hWejMZ6h/?mid=Gtk53bn1",
            premium_level="A",
            league="Copa Libertadores - Fase de Grupos",
            country="América do sul",
            finished=True, finished_reason="INVALID_MINUTE_STATUS",
            finished_until=future,
            ever_loaded_stats=False,
            last_scanned_at=None,
            last_minute=None,
            first_seen_at=first_seen,
        )
        # Discovery do ciclo viu o jogo live novamente
        report = run_coverage_guard(
            catalog=cat,
            discovered_live_ids={"FS_Gtk53bn1"},
            watchlist_ids=set(),
            now=now,
        )
        e = cat.get("FS_Gtk53bn1")
        self.assertFalse(e["finished_or_not_live"],
                          f"Nacional×Coquimbo DEVE ser recovered: {e}")
        self.assertTrue(e["recovered_by_coverage_guard"])
        self.assertEqual(e["recovered_reason_before"], "INVALID_MINUTE_STATUS")
        self.assertEqual(e["not_live_reason"], "")
        self.assertIsNone(e["finished_or_not_live_until"])
        # is_finished_or_not_live_active deve agora retornar False
        self.assertFalse(cat.is_finished_or_not_live_active("FS_Gtk53bn1"))
        # Premium preservado
        self.assertTrue(e["is_premium"])
        self.assertEqual(e["premium_level"], "A")
        # Reportado como recovered
        self.assertEqual(report.stats["recovered_live_games"], 1)
        # Telegram crítico montado
        self.assertEqual(len(report.telegram_critical), 1)
        tg = report.telegram_critical[0]
        self.assertEqual(tg["premium_level"], "A")
        self.assertEqual(tg["league"], "Copa Libertadores - Fase de Grupos")


# ──────────────────────────────────────────────────────────────────────
# C — Premium A sem scan > 180s
# ──────────────────────────────────────────────────────────────────────

class TestC_PremiumANotScannedFast(unittest.TestCase):

    def test_C1_premium_A_never_scanned_old(self):
        """Premium A descoberto há 5min, nunca scaneado → ERROR."""
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        first_seen = (now - timedelta(minutes=5)).isoformat()
        _add_entry(cat, mid="FS_pA_old", premium_level="A",
                    league="Premier League", country="Inglaterra",
                    last_scanned_at=None,
                    first_seen_at=first_seen)
        report = run_coverage_guard(
            catalog=cat, discovered_live_ids={"FS_pA_old"},
            watchlist_ids=set(), now=now,
        )
        errs = [ev for ev in report.events
                 if ev.event_type == COVERAGE_ERROR_PREMIUM_A_NOT_SCANNED_FAST]
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].severity, SEV_ERROR)

    def test_C2_premium_A_scanned_200s_ago(self):
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        last_scan = (now - timedelta(seconds=200)).isoformat()
        first_seen = (now - timedelta(minutes=10)).isoformat()
        _add_entry(cat, mid="FS_pA_lag", premium_level="A",
                    last_scanned_at=last_scan, ever_loaded_stats=True,
                    last_minute=23, first_seen_at=first_seen)
        report = run_coverage_guard(
            catalog=cat, discovered_live_ids={"FS_pA_lag"},
            watchlist_ids=set(), now=now,
        )
        errs = [ev for ev in report.events
                 if ev.event_type == COVERAGE_ERROR_PREMIUM_A_NOT_SCANNED_FAST]
        self.assertEqual(len(errs), 1)
        self.assertGreaterEqual(errs[0].seconds_since_last_scan, 200)

    def test_C3_premium_A_recently_discovered_NO_error(self):
        """Premium A descoberto há <30s — ainda é cedo pra cobrar scan."""
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        first_seen = (now - timedelta(seconds=15)).isoformat()
        _add_entry(cat, mid="FS_pA_new", premium_level="A",
                    last_scanned_at=None, first_seen_at=first_seen)
        report = run_coverage_guard(
            catalog=cat, discovered_live_ids={"FS_pA_new"},
            watchlist_ids=set(), now=now,
        )
        errs = [ev for ev in report.events
                 if ev.event_type == COVERAGE_ERROR_PREMIUM_A_NOT_SCANNED_FAST]
        self.assertEqual(len(errs), 0)


# ──────────────────────────────────────────────────────────────────────
# D — Não premium sem scan > 8min = WARN, não ERROR
# ──────────────────────────────────────────────────────────────────────

class TestD_NonPremiumWarnOnly(unittest.TestCase):

    def test_D1_non_premium_9min_warn(self):
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        last_scan = (now - timedelta(minutes=9)).isoformat()
        first_seen = (now - timedelta(minutes=20)).isoformat()
        _add_entry(cat, mid="FS_np", premium_level="NONE",
                    last_scanned_at=last_scan, ever_loaded_stats=True,
                    last_minute=45, first_seen_at=first_seen)
        report = run_coverage_guard(
            catalog=cat, discovered_live_ids={"FS_np"},
            watchlist_ids=set(), now=now,
        )
        warns = [ev for ev in report.events
                  if ev.event_type == COVERAGE_WARN_NON_PREMIUM_NOT_SCANNED]
        self.assertEqual(len(warns), 1)
        self.assertEqual(warns[0].severity, SEV_WARN)
        errs = [ev for ev in report.events
                 if ev.severity in (SEV_ERROR, SEV_CRITICAL)]
        self.assertEqual(len(errs), 0)


# ──────────────────────────────────────────────────────────────────────
# E — Status forte: guard NÃO recupera
# ──────────────────────────────────────────────────────────────────────

class TestE_StrongStatusNotRecovered(unittest.TestCase):

    def test_E1_FINISHED_MATCH_nao_eh_revertido(self):
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        future = (now + timedelta(hours=11)).isoformat()
        _add_entry(cat, mid="FS_terminado", premium_level="A",
                    finished=True, finished_reason="FINISHED_MATCH",
                    finished_until=future,
                    first_seen_at=(now - timedelta(minutes=10)).isoformat())
        report = run_coverage_guard(
            catalog=cat, discovered_live_ids={"FS_terminado"},
            watchlist_ids=set(), now=now,
        )
        e = cat.get("FS_terminado")
        # NÃO foi recuperado
        self.assertTrue(e["finished_or_not_live"])
        self.assertEqual(e["not_live_reason"], "FINISHED_MATCH")
        self.assertFalse(e.get("recovered_by_coverage_guard"))
        # Mas o guard registrou INFO (divergência entre discovery e catálogo)
        infos = [ev for ev in report.events
                  if ev.severity == SEV_INFO
                  and ev.event_type == COVERAGE_ERROR_LIVE_MARKED_FINISHED]
        self.assertEqual(len(infos), 1)

    def test_E2_NOT_LIVE_STATUS_nao_eh_revertido(self):
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        future = (now + timedelta(hours=11)).isoformat()
        _add_entry(cat, mid="FS_susp", premium_level="A",
                    finished=True, finished_reason="NOT_LIVE_STATUS",
                    finished_until=future)
        report = run_coverage_guard(
            catalog=cat, discovered_live_ids={"FS_susp"},
            watchlist_ids=set(), now=now,
        )
        e = cat.get("FS_susp")
        self.assertTrue(e["finished_or_not_live"])
        self.assertEqual(report.stats["recovered_live_games"], 0)


# ──────────────────────────────────────────────────────────────────────
# F — Premium A em no_stats_backoff longo → cap em 3 min
# ──────────────────────────────────────────────────────────────────────

class TestF_BackoffCap(unittest.TestCase):

    def test_F1_premium_A_backoff_30min_cap_3min(self):
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        long_until = (now + timedelta(minutes=30)).isoformat()
        _add_entry(cat, mid="FS_pA_back", premium_level="A",
                    no_stats_until=long_until,
                    first_seen_at=(now - timedelta(minutes=10)).isoformat(),
                    last_scanned_at=(now - timedelta(minutes=5)).isoformat(),
                    ever_loaded_stats=True, last_minute=23)
        report = run_coverage_guard(
            catalog=cat, discovered_live_ids={"FS_pA_back"},
            watchlist_ids=set(), now=now,
        )
        e = cat.get("FS_pA_back")
        new_until = datetime.fromisoformat(e["no_stats_until"])
        delta = (new_until - now).total_seconds()
        self.assertLessEqual(delta, 180 + 2)   # cap em 180s (+epsilon)
        self.assertGreater(delta, 60)
        # Reportado
        caps = [ev for ev in report.events
                 if ev.event_type == COVERAGE_PREMIUM_A_BACKOFF_CAPPED]
        self.assertEqual(len(caps), 1)
        self.assertEqual(report.stats["premium_a_backoff_capped"], 1)

    def test_F2_premium_A_backoff_curto_nao_alterado(self):
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        short_until = (now + timedelta(seconds=60)).isoformat()
        _add_entry(cat, mid="FS_pA_b2", premium_level="A",
                    no_stats_until=short_until,
                    first_seen_at=(now - timedelta(minutes=5)).isoformat(),
                    last_scanned_at=(now - timedelta(seconds=70)).isoformat(),
                    ever_loaded_stats=True)
        report = run_coverage_guard(
            catalog=cat, discovered_live_ids={"FS_pA_b2"},
            watchlist_ids=set(), now=now,
        )
        e = cat.get("FS_pA_b2")
        self.assertEqual(e["no_stats_until"], short_until,
                          "Backoff curto não pode ser alterado")
        self.assertEqual(report.stats["premium_a_backoff_capped"], 0)

    def test_F3_premium_B_backoff_longo_nao_alterado(self):
        """Cap só vale pra premium A."""
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        long_until = (now + timedelta(minutes=30)).isoformat()
        _add_entry(cat, mid="FS_pB_b", premium_level="B",
                    no_stats_until=long_until)
        report = run_coverage_guard(
            catalog=cat, discovered_live_ids={"FS_pB_b"},
            watchlist_ids=set(), now=now,
        )
        e = cat.get("FS_pB_b")
        self.assertEqual(e["no_stats_until"], long_until)


# ──────────────────────────────────────────────────────────────────────
# G — Coverage guard não toca Regra 3.1.2.0
# ──────────────────────────────────────────────────────────────────────

class TestG_NoRuleSideEffects(unittest.TestCase):

    def test_G1_module_does_not_import_codigo_3_1(self):
        """O módulo guard não pode importar src.codigo_3_1 — separação dura."""
        import src.coverage_guard as cg
        import inspect
        src_text = inspect.getsource(cg)
        self.assertNotIn("import codigo_3_1", src_text)
        self.assertNotIn("from src.codigo_3_1", src_text)
        self.assertNotIn("decision_engine", src_text)
        self.assertNotIn("evaluate_codigo_3_1", src_text)

    def test_G2_does_not_modify_state_json(self):
        """Guard não escreve em state.json (anti-spam da regra)."""
        import src.coverage_guard as cg
        import inspect
        src_text = inspect.getsource(cg)
        self.assertNotIn("state.json", src_text)
        self.assertNotIn("anti_spam", src_text.lower())


# ──────────────────────────────────────────────────────────────────────
# H — V1.2 sem vazamento (nomenclatura própria)
# ──────────────────────────────────────────────────────────────────────

class TestH_NoV12Leak(unittest.TestCase):

    def test_H1_guard_messages_no_v12_terms(self):
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        future = (now + timedelta(hours=11)).isoformat()
        _add_entry(cat, mid="FS_h1", premium_level="A",
                    finished=True, finished_reason="INVALID_MINUTE_STATUS",
                    finished_until=future)
        report = run_coverage_guard(
            catalog=cat, discovered_live_ids={"FS_h1"},
            watchlist_ids=set(), now=now,
        )
        # Mensagem do TG não pode citar V1.2
        msg = format_telegram_message(report.telegram_critical[0])
        forbidden = ["V1.2", "motor_v12", "Motor V1.2", "decision_engine",
                      "REDUCE_OVER", "LOCK_PROFIT"]
        for term in forbidden:
            self.assertNotIn(term, msg, f"Vazamento V1.2: {term} em {msg!r}")


# ──────────────────────────────────────────────────────────────────────
# Discovery sem entry no catálogo
# ──────────────────────────────────────────────────────────────────────

class TestDiscoveryNotCataloged(unittest.TestCase):

    def test_NC1_discovered_not_cataloged(self):
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        # FS_orphan não existe no catálogo
        report = run_coverage_guard(
            catalog=cat, discovered_live_ids={"FS_orphan"},
            watchlist_ids=set(), now=now,
        )
        events = [ev for ev in report.events
                   if ev.event_type == COVERAGE_ERROR_DISCOVERED_NOT_CATALOGED]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].severity, SEV_ERROR)


# ──────────────────────────────────────────────────────────────────────
# Display + persistência
# ──────────────────────────────────────────────────────────────────────

class TestDisplayAndPersistence(unittest.TestCase):

    def test_terminal_summary_format(self):
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        future = (now + timedelta(hours=11)).isoformat()
        _add_entry(cat, mid="FS_d1", premium_level="A",
                    finished=True, finished_reason="INVALID_MINUTE_STATUS",
                    finished_until=future,
                    first_seen_at=(now - timedelta(minutes=10)).isoformat())
        report = run_coverage_guard(
            catalog=cat, discovered_live_ids={"FS_d1"},
            watchlist_ids=set(), now=now,
        )
        text = format_terminal_summary(report)
        self.assertIn("📡 COVERAGE GUARD", text)
        self.assertIn("live_discovered:", text)
        self.assertIn("recovered_live_games: 1", text)
        self.assertIn("coverage_errors:", text)

    def test_telegram_message_format(self):
        tg_item = {
            "title": "🚨 COVERAGE GUARD — JOGO AO VIVO RECUPERADO",
            "home": "Club Nacional", "away": "Coquimbo Unido",
            "league": "Copa Libertadores", "country": "América do sul",
            "reason_before": "INVALID_MINUTE_STATUS",
            "premium_level": "A",
        }
        msg = format_telegram_message(tg_item)
        self.assertIn("Club Nacional x Coquimbo Unido", msg)
        self.assertIn("Copa Libertadores", msg)
        self.assertIn("INVALID_MINUTE_STATUS", msg)
        self.assertIn("monitoramento retomado", msg)

    def test_append_to_jsonl(self):
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        future = (now + timedelta(hours=11)).isoformat()
        _add_entry(cat, mid="FS_j1", premium_level="A",
                    finished=True, finished_reason="INVALID_MINUTE_STATUS",
                    finished_until=future)
        report = run_coverage_guard(
            catalog=cat, discovered_live_ids={"FS_j1"},
            watchlist_ids=set(), now=now,
        )
        tmp = Path(tempfile.mkdtemp()) / "logs/live_coverage_guard.jsonl"
        n = append_to_jsonl(tmp, report, now=now)
        self.assertGreaterEqual(n, 1)
        self.assertTrue(tmp.exists())
        # Cada linha é um JSON válido com campos obrigatórios
        with open(tmp) as f:
            for line in f:
                rec = json.loads(line)
                for k in ("timestamp", "severity", "event_type",
                           "match_id", "reason_before", "action_taken"):
                    self.assertIn(k, rec)


class TestNoTelegramByDefault(unittest.TestCase):
    """v2.5 — Coverage Guard NÃO envia Telegram por padrão.

    Guard continua produzindo report.telegram_critical (lista de itens) pra
    log/audit, mas o caller (live_daemon) só envia se TECHNICAL_TELEGRAM_ENABLED.
    Aqui validamos: (1) o módulo guard não chama tg.send_text/_send_raw
    diretamente, e (2) com flag off, send_text/_send_raw nunca são chamados.
    """

    def test_NT1_guard_module_does_not_import_telegram(self):
        """Guard é puro — nunca importa telegram_client."""
        import src.coverage_guard as cg
        import inspect
        src_text = inspect.getsource(cg)
        self.assertNotIn("telegram_client", src_text)
        self.assertNotIn("send_text", src_text)
        self.assertNotIn("_send_raw", src_text)
        self.assertNotIn("sendMessage", src_text)

    def test_NT2_run_coverage_guard_does_not_send_telegram(self):
        """run_coverage_guard nunca emite TG diretamente (não tem como)."""
        cat = _make_catalog()
        now = datetime.now(timezone.utc)
        future = (now + timedelta(hours=11)).isoformat()
        _add_entry(cat, mid="FS_nt1", premium_level="A",
                    finished=True, finished_reason="INVALID_MINUTE_STATUS",
                    finished_until=future,
                    first_seen_at=(now - timedelta(minutes=10)).isoformat())
        # Sem instância de TG passada — se chamasse send_text quebraria
        report = run_coverage_guard(
            catalog=cat, discovered_live_ids={"FS_nt1"},
            watchlist_ids=set(), now=now,
        )
        # Recovery ocorreu — log foi gerado — telegram_critical foi montado
        self.assertEqual(report.stats["recovered_live_games"], 1)
        self.assertGreaterEqual(len(report.telegram_critical), 1)
        # Mas guard não enviou nada (não tem TG client). Quem envia é o caller.

    def test_NT3_operational_flag_off_by_default(self):
        os.environ.pop("TECHNICAL_TELEGRAM_ENABLED", None)
        from src.operational_config import coverage_guard_telegram_enabled
        self.assertFalse(coverage_guard_telegram_enabled())


def _run():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (TestA_AutoRecover, TestB_NacionalCoquimboCase,
                TestC_PremiumANotScannedFast, TestD_NonPremiumWarnOnly,
                TestE_StrongStatusNotRecovered, TestF_BackoffCap,
                TestG_NoRuleSideEffects, TestH_NoV12Leak,
                TestDiscoveryNotCataloged, TestDisplayAndPersistence,
                TestNoTelegramByDefault):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    return 0 if runner.run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run())
