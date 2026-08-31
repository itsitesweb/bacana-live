"""
Teste do FLUXO REAL do live_daemon — não apenas do TelegramClient.

Cobertura obrigatória:
  D1. MANUAL_REVIEW no daemon → tg.send_decision NÃO é chamado.
  D2. MANUAL_REVIEW no daemon → JSONL grava telegram_sent=False
       e telegram_filter_reason="MANUAL_REVIEW_LOG_ONLY".
  D3. MANUAL_REVIEW no daemon → stdout NÃO contém "Telegram enviado".
  D4. ENTER_BACK_T1_MAIN no daemon → tg.send_decision É chamado.
  D5. ENTER_BACK_T1_MAIN no daemon → quando entrega ok,
       JSONL grava telegram_sent=True e telegram_filter_reason="SENT".
  D6. Defense-in-depth no client: mesmo se alguém burlar o guard do daemon
       e chamar tg.send_decision com MANUAL_REVIEW, ele retorna
       SendResult(False, "MANUAL_REVIEW_LOG_ONLY") e NÃO faz HTTP POST.
"""
import io
import json
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Env vars antes de importar telegram_client (lê no __init__)
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy_token_for_test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "dummy_chat_id_for_test")

# ─── Stub Playwright/FlashscoreReader (não usados neste teste) ──────────
# live_daemon importa src.flashscore_adapter (que importa playwright).
# Em ambiente de teste/CI sem Playwright, injetamos um stub mínimo.
if "playwright" not in sys.modules:
    _pw_stub = types.ModuleType("playwright")
    _pw_sync = types.ModuleType("playwright.sync_api")
    class _Dummy:
        pass
    _pw_sync.sync_playwright = lambda: _Dummy()
    _pw_sync.Page = _Dummy
    _pw_sync.BrowserContext = _Dummy
    sys.modules["playwright"] = _pw_stub
    sys.modules["playwright.sync_api"] = _pw_sync

import live_daemon  # noqa: E402
from src.models import MatchState, Decision, DerivedVars  # noqa: E402
from src.telegram_client import TelegramClient, SendResult  # noqa: E402


def _make_ms(action_hint="manual"):
    # Para "enter": valores fortes o suficiente pra TRINCA formar
    # (home unilateral 5/5) e DT não bloquear (home dominante, não
    # trailing). Indispensável após o enforcement Turbo no daemon.
    if action_hint == "enter":
        # _raw populados (dado presente no feed) pra TRINCA não bloquear.
        return MatchState(
            match_id=f"test_{action_hint}",
            home="RW Essen", away="Furth",
            home_score=1, away_score=0,
            minute=55,
            home_bc=6, away_bc=0,
            home_xg=2.10, away_xg=0.10,
            home_xgot=2.05, away_xgot=0.05,
            home_bc_raw=6, away_bc_raw=0,
            home_xg_raw=2.10, away_xg_raw=0.10,
            home_xgot_raw=2.05, away_xgot_raw=0.05,
        )
    # Demais casos (manual, defense): MANUAL_REVIEW nunca chega no TURBO
    # (guard antes), mas populamos _raw pra não falsamente disparar
    # missing_xgot caso o fluxo mude no futuro.
    return MatchState(
        match_id=f"test_{action_hint}",
        home="RW Essen", away="Furth",
        home_score=1, away_score=0,
        minute=1,
        home_bc=3, away_bc=1,
        home_xgot=0.5, away_xgot=0.3,
        home_xg=0.7, away_xg=0.4,
        home_bc_raw=3, away_bc_raw=1,
        home_xgot_raw=0.5, away_xgot_raw=0.3,
        home_xg_raw=0.7, away_xg_raw=0.4,
    )


def _make_decision(action, blocked_reason="", profile="MIXED"):
    dec = Decision()
    dec.recommended_action = action
    dec.blocked_reason = blocked_reason
    dec.game_profile = profile
    dec.operator_instruction = "test"
    dec.message_severity = "ACTION"
    if action == "ENTER_BACK_T1_MAIN":
        dec.confidence_tier = "A"
        dec.market_target = "BACK_DOMINANT_TEAM"
        dec.signal_valid_until = 47
    return dec


def _make_derived():
    return DerivedVars()


def _make_tg():
    cfg = {"telegram": {"enabled": True,
                        "bot_token_env": "TELEGRAM_BOT_TOKEN",
                        "chat_id_env": "TELEGRAM_CHAT_ID",
                        "simulation_tag": "[SIMULAÇÃO]",
                        "anti_spam_minutes": 5,
                        "manual_review_cooldown_minutes": 30,
                        "state_file": ""}}
    return TelegramClient(cfg)


class FakeReader:
    """FlashscoreReader stub — devolve sempre o mesmo MatchState."""
    def __init__(self, ms):
        self._ms = ms

    def read_match(self, url):
        return self._ms


