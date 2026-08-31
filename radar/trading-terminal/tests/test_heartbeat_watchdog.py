"""
Testes da Seção 13 (heartbeat + watchdog) e Seção 10-12 (cadência/cobertura)
do dossiê v1.1 de O Código 3:1.

H1-H8 — heartbeat e watchdog
C1-C6 — cadência e cobertura
"""
import json
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub Playwright pra evitar import error no live_daemon
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

import live_daemon
from watchdog import Watchdog


# ──────────────────────────────────────────────────────────────────────
# H1-H8 — HEARTBEAT + WATCHDOG
# ──────────────────────────────────────────────────────────────────────


class TestHeartbeatAndWatchdog(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.heartbeat = self.tmp / "heartbeat.json"
        self.state = self.tmp / "watchdog_state.json"
        # Sender mockado para capturar chamadas sem fazer HTTP real
        self.sent_msgs = []
        self.sender_returns = True

        def sender(msg):
            self.sent_msgs.append(msg)
            return self.sender_returns
        self.sender = sender

    def _write_heartbeat(self, *, scan_at=None, scan_number=1,
                          telegram_sent_last_cycle=0, games_scanned=10,
                          extra=None):
        if scan_at is None:
            scan_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "status": "alive",
            "terminal_name": "O Código 3:1",
            "mode": "codigo_3_1",
            "last_scan_at": scan_at,
            "last_scan_duration_seconds": 87.3,
            "scan_number": scan_number,
            "total_live_games_discovered": 50,
            "games_discovered": 50,
            "games_with_cc_available": 12,
            "games_without_cc_available": 38,
            "games_scanned": games_scanned,
            "games_scanned_this_cycle": games_scanned,
            "games_skipped_this_cycle": 0,
            "telegram_ready": True,
            "telegram_sent_last_cycle": telegram_sent_last_cycle,
            "errors_last_cycle": 0,
        }
        if extra:
            payload.update(extra)
        self.heartbeat.write_text(json.dumps(payload))
        return payload

    # ──────── H1 ────────
    def test_H1_heartbeat_created_after_first_cycle(self):
        # Simular o que o daemon faz: chamar save_heartbeat
        import live_daemon as ld
        old_hb = ld.HEARTBEAT_FILE
        ld.HEARTBEAT_FILE = self.heartbeat
        try:
            ld.save_heartbeat(
                scan_number=1,
                last_scan_at=datetime.now(timezone.utc).isoformat(),
                last_scan_duration_seconds=87.3,
                total_live_games_discovered=50,
                games_discovered=50,
                games_with_cc_available=12,
                games_without_cc_available=38,
                games_scanned=12,
                games_scanned_this_cycle=12,
                games_skipped_this_cycle=0,
                telegram_ready=True,
                telegram_sent_last_cycle=1,
                errors_last_cycle=0,
            )
        finally:
            ld.HEARTBEAT_FILE = old_hb

        self.assertTrue(self.heartbeat.exists(), "heartbeat.json deve existir após 1º ciclo")
        data = json.loads(self.heartbeat.read_text())
        # Campos obrigatórios (Seção 13.1)
        required = ["status", "terminal_name", "mode", "last_scan_at",
                    "last_scan_duration_seconds", "scan_number",
                    "total_live_games_discovered", "games_discovered",
                    "games_with_cc_available", "games_without_cc_available",
                    "games_scanned", "games_scanned_this_cycle",
                    "games_skipped_this_cycle", "telegram_ready",
                    "telegram_sent_last_cycle", "errors_last_cycle"]
        for key in required:
            self.assertIn(key, data, f"heartbeat deve conter '{key}'")
        self.assertEqual(data["terminal_name"], "O Código 3:1")
        self.assertEqual(data["mode"], "codigo_3_1")
        self.assertEqual(data["status"], "alive")

    # ──────── H2 ────────
    def test_H2_heartbeat_updated_each_cycle(self):
        import live_daemon as ld
        old_hb = ld.HEARTBEAT_FILE
        ld.HEARTBEAT_FILE = self.heartbeat
        try:
            # Ciclo 1
            ts1 = datetime.now(timezone.utc).isoformat()
            ld.save_heartbeat(scan_number=1, last_scan_at=ts1,
                              last_scan_duration_seconds=80.0,
                              total_live_games_discovered=50, games_discovered=50,
                              games_with_cc_available=10, games_without_cc_available=40,
                              games_scanned=10, games_scanned_this_cycle=10,
                              games_skipped_this_cycle=0, telegram_ready=True,
                              telegram_sent_last_cycle=0, errors_last_cycle=0)
            d1 = json.loads(self.heartbeat.read_text())
            # Ciclo 2 (mais tarde, scan_number maior)
            ts2 = (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat()
            ld.save_heartbeat(scan_number=2, last_scan_at=ts2,
                              last_scan_duration_seconds=90.0,
                              total_live_games_discovered=52, games_discovered=52,
                              games_with_cc_available=12, games_without_cc_available=40,
                              games_scanned=12, games_scanned_this_cycle=12,
                              games_skipped_this_cycle=0, telegram_ready=True,
                              telegram_sent_last_cycle=1, errors_last_cycle=0)
            d2 = json.loads(self.heartbeat.read_text())
        finally:
            ld.HEARTBEAT_FILE = old_hb

        self.assertEqual(d1["scan_number"], 1)
        self.assertEqual(d2["scan_number"], 2)
        self.assertNotEqual(d1["last_scan_at"], d2["last_scan_at"])

    # ──────── H3 ────────
    def test_H3_watchdog_silent_when_heartbeat_recent(self):
        # Heartbeat de 2 min atrás → dentro do threshold de 10 min
        recent = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        self._write_heartbeat(scan_at=recent)

        w = Watchdog(alert_threshold_minutes=10,
                     heartbeat_path=self.heartbeat, state_path=self.state,
                     telegram_sender=self.sender)
        result = w.check()
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["sent_critical"])
        self.assertFalse(result["sent_summary"])
        self.assertEqual(self.sent_msgs, [], "Nenhum Telegram em estado saudável")

    # ──────── H4 ────────
    def test_H4_watchdog_sends_critical_when_heartbeat_stale(self):
        # Heartbeat de 15 min atrás → ALÉM do threshold de 10 min
        stale = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        self._write_heartbeat(scan_at=stale, games_scanned=8)

        w = Watchdog(alert_threshold_minutes=10,
                     heartbeat_path=self.heartbeat, state_path=self.state,
                     telegram_sender=self.sender)
        result = w.check()
        self.assertEqual(result["status"], "critical")
        self.assertTrue(result["sent_critical"])
        self.assertEqual(len(self.sent_msgs), 1)
        msg = self.sent_msgs[0]
        self.assertIn("🔴 ALERTA — O CÓDIGO 3:1", msg)
        self.assertIn("15 min", msg)
        self.assertIn("Jogos escaneados no último ciclo: 8", msg)

    # ──────── H5 ────────
    def test_H5_watchdog_anti_spam_does_not_repeat(self):
        stale = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        self._write_heartbeat(scan_at=stale)

        w = Watchdog(alert_threshold_minutes=10,
                     heartbeat_path=self.heartbeat, state_path=self.state,
                     telegram_sender=self.sender)
        # 1ª checagem: envia
        r1 = w.check()
        self.assertTrue(r1["sent_critical"])
        # 2ª checagem (sem mudança no heartbeat): NÃO envia de novo
        r2 = w.check()
        self.assertFalse(r2["sent_critical"])
        self.assertEqual(r2["status"], "critical")
        # 3ª checagem: idem
        r3 = w.check()
        self.assertFalse(r3["sent_critical"])
        # Total enviado: APENAS 1
        self.assertEqual(len(self.sent_msgs), 1,
                         f"Anti-spam deve impedir reenvio. Enviadas: {len(self.sent_msgs)}")

    # ──────── H6 ────────
    def test_H6_no_summary_without_flag(self):
        # Heartbeat saudável + summary_hours=None → silêncio total
        recent = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self._write_heartbeat(scan_at=recent)
        w = Watchdog(alert_threshold_minutes=10, summary_hours=None,
                     heartbeat_path=self.heartbeat, state_path=self.state,
                     telegram_sender=self.sender)
        for _ in range(5):
            w.check()
        self.assertEqual(self.sent_msgs, [],
                         "Sem --summary-hours, watchdog não deve enviar resumo OK")

    # ──────── H7 ────────
    def test_H7_summary_sent_only_after_interval(self):
        # Heartbeat saudável + summary_hours=3
        recent = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self._write_heartbeat(scan_at=recent, telegram_sent_last_cycle=1)

        # Mock do now_fn para controlar o tempo
        fake_now = [datetime.now(timezone.utc)]

        def now_fn():
            return fake_now[0]

        w = Watchdog(alert_threshold_minutes=10, summary_hours=3,
                     heartbeat_path=self.heartbeat, state_path=self.state,
                     telegram_sender=self.sender, now_fn=now_fn)
        # 1ª checagem (sem last_summary_at) → envia o primeiro resumo
        r1 = w.check()
        self.assertTrue(r1["sent_summary"], f"1ª checagem deveria enviar 1º summary; status={r1['status']}")
        self.assertEqual(len(self.sent_msgs), 1)
        self.assertIn("🟢 STATUS — O CÓDIGO 3:1", self.sent_msgs[0])

        # Atualizar heartbeat (novo scan) e avançar 1h → AINDA não envia
        fake_now[0] += timedelta(hours=1)
        recent2 = fake_now[0].isoformat()
        self._write_heartbeat(scan_at=recent2, scan_number=2,
                                telegram_sent_last_cycle=2)
        r2 = w.check()
        self.assertFalse(r2["sent_summary"], "1h depois ainda dentro da janela 3h")
        self.assertEqual(len(self.sent_msgs), 1)

        # Avançar mais 3h → envia 2º summary
        fake_now[0] += timedelta(hours=3)
        recent3 = fake_now[0].isoformat()
        self._write_heartbeat(scan_at=recent3, scan_number=3,
                                telegram_sent_last_cycle=0)
        r3 = w.check()
        self.assertTrue(r3["sent_summary"], "3h depois deve enviar 2º summary")
        self.assertEqual(len(self.sent_msgs), 2)

    # ──────── H9 ────────
    def test_H9_cycle_over_target_and_delay(self):
        """Heartbeat marca cycle_over_target=True e scan_delay_seconds correto
        quando ciclo > target."""
        import live_daemon as ld
        old_hb = ld.HEARTBEAT_FILE
        ld.HEARTBEAT_FILE = self.heartbeat
        try:
            # Ciclo de 200s com alvo 120s → atraso = 80s
            ld.save_heartbeat(
                scan_number=5,
                last_scan_at=datetime.now(timezone.utc).isoformat(),
                last_scan_duration_seconds=200.0,
                target_scan_interval_seconds=120,
                total_live_games_discovered=15,
                games_discovered=15,
                games_with_cc_available=2,
                games_without_cc_available=10,
                games_scanned=2,
                games_scanned_this_cycle=2,
                games_skipped_this_cycle=3,
                games_finished_or_not_live=5,
                no_stats_backoff_count=8,
                games_skipped_by_no_stats_backoff=2,
                telegram_ready=True,
                telegram_sent_last_cycle=0,
                errors_last_cycle=0,
            )
        finally:
            ld.HEARTBEAT_FILE = old_hb

        data = json.loads(self.heartbeat.read_text())
        self.assertTrue(data["cycle_over_target"],
                        "Ciclo 200s > alvo 120s deve marcar cycle_over_target=True")
        self.assertEqual(data["scan_delay_seconds"], 80,
                         "Atraso deve ser 200-120=80s")
        self.assertEqual(data["target_scan_interval_seconds"], 120)
        self.assertEqual(data["actual_cycle_duration_seconds"], 200.0)
        self.assertEqual(data["no_stats_backoff_count"], 8)
        self.assertEqual(data["games_skipped_by_no_stats_backoff"], 2)

    def test_H10_cycle_under_target_no_delay(self):
        """Heartbeat marca cycle_over_target=False quando ciclo dentro do alvo."""
        import live_daemon as ld
        old_hb = ld.HEARTBEAT_FILE
        ld.HEARTBEAT_FILE = self.heartbeat
        try:
            ld.save_heartbeat(
                scan_number=1,
                last_scan_at=datetime.now(timezone.utc).isoformat(),
                last_scan_duration_seconds=95.0,
                target_scan_interval_seconds=120,
                total_live_games_discovered=10,
                games_discovered=10,
                games_with_cc_available=8,
                games_without_cc_available=2,
                games_scanned=8,
                games_scanned_this_cycle=8,
                games_skipped_this_cycle=0,
                games_finished_or_not_live=0,
                no_stats_backoff_count=0,
                games_skipped_by_no_stats_backoff=0,
                telegram_ready=True,
                telegram_sent_last_cycle=1,
                errors_last_cycle=0,
            )
        finally:
            ld.HEARTBEAT_FILE = old_hb

        data = json.loads(self.heartbeat.read_text())
        self.assertFalse(data["cycle_over_target"])
        self.assertEqual(data["scan_delay_seconds"], 0)

    # ──────── H8 ────────
    def test_H8_heartbeat_registers_counters(self):
        import live_daemon as ld
        old_hb = ld.HEARTBEAT_FILE
        ld.HEARTBEAT_FILE = self.heartbeat
        try:
            ld.save_heartbeat(scan_number=42,
                              last_scan_at=datetime.now(timezone.utc).isoformat(),
                              last_scan_duration_seconds=110.0,
                              total_live_games_discovered=53,
                              games_discovered=53,
                              games_with_cc_available=15,
                              games_without_cc_available=38,
                              games_scanned=12,
                              games_scanned_this_cycle=12,
                              games_skipped_this_cycle=3,
                              telegram_ready=True,
                              telegram_sent_last_cycle=2,
                              errors_last_cycle=0)
        finally:
            ld.HEARTBEAT_FILE = old_hb

        data = json.loads(self.heartbeat.read_text())
        self.assertEqual(data["games_discovered"], 53)
        self.assertEqual(data["games_with_cc_available"], 15)
        self.assertEqual(data["games_without_cc_available"], 38)
        self.assertEqual(data["games_scanned"], 12)
        self.assertEqual(data["games_scanned_this_cycle"], 12)
        self.assertEqual(data["games_skipped_this_cycle"], 3)
        self.assertEqual(data["telegram_sent_last_cycle"], 2)


