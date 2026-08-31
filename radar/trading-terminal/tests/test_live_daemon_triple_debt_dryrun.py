"""
Testes do PLUG DRY-RUN da TRINCA no live_daemon.

Garantem:
  DRY1. helper appenda 1 linha por chamada no audit log
  DRY2. helper não muta MatchState nem Decision
  DRY3. live_daemon importa src.triple_debt_filter (alias _triple_debt_*)
  DRY4. existem 2 call sites (run_cycle + run_cycle_watchlist),
        ambos gated por `action != "NO_ACTION"`
  DRY5. helper falha silenciosamente se algo crashar (try/except)
  DRY6. módulo TRINCA não importa NEM chama nada de Telegram
  DRY7. nenhum arquivo de produção (banco limpo, logs antigos) é
        tocado pelo plug
  DRY8. Telegram path NÃO é afetado: mesma decisão produz mesmo
        recommended_action antes e depois do audit (puro dry-run)
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy_token_for_test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "dummy_chat_id_for_test")

# Stub Playwright (live_daemon importa flashscore_adapter)
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
from src.models import MatchState, Decision, DerivedVars  # noqa: E402
from src import triple_debt_filter as TDF  # noqa: E402


LIVE_DAEMON_PATH = Path(__file__).resolve().parent.parent / "live_daemon.py"
TDF_PATH = (Path(__file__).resolve().parent.parent
             / "src" / "triple_debt_filter.py")


def _build_ms(home_cc=3, away_cc=0, home_xg=1.20, away_xg=0.20,
                home_xgot=1.05, away_xgot=0.05,
                home_score=0, away_score=0, minute=35):
    return MatchState(
        match_id="FS_TEST123", home="TestHome", away="TestAway",
        minute=minute, home_score=home_score, away_score=away_score,
        home_xg=home_xg, away_xg=away_xg,
        home_xgot=home_xgot, away_xgot=away_xgot,
        home_bc=home_cc, away_bc=away_cc,
        home_xg_raw=home_xg, away_xg_raw=away_xg,
        home_xgot_raw=home_xgot, away_xgot_raw=away_xgot,
        home_bc_raw=home_cc, away_bc_raw=away_cc,
    )


def _build_decision(action="ENTER_OVER_PREMIUM",
                       sev="URGENT", market_target="Over 2.5"):
    return Decision(
        recommended_action=action,
        message_severity=sev,
        market_target=market_target,
        confidence_tier="A-",
        operator_instruction="entrada 1u",
        signal_valid_until=0,
        game_profile="STRONG",
        blocked_reason="",
    )


# === DRY1, DRY2 — helper isolado ============================================
class TestDRY_HelperBehavior(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.audit_path = self.tmp / "triple_debt_audit.jsonl"
        # Redireciona o path default do módulo TRINCA pro tmp via patch
        self._orig_audit_path = TDF.AUDIT_LOG_PATH
        TDF.AUDIT_LOG_PATH = self.audit_path

    def tearDown(self):
        TDF.AUDIT_LOG_PATH = self._orig_audit_path
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_DRY1_helper_appenda_uma_linha(self):
        ms = _build_ms()
        d  = _build_decision()
        live_daemon._triple_debt_dry_run_audit(ms, d)
        self.assertTrue(self.audit_path.exists())
        lines = self.audit_path.read_text().splitlines()
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        self.assertEqual(rec["match_id"], "FS_TEST123")
        self.assertEqual(rec["original_tier"], "URGENT")
        self.assertEqual(rec["original_alert_type"], "ENTER_OVER_PREMIUM")
        self.assertIn("triple_debt_formed", rec)
        self.assertIn("scope", rec)
        self.assertIn("cc_in_scope", rec)
        self.assertIn("xg_in_scope", rec)
        self.assertIn("xgot_in_scope", rec)
        self.assertIn("goals_in_scope", rec)
        self.assertIn("cc_debt", rec)
        self.assertIn("xg_debt", rec)
        self.assertIn("xgot_debt", rec)
        self.assertIn("would_block_signal", rec)
        self.assertIn("block_reason", rec)
        self.assertIn("failed_reasons", rec)

    def test_DRY2a_helper_nao_muta_match_state(self):
        ms = _build_ms()
        snap = {
            k: getattr(ms, k) for k in
            ("match_id","home","away","minute","home_score","away_score",
             "home_xg","away_xg","home_xgot","away_xgot",
             "home_bc","away_bc")
        }
        live_daemon._triple_debt_dry_run_audit(ms, _build_decision())
        after = {k: getattr(ms, k) for k in snap}
        self.assertEqual(snap, after,
                          "MatchState foi mutado pelo audit dry-run")

    def test_DRY2b_helper_nao_muta_decision(self):
        d = _build_decision()
        snap = (d.recommended_action, d.message_severity,
                 d.market_target, d.confidence_tier, d.blocked_reason)
        live_daemon._triple_debt_dry_run_audit(_build_ms(), d)
        after = (d.recommended_action, d.message_severity,
                  d.market_target, d.confidence_tier, d.blocked_reason)
        self.assertEqual(snap, after,
                          "Decision foi mutado pelo audit dry-run")

    def test_DRY5a_helper_silencioso_quando_TDF_crasha(self):
        """Mesmo se validate levantar exceção, helper não propaga."""
        def _explode(_): raise RuntimeError("boom")
        with patch.object(live_daemon, "_triple_debt_validate", _explode):
            try:
                live_daemon._triple_debt_dry_run_audit(_build_ms(),
                                                         _build_decision())
            except Exception as e:
                self.fail(f"helper levantou exceção em vez de engolir: {e}")

    def test_DRY5b_helper_silencioso_quando_ms_eh_lixo(self):
        """ms sem atributos não deve derrubar."""
        try:
            live_daemon._triple_debt_dry_run_audit(object(),
                                                     _build_decision())
        except Exception as e:
            self.fail(f"helper levantou exceção: {e}")


# === DRY3, DRY4 — wiring no live_daemon ====================================
class TestDRY_WiringDaemon(unittest.TestCase):

    def test_DRY3_live_daemon_importa_modulo_TRINCA(self):
        """live_daemon precisa importar (com alias) validate + audit_log."""
        src = LIVE_DAEMON_PATH.read_text()
        self.assertIn("from src.triple_debt_filter import", src)
        self.assertIn("validate_triple_debt_filter as _triple_debt_validate",
                      src)
        self.assertIn("audit_log as _triple_debt_audit_log", src)

    def test_DRY4a_existem_2_call_sites_gated_por_no_action(self):
        """Esperado: 2 chamadas a _triple_debt_dry_run_audit(ms, decision),
        cada uma logo após `if action != "NO_ACTION":`."""
        src = LIVE_DAEMON_PATH.read_text()
        # Conta apenas linhas INDENTADAS (chamada dentro de bloco) — exclui
        # a definição da função `def _triple_debt_dry_run_audit(...)`.
        lines = src.splitlines()
        idx_calls = [
            i for i, ln in enumerate(lines)
            if "_triple_debt_dry_run_audit(ms, decision)" in ln
            and not ln.lstrip().startswith("def ")
        ]
        self.assertEqual(len(idx_calls), 2,
            f"Esperava 2 call sites, achei {len(idx_calls)}")
        for idx in idx_calls:
            window = lines[max(0, idx-5):idx]
            has_gate = any('if action != "NO_ACTION"' in ln for ln in window)
            self.assertTrue(has_gate,
                f"call site na linha {idx+1} sem gate "
                f"`if action != \"NO_ACTION\":` próximo")

    def test_DRY4b_helper_definido_uma_vez(self):
        src = LIVE_DAEMON_PATH.read_text()
        defs = re.findall(r"^def _triple_debt_dry_run_audit\(", src, re.M)
        self.assertEqual(len(defs), 1)

    def test_DRY4c_call_sites_estao_ANTES_do_telegram_send(self):
        """Garantir que o audit roda ANTES de tg.send_decision."""
        src = LIVE_DAEMON_PATH.read_text()
        lines = src.splitlines()
        send_lines = [i for i, ln in enumerate(lines)
                       if "tg.send_decision(" in ln]
        audit_lines = [i for i, ln in enumerate(lines)
                        if "_triple_debt_dry_run_audit(ms, decision)" in ln]
        # Cada audit_line precisa ter um send_line APÓS (não antes)
        for a in audit_lines:
            subsequent_sends = [s for s in send_lines if s > a]
            self.assertGreater(len(subsequent_sends), 0,
                f"audit na linha {a+1} sem send subsequente")


# === DRY6 — TRINCA não toca Telegram =======================================
class TestDRY_NaoTelegrama(unittest.TestCase):

    def test_DRY6_modulo_TRINCA_nao_importa_telegram(self):
        src = TDF_PATH.read_text()
        import_lines = [ln for ln in src.splitlines()
                         if re.match(r"^\s*(import|from)\s+", ln)]
        for ln in import_lines:
            for forbidden in ("telegram_client", "telegram_formatter",
                               "TelegramClient", "requests", "http"):
                self.assertNotIn(forbidden, ln,
                    f"TRINCA toca Telegram/HTTP via: {ln}")


# === DRY7 — produção intocada ==============================================
class TestDRY_ProducaoIntocada(unittest.TestCase):

    def test_DRY7_arquivos_legacy_existentes_intactos(self):
        """O plug não substituiu nenhum arquivo de produção; o módulo
        TRINCA não está dentro de codigo_3_1/rules_*."""
        # Confirma que os arquivos legacy ainda existem (não foram apagados)
        for f in ("src/codigo_3_1.py", "src/rules_over.py",
                   "src/rules_back.py", "src/telegram_client.py",
                   "src/telegram_formatter.py", "src/coverage_guard.py",
                   "src/signals_persistence.py",
                   "logs/rule_3_1_2_signals.jsonl"):
            self.assertTrue(
                (LIVE_DAEMON_PATH.parent / f).exists(),
                f"arquivo legacy sumiu: {f}")
        # Confirma que NENHUM desses arquivos importou triple_debt_filter
        # (regra antiga não conhece a nova)
        for f in ("src/codigo_3_1.py", "src/rules_over.py",
                   "src/rules_back.py", "src/coverage_guard.py",
                   "src/signals_persistence.py", "src/telegram_client.py",
                   "src/telegram_formatter.py"):
            content = (LIVE_DAEMON_PATH.parent / f).read_text()
            self.assertNotIn("triple_debt_filter", content,
                f"legacy {f} importou TRINCA (acoplamento indevido)")


# === DRY8 — Telegram path inalterado pelo audit ============================
class TestDRY_TelegramPathPreservado(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = TDF.AUDIT_LOG_PATH
        TDF.AUDIT_LOG_PATH = self.tmp / "audit.jsonl"

    def tearDown(self):
        TDF.AUDIT_LOG_PATH = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_DRY8a_decision_action_intacto_apos_audit(self):
        """O audit não pode alterar o recommended_action — Telegram deve
        despachar pelo mesmo valor que tinha antes do audit."""
        ms = _build_ms()
        d  = _build_decision(action="ENTER_BACK_T1_MAIN", sev="ACTION")
        before = d.recommended_action
        live_daemon._triple_debt_dry_run_audit(ms, d)
        self.assertEqual(d.recommended_action, before)

    def test_DRY8b_audit_nao_chama_tg_send_decision(self):
        """O helper não pode invocar tg.send_decision. Patch o atributo
        e garante que NÃO foi chamado."""
        called = {"sent": False}
        class FakeTG:
            def send_decision(self, *a, **kw):
                called["sent"] = True
        # _triple_debt_dry_run_audit recebe só ms e decision; nem vê tg.
        # Esse teste é tautológico (TG nem é parâmetro), mas serve de
        # documentação do contrato — caso alguém adicione tg no futuro.
        live_daemon._triple_debt_dry_run_audit(_build_ms(),
                                                 _build_decision())
        self.assertFalse(called["sent"])


def _run():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (TestDRY_HelperBehavior, TestDRY_WiringDaemon,
                TestDRY_NaoTelegrama, TestDRY_ProducaoIntocada,
                TestDRY_TelegramPathPreservado):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    r = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run())
