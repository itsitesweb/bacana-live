"""
Testes da função de decisão do self-watchdog (`live_daemon._self_watchdog_decision`).

Cobre os 5 cenários críticos:
- S1: Warmup ativo → nunca mata
- S2: Warmup passou + heartbeat NÃO EXISTE → MATA (BUG do daemon paralisado)
- S3: Warmup passou + heartbeat de daemon ANTERIOR → MATA
- S4: Heartbeat fresco do daemon atual mas TRAVADO (>8min) → MATA
- S5: Heartbeat fresco e saudável → NÃO mata

Bug histórico que motivou esses testes:
- Daemon do CÓDIGO 3:1 ficou paralisado no Playwright;
- self-watchdog ignorava porque heartbeat.json não existia;
- bash não reiniciava porque python não morria.
"""
import json
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Stub Playwright (live_daemon importa indiretamente)
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from live_daemon import _self_watchdog_decision


class TestSelfWatchdog(unittest.TestCase):
    """5 cenários cobrindo a função pura."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.hb = self.tmp / "heartbeat.json"

    # ─────────────── S1 ───────────────
    def test_S1_warmup_never_kills(self):
        """Durante o warmup (primeiros 5min) NUNCA mata, mesmo sem heartbeat."""
        ps = datetime.now(timezone.utc)
        now = ps + timedelta(seconds=100)  # 100s desde start
        kill, motivo = _self_watchdog_decision(ps, now, self.hb)
        self.assertFalse(kill, f"Não deveria matar em warmup. Motivo: {motivo}")
        self.assertIn("warmup", motivo)

    # ─────────────── S2 (BUG CRÍTICO) ───────────────
    def test_S2_no_heartbeat_after_warmup_kills(self):
        """Warmup passou + heartbeat nunca foi escrito → MATA.

        ESTE É O BUG QUE PARALISOU O CÓDIGO 3:1 EM PRODUÇÃO.
        """
        ps = datetime.now(timezone.utc) - timedelta(minutes=15)
        now = datetime.now(timezone.utc)
        self.assertFalse(self.hb.exists(), "Setup: hb não pode existir")
        kill, motivo = _self_watchdog_decision(ps, now, self.hb)
        self.assertTrue(kill, "Deveria matar — heartbeat não existe após 15min!")
        self.assertIn("sem heartbeat", motivo)

    # ─────────────── S3 ───────────────
    def test_S3_old_heartbeat_from_previous_daemon_kills(self):
        """Warmup passou + heartbeat é de daemon anterior → MATA."""
        ps = datetime.now(timezone.utc) - timedelta(minutes=15)
        # Heartbeat escrito ANTES de process_start (= daemon antigo)
        old_ts = (ps - timedelta(minutes=30)).isoformat()
        self.hb.write_text(json.dumps({"last_scan_at": old_ts}))
        now = datetime.now(timezone.utc)
        kill, motivo = _self_watchdog_decision(ps, now, self.hb)
        self.assertTrue(kill, "Deveria matar — heartbeat é do daemon anterior!")
        self.assertIn("daemon anterior", motivo)

    # ─────────────── S4 ───────────────
    def test_S4_stuck_cycle_after_warmup_kills(self):
        """Heartbeat do daemon atual mas > 8min sem atualizar → MATA."""
        ps = datetime.now(timezone.utc) - timedelta(minutes=20)
        # Heartbeat escrito 10min atrás, APÓS process_start
        stuck_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        self.hb.write_text(json.dumps({"last_scan_at": stuck_ts}))
        now = datetime.now(timezone.utc)
        kill, motivo = _self_watchdog_decision(ps, now, self.hb)
        self.assertTrue(kill, "Deveria matar — ciclo travado há 10min!")
        self.assertIn("limite", motivo)

    # ─────────────── S5 ───────────────
    def test_S5_healthy_heartbeat_does_not_kill(self):
        """Heartbeat fresco (< 8min) do daemon atual → NÃO mata."""
        ps = datetime.now(timezone.utc) - timedelta(minutes=20)
        # Heartbeat escrito 2min atrás
        fresh_ts = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        self.hb.write_text(json.dumps({"last_scan_at": fresh_ts}))
        now = datetime.now(timezone.utc)
        kill, motivo = _self_watchdog_decision(ps, now, self.hb)
        self.assertFalse(kill, f"Não deveria matar — saudável. Motivo: {motivo}")
        self.assertIn("OK", motivo)

    # ─────────────── Defensivos ───────────────
    def test_S6_corrupt_heartbeat_kills(self):
        """Heartbeat ilegível (JSON quebrado) → MATA (não confunde com saudável)."""
        ps = datetime.now(timezone.utc) - timedelta(minutes=15)
        self.hb.write_text("{ NOT JSON")
        kill, motivo = _self_watchdog_decision(
            ps, datetime.now(timezone.utc), self.hb)
        self.assertTrue(kill)
        self.assertIn("ilegível", motivo)

    def test_S7_heartbeat_without_timestamp_kills(self):
        """Heartbeat sem last_scan_at → MATA."""
        ps = datetime.now(timezone.utc) - timedelta(minutes=15)
        self.hb.write_text(json.dumps({"status": "alive"}))  # sem last_scan_at
        kill, motivo = _self_watchdog_decision(
            ps, datetime.now(timezone.utc), self.hb)
        self.assertTrue(kill)
        self.assertIn("sem timestamp", motivo)


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(unittest.TestLoader().loadTestsFromTestCase(TestSelfWatchdog))
    sys.exit(0 if res.wasSuccessful() else 1)