# ──────────────────────────────────────────────────────────────────────
# C1-C6 — CADÊNCIA E COBERTURA
# ──────────────────────────────────────────────────────────────────────


class TestCadenceAndCoverage(unittest.TestCase):

    def setUp(self):
        # Forçar parse dos args com defaults
        from argparse import ArgumentParser
        # Simular o parser do live_daemon
        # (replicamos o subset relevante para validar defaults sem rodar main())
        self.parser = ArgumentParser()
        self.parser.add_argument("--scan-interval", type=int, default=120)
        self.parser.add_argument("--discovery-interval", type=int, default=120)
        self.parser.add_argument("--mode", choices=["codigo_3_1", "motor_v12"],
                                  default="codigo_3_1")

    # ──────── C1 ────────
    def test_C1_discovery_interval_is_120(self):
        # Verifica no parser real do live_daemon que o default é 120
        import argparse
        import importlib
        import live_daemon as ld
        # Construir parser equivalente ao do main()
        defaults = {}
        # Heurística: chama main com --help capturando defaults seria invasivo.
        # Em vez disso, leio o source pra extrair o default.
        source = Path(ld.__file__).read_text()
        self.assertIn('"--discovery-interval", type=int, default=120',
                      source,
                      "discovery_interval default deve ser 120s (dossiê v1.1 §12)")

    # ──────── C2 ────────
    def test_C2_scan_interval_is_120(self):
        import live_daemon as ld
        source = Path(ld.__file__).read_text()
        self.assertIn('"--scan-interval", type=int, default=120',
                      source,
                      "scan_interval default deve ser 120s (dossiê v1.1 §10)")

    # ──────── C3 ────────
    def test_C3_new_game_with_cc_enters_watchlist(self):
        # Cenário: jogo novo descoberto pela discovery, com CC > 0 → entra Tier 1
        from src.catalog import Catalog
        from src.watchlist import build_watchlist
        cat = Catalog(persist_path=None)
        cat.upsert_discovered("FS_new", "http://x/new/")
        # Marca como já carregou stats com CC (simula 1º scan bem-sucedido)
        cat.mark_scanned("FS_new", minute=40, score="0-0", bc_sum=2)
        wl = build_watchlist(cat, max_size=15, tier3_reserved=3)
        self.assertIn("FS_new", wl,
                      "Jogo novo com CC > 0 e na janela operacional deve entrar na watchlist")

    # ──────── C4 ────────
    def test_C4_game_without_cc_is_marked_no_stats(self):
        # Quando o read_match retorna None, o catálogo conta no_stats
        # → contado em games_without_cc_available no heartbeat.
        from src.catalog import Catalog
        cat = Catalog(persist_path=None)
        cat.upsert_discovered("FS_nostats", "http://x/nostats/")
        cat.mark_no_stats("FS_nostats")
        entry = cat.get("FS_nostats")
        self.assertEqual(entry["no_stats_count"], 1)
        self.assertFalse(entry["ever_loaded_stats"],
                         "ever_loaded_stats=False indica jogo sem CC disponível")
        # No heartbeat, esse jogo conta em games_without_cc_available

    # ──────── C5 ────────
    def test_C5_all_games_with_cc_are_eligible(self):
        # Todos os jogos com ever_loaded_stats=True devem aparecer no contador
        # games_with_cc_available do heartbeat.
        from src.catalog import Catalog
        cat = Catalog(persist_path=None)
        for i in range(5):
            mid = f"FS_with_cc_{i}"
            cat.upsert_discovered(mid, f"http://x/{i}/")
            cat.mark_scanned(mid, minute=40, score="0-0", bc_sum=1)
        for i in range(3):
            mid = f"FS_no_cc_{i}"
            cat.upsert_discovered(mid, f"http://x/no/{i}/")
            cat.mark_no_stats(mid)

        all_games = cat.all()
        with_cc = [g for g in all_games if g.get("ever_loaded_stats")]
        without_cc = [g for g in all_games if not g.get("ever_loaded_stats")]
        self.assertEqual(len(with_cc), 5,
                         "Todos os 5 jogos com CC devem ser contabilizados como elegíveis")
        self.assertEqual(len(without_cc), 3,
                         "Os 3 jogos sem CC devem ser contabilizados como inelegíveis")

    # ──────── C6 ────────
    def test_C6_skipped_games_recorded_in_heartbeat(self):
        # Quando watchlist limita a 15 mas há 20 jogos elegíveis → 5 skipped
        from src.catalog import Catalog
        import live_daemon as ld

        cat = Catalog(persist_path=None)
        for i in range(20):
            mid = f"FS_g_{i:02d}"
            cat.upsert_discovered(mid, f"http://x/{i}/")
            cat.mark_scanned(mid, minute=40, score="0-0", bc_sum=1)

        cc_available_total = sum(1 for g in cat.all() if g.get("ever_loaded_stats"))
        scanned_now = 15  # watchlist max_size = 15
        skipped = max(0, cc_available_total - scanned_now)
        self.assertEqual(cc_available_total, 20)
        self.assertEqual(skipped, 5,
                         "Com 20 elegíveis e 15 escaneados, games_skipped_this_cycle=5")

        # Salvar heartbeat com esses valores e verificar persistência
        tmp = Path(tempfile.mkdtemp()) / "heartbeat.json"
        old_hb = ld.HEARTBEAT_FILE
        ld.HEARTBEAT_FILE = tmp
        try:
            ld.save_heartbeat(scan_number=1,
                              last_scan_at=datetime.now(timezone.utc).isoformat(),
                              last_scan_duration_seconds=120.0,
                              total_live_games_discovered=20,
                              games_discovered=20,
                              games_with_cc_available=cc_available_total,
                              games_without_cc_available=0,
                              games_scanned=scanned_now,
                              games_scanned_this_cycle=scanned_now,
                              games_skipped_this_cycle=skipped,
                              telegram_ready=True,
                              telegram_sent_last_cycle=0,
                              errors_last_cycle=0)
        finally:
            ld.HEARTBEAT_FILE = old_hb

        data = json.loads(tmp.read_text())
        self.assertEqual(data["games_skipped_this_cycle"], 5)


# ──────────────────────────────────────────────────────────────────────


def _run_all():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestHeartbeatAndWatchdog))
    suite.addTests(loader.loadTestsFromTestCase(TestCadenceAndCoverage))
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run_all())