def _run_daemon_cycle(ms, action, log_file=None):
    """
    Executa run_cycle com:
      - reader fake (devolve `ms`)
      - run_scan monkey-patchado para devolver Decision(action)
      - tg.send_decision espionado
      - LOG_FILE/STATE_FILE temporários
    Retorna (captured_stdout, jsonl_entries, send_calls, tg_used).
    """
    tmpdir = tempfile.mkdtemp()
    if log_file is None:
        log_file = Path(tmpdir) / "daemon_decisions.jsonl"
    state_file = Path(tmpdir) / "daemon_state.json"

    reader = FakeReader(ms)
    cfg = {"telegram": {"enabled": True,
                        "bot_token_env": "TELEGRAM_BOT_TOKEN",
                        "chat_id_env": "TELEGRAM_CHAT_ID",
                        "simulation_tag": "[SIMULAÇÃO]",
                        "anti_spam_minutes": 5,
                        "manual_review_cooldown_minutes": 30,
                        "state_file": str(Path(tmpdir) / "tg_state.json")}}
    tg = TelegramClient(cfg)

    # Espião na chamada real de send_decision
    send_calls = []
    original_send = tg.send_decision

    def spy_send(decision, _ms, _d):
        send_calls.append({
            "action": decision.recommended_action,
            "blocked_reason": decision.blocked_reason,
            "match": f"{_ms.home}|{_ms.away}",
        })
        # Para a ação positiva (ENTER), simula entrega bem-sucedida sem HTTP.
        if decision.recommended_action.startswith("ENTER_"):
            return SendResult(True, "SENT")
        # Para qualquer outro chamado que não devia ter chegado aqui,
        # delega para a impl real (que vai filtrar).
        return original_send(decision, _ms, _d)

    decision = _make_decision(action)
    derived = _make_derived()

    buf = io.StringIO()
    with redirect_stdout(buf), \
         patch.object(live_daemon, "LOG_FILE", log_file), \
         patch.object(live_daemon, "STATE_FILE", state_file), \
         patch.object(live_daemon, "run_scan",
                      lambda _ms, _cfg: (decision, derived)), \
         patch.object(tg, "send_decision", side_effect=spy_send):
        live_daemon.run_cycle(reader, ["http://fake/jogo/x/"], cfg, tg, {})

    entries = []
    if log_file.exists():
        for line in log_file.read_text().splitlines():
            entries.append(json.loads(line))

    return buf.getvalue(), entries, send_calls, tg


# ─────────────────────────────────────────────────────────────────────


class TestDaemonManualReview(unittest.TestCase):

    def test_D1_manual_review_does_not_call_send_decision(self):
        ms = _make_ms("manual")
        _stdout, entries, send_calls, _tg = _run_daemon_cycle(
            ms, "MANUAL_REVIEW"
        )
        self.assertEqual(
            send_calls, [],
            "tg.send_decision NÃO pode ser chamado em MANUAL_REVIEW. "
            f"Foi chamado {len(send_calls)}x: {send_calls}"
        )

    def test_D2_manual_review_logs_filter_reason(self):
        ms = _make_ms("manual")
        _stdout, entries, _send, _tg = _run_daemon_cycle(
            ms, "MANUAL_REVIEW"
        )
        self.assertEqual(len(entries), 1, "Deve haver 1 entrada no JSONL")
        e = entries[0]
        self.assertEqual(e["recommended_action"], "MANUAL_REVIEW")
        self.assertEqual(e["telegram_sent"], False,
                         "telegram_sent deve ser False")
        self.assertEqual(e["telegram_filter_reason"], "MANUAL_REVIEW_LOG_ONLY",
                         "telegram_filter_reason deve ser MANUAL_REVIEW_LOG_ONLY")

    def test_D3_manual_review_stdout_does_not_say_enviado(self):
        ms = _make_ms("manual")
        stdout, _entries, _send, _tg = _run_daemon_cycle(
            ms, "MANUAL_REVIEW"
        )
        self.assertNotIn("Telegram enviado", stdout,
                         f"stdout NÃO pode conter 'Telegram enviado'. "
                         f"Saída:\n{stdout}")
        self.assertIn("MANUAL_REVIEW_LOG_ONLY", stdout,
                      "stdout deve mencionar MANUAL_REVIEW_LOG_ONLY")

    def test_D4_enter_calls_send_decision(self):
        ms = _make_ms("enter")
        _stdout, _entries, send_calls, _tg = _run_daemon_cycle(
            ms, "ENTER_BACK_T1_MAIN"
        )
        self.assertEqual(len(send_calls), 1,
                         f"ENTER_BACK_T1_MAIN deve chamar send_decision 1x. "
                         f"Chamadas: {send_calls}")
        self.assertEqual(send_calls[0]["action"], "ENTER_BACK_T1_MAIN")

    def test_D5_enter_logs_sent_true(self):
        ms = _make_ms("enter")
        stdout, entries, _send, _tg = _run_daemon_cycle(
            ms, "ENTER_BACK_T1_MAIN"
        )
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e["telegram_sent"], True,
                         "telegram_sent deve ser True para ENTER entregue")
        self.assertEqual(e["telegram_filter_reason"], "SENT")
        self.assertIn("Telegram enviado", stdout)

    def test_D6_client_short_circuits_manual_review(self):
        """Defense-in-depth: mesmo se daemon esquecer o guard, o client bloqueia."""
        tg = _make_tg()
        ms = _make_ms("defense")
        dec = _make_decision("MANUAL_REVIEW",
                             blocked_reason="zona mista 3x1 com xGOT ambíguo")
        derived = _make_derived()

        http_calls = []
        with patch.object(tg, "_send_raw",
                          side_effect=lambda _t: http_calls.append(_t) or True):
            result = tg.send_decision(dec, ms, derived)

        self.assertFalse(result.sent, "MANUAL_REVIEW jamais pode entregar")
        self.assertEqual(result.reason, "MANUAL_REVIEW_LOG_ONLY")
        self.assertEqual(http_calls, [],
                         "Nenhuma chamada HTTP pode ter ocorrido para MANUAL_REVIEW")
        # __bool__ compat
        self.assertFalse(bool(result),
                         "SendResult deve ser falsy quando sent=False")


# ─────────────────────────────────────────────────────────────────────


def _run_all():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestDaemonManualReview)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run_all())
