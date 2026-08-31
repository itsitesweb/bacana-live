"""
Teste de regressão CRÍTICO — reproduz o incidente real:

  Sporting Kansas City II x Austin FC II — Telegram em 22/05/2026:
    21:40 ENTER_OVER_PREMIUM (min 36, CC 1x2, total 3, MinCC 1)
    21:43 EXIT_OVER (min 39, "Motivo: FECHAR POSIÇÃO AGORA")          ← BUG
    21:53 ENTER_OVER_PREMIUM (min 45, CC 1x2 INALTERADO)               ← BUG
    21:56 EXIT_OVER (min 45, "Motivo: Jogo sem big chance há 999 min") ← BUG

Causas raízes auditadas:
  1. utils._parse computes 999 quando minute_of_last_match_bc=0 (state vazio).
  2. update_state nunca inicializava minute_of_last_match_bc ao entrar em Over.
  3. inject_state nunca recuperava minute_of_last_*_bc do state persistido.
  4. post_position aceitava 999 como condição válida pra disparar EXIT.
  5. Cooldown de 5 min expirava antes de nova CC aparecer, permitindo reentry.

Testes desta suíte verificam que TODAS as 4 correções estão ativas.
"""
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

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
from src.models import MatchState, Decision, DerivedVars
from src.decision_engine import run_scan, load_config
from src.utils import compute_derived, UNKNOWN_LAST_BC
from src.post_position import manage_position


# ─── Cenário Sporting KC II x Austin FC II ──────────────────────────────

def _make_sporting_state(minute: int, home_bc: int, away_bc: int,
                          home_score: int = 0, away_score: int = 2,
                          home_xgot: float = 0.16, away_xgot: float = 1.38) -> MatchState:
    return MatchState(
        match_id="FS_sporting_austin",
        home="Sporting Kansas City II",
        away="Austin FC II",
        minute=minute,
        home_score=home_score,
        away_score=away_score,
        home_bc=home_bc,
        away_bc=away_bc,
        home_xgot=home_xgot,
        away_xgot=away_xgot,
        home_xg=0.5,
        away_xg=1.0,
    )


def _fake_enter_decision(target_line: float = 2.5) -> Decision:
    d = Decision()
    d.recommended_action = "ENTER_OVER_PREMIUM"
    d.market_target = "OVER 2.5"
    d.confidence_tier = "A"
    d.target_over_line = target_line
    d.game_profile = "BILATERAL_OVER"
    return d


def _fake_exit_decision() -> Decision:
    d = Decision()
    d.recommended_action = "EXIT_OVER"
    d.blocked_reason = "(motivo qualquer)"
    return d


# ─────────────────────────────────────────────────────────────────────────


class TestSentinelDoesNotTriggerExit(unittest.TestCase):
    """Fix A: minutes_since_last_match_bc=999 NUNCA gera EXIT_OVER."""

    def test_E1_unknown_last_bc_never_exits_by_no_cc(self):
        # Cenário: jogo em Over recém-carregado, state vazio,
        # minute_of_last_match_bc=0 → utils retorna 999.
        ms = _make_sporting_state(minute=39, home_bc=1, away_bc=2)
        ms.position_type = "OVER"
        ms.position_team = "away"
        ms.target_over_line = 2.5
        ms.entry_minute = 36
        ms.opponent_bc_at_entry = 0
        # CRITICAL: minute_of_last_match_bc NÃO foi inicializado (=0)
        ms.minute_of_last_match_bc = 0

        d = compute_derived(ms)
        # Confirmar que utils retornou UNKNOWN_LAST_BC
        self.assertEqual(d.minutes_since_last_match_bc, UNKNOWN_LAST_BC,
                         "Pré-condição do bug: utils retorna 999 quando minute_of_last_match_bc=0")

        decision = Decision()
        manage_position(ms, d, decision, load_config())

        self.assertNotEqual(decision.recommended_action, "EXIT_OVER",
                            f"BUG: EXIT_OVER disparado com last_bc=UNKNOWN. "
                            f"Action veio: {decision.recommended_action} | "
                            f"Motivo: {decision.blocked_reason}")
        self.assertNotEqual(decision.recommended_action, "REDUCE_OVER")
        self.assertNotEqual(decision.recommended_action, "YELLOW_ALERT_OVER")
        # Comportamento esperado: HOLD_OVER_WITH_CAUTION (silencioso)
        self.assertEqual(decision.recommended_action, "HOLD_OVER_WITH_CAUTION")
        self.assertIn("desconhecida", decision.blocked_reason)

    def test_E2_known_last_bc_still_triggers_exit_when_20min_passed(self):
        """Sanity check: quando o estado ESTÁ correto, regra normal funciona."""
        ms = _make_sporting_state(minute=60, home_bc=1, away_bc=2)
        ms.position_type = "OVER"
        ms.position_team = "away"
        ms.target_over_line = 2.5
        ms.entry_minute = 36
        ms.opponent_bc_at_entry = 0
        # Estado CORRETO: última CC foi no min 36 (24 min atrás)
        ms.minute_of_last_match_bc = 36

        d = compute_derived(ms)
        self.assertEqual(d.minutes_since_last_match_bc, 24)

        decision = Decision()
        manage_position(ms, d, decision, load_config())
        # 24 min >= 20 → EXIT_OVER legítimo
        self.assertEqual(decision.recommended_action, "EXIT_OVER",
                         f"Action veio: {decision.recommended_action}")


class TestUpdateStateInitializesBcMinutes(unittest.TestCase):
    """Fix B: update_state inicializa minute_of_last_match_bc ao ENTER e em deltas."""

    def test_E3_enter_over_initializes_last_match_bc_when_total_bc_positive(self):
        ms = _make_sporting_state(minute=36, home_bc=1, away_bc=2)
        # Primeiro scan: sem prev (prev_home_bc=-1)
        ms.prev_home_bc = -1
        ms.prev_away_bc = -1

        state = {}
        decision = _fake_enter_decision(target_line=2.5)
        live_daemon.update_state(state, ms, decision)

        entry = state[ms.match_id]
        self.assertEqual(entry["position_type"], "OVER")
        # Bootstrap defensivo deve ter inicializado minute_of_last_match_bc = minuto atual
        self.assertEqual(entry["minute_of_last_match_bc"], 36,
                         "ENTER_OVER deve inicializar minute_of_last_match_bc = minuto atual "
                         "se total_bc > 0 (bootstrap defensivo)")
        # E total_bc_at_exit deve ser zerado (sem lock pendente)
        self.assertEqual(entry["total_bc_at_exit"], 0)

    def test_E4_inject_state_restores_minute_of_last_match_bc(self):
        # Round-trip: salvar e re-injetar
        ms1 = _make_sporting_state(minute=36, home_bc=1, away_bc=2)
        ms1.prev_home_bc = -1
        ms1.prev_away_bc = -1
        state = {}
        live_daemon.update_state(state, ms1, _fake_enter_decision())

        # Próximo ciclo: novo MatchState do mesmo jogo
        ms2 = _make_sporting_state(minute=42, home_bc=1, away_bc=2)
        live_daemon.inject_state(ms2, state)

        self.assertEqual(ms2.minute_of_last_match_bc, 36,
                         "inject_state deve restaurar minute_of_last_match_bc")
        self.assertEqual(ms2.position_type, "OVER")

        # Confirma que utils agora calcula corretamente (NÃO retorna 999)
        d = compute_derived(ms2)
        self.assertEqual(d.minutes_since_last_match_bc, 6,
                         "Após restauração, utils deve calcular 42-36=6 min, não 999")

    def test_E5_delta_detection_updates_minute_of_last_bc(self):
        # Cenário: scan 1 com home_bc=1, scan 2 com home_bc=2 (nova CC)
        state = {}

        # Scan 1
        ms1 = _make_sporting_state(minute=30, home_bc=1, away_bc=0)
        ms1.prev_home_bc = -1
        ms1.prev_away_bc = -1
        decision1 = Decision()
        decision1.recommended_action = "NO_ACTION"
        live_daemon.update_state(state, ms1, decision1)

        # Scan 2 — home_bc subiu de 1 → 2 (nova CC do home no min 40)
        ms2 = _make_sporting_state(minute=40, home_bc=2, away_bc=0)
        live_daemon.inject_state(ms2, state)  # prev_home_bc=1
        decision2 = Decision()
        decision2.recommended_action = "NO_ACTION"
        live_daemon.update_state(state, ms2, decision2)

        entry = state[ms2.match_id]
        self.assertEqual(entry["minute_of_last_home_bc"], 40,
                         "Delta home_bc 1→2 deve atualizar minute_of_last_home_bc=40")
        self.assertEqual(entry["minute_of_last_match_bc"], 40)


class TestAntiReentryOverBlocksWithoutNewBc(unittest.TestCase):
    """Fix D: após EXIT_OVER, bloquear nova entrada Over sem nova CC."""

    def test_E6a_reentry_within_cooldown_blocked_by_cooldown(self):
        """Camada 1: cooldown de 10 min bloqueia reentry imediata."""
        state = {}
        ms_enter = _make_sporting_state(minute=36, home_bc=1, away_bc=2)
        ms_enter.prev_home_bc = -1
        ms_enter.prev_away_bc = -1
        live_daemon.update_state(state, ms_enter, _fake_enter_decision())

        ms_exit = _make_sporting_state(minute=39, home_bc=1, away_bc=2)
        live_daemon.inject_state(ms_exit, state)
        live_daemon.update_state(state, ms_exit, _fake_exit_decision())
        self.assertEqual(state[ms_exit.match_id]["total_bc_at_exit"], 3,
                         "EXIT_OVER deve salvar total_bc_at_exit")
        self.assertEqual(state[ms_exit.match_id]["cooldown_until_minute"], 49,
                         "Cooldown deve ir até min 49 (39+10)")

        # Min 45 — dentro do cooldown (45 < 49) → camada cooldown bloqueia primeiro
        ms_reentry = _make_sporting_state(minute=45, home_bc=1, away_bc=2)
        live_daemon.inject_state(ms_reentry, state)
        decision_reentry, _d = run_scan(ms_reentry, load_config())

        self.assertEqual(decision_reentry.recommended_action, "COOLDOWN",
                         f"Min 45 < cooldown_until=49 → COOLDOWN. Veio: {decision_reentry.recommended_action}")

    def test_E6b_reentry_after_cooldown_still_blocked_by_anti_reentry(self):
        """Camada 2: depois do cooldown expirar, anti-reentry ainda bloqueia se SEM nova CC."""
        state = {}
        ms_enter = _make_sporting_state(minute=36, home_bc=1, away_bc=2)
        ms_enter.prev_home_bc = -1
        ms_enter.prev_away_bc = -1
        live_daemon.update_state(state, ms_enter, _fake_enter_decision())

        ms_exit = _make_sporting_state(minute=39, home_bc=1, away_bc=2)
        live_daemon.inject_state(ms_exit, state)
        live_daemon.update_state(state, ms_exit, _fake_exit_decision())

        # Min 55 — APÓS o cooldown (55 > 49), MAS sem nova CC (ainda 1x2)
        ms_reentry = _make_sporting_state(minute=55, home_bc=1, away_bc=2)
        live_daemon.inject_state(ms_reentry, state)
        self.assertEqual(ms_reentry.total_bc_at_exit, 3)

        decision_reentry, _d = run_scan(ms_reentry, load_config())

        self.assertEqual(decision_reentry.recommended_action, "BLOCKED",
                         f"Pós-cooldown sem nova CC: anti-reentry deve BLOQUEAR. "
                         f"Action: {decision_reentry.recommended_action}")
        self.assertEqual(decision_reentry.blocked_reason, "NO_NEW_BC_SINCE_OVER_EXIT")

    def test_E7_reentry_over_allowed_when_new_bc_appears(self):
        # Mesmo cenário, mas no cycle 3 surge uma nova CC (total vai pra 4)
        state = {}

        ms_enter = _make_sporting_state(minute=36, home_bc=1, away_bc=2)
        ms_enter.prev_home_bc = -1
        ms_enter.prev_away_bc = -1
        live_daemon.update_state(state, ms_enter, _fake_enter_decision())

        ms_exit = _make_sporting_state(minute=39, home_bc=1, away_bc=2)
        live_daemon.inject_state(ms_exit, state)
        live_daemon.update_state(state, ms_exit, _fake_exit_decision())

        # Nova CC: home_bc subiu 1→2 (total=4 > total_bc_at_exit=3)
        ms_reentry = _make_sporting_state(minute=48, home_bc=2, away_bc=2)
        live_daemon.inject_state(ms_reentry, state)

        decision_reentry, _d = run_scan(ms_reentry, load_config())
        # Não deve mais ser BLOCKED por NO_NEW_BC_SINCE_OVER_EXIT
        self.assertNotEqual(decision_reentry.blocked_reason, "NO_NEW_BC_SINCE_OVER_EXIT",
                            f"Com nova CC deve liberar reentry. Action: {decision_reentry.recommended_action} "
                            f"| blocked_reason: {decision_reentry.blocked_reason}")


class TestCooldownExtendedTo10Min(unittest.TestCase):
    """Fix D parte 2: cooldown_minutes_after_exit aumentado de 5 → 10."""

    def test_E8_cooldown_default_is_10_min(self):
        cfg = load_config()
        self.assertEqual(cfg["engine"]["cooldown_minutes_after_exit"], 10,
                         "config.yaml deve ter cooldown_minutes_after_exit=10")

    def test_E9_update_state_writes_cooldown_10min_after_exit(self):
        state = {}
        ms = _make_sporting_state(minute=39, home_bc=1, away_bc=2)
        ms.prev_home_bc = -1
        ms.prev_away_bc = -1
        # Simula que tinha posição
        state[ms.match_id] = {"position_type": "OVER", "position_team": "away"}
        live_daemon.update_state(state, ms, _fake_exit_decision())

        entry = state[ms.match_id]
        self.assertEqual(entry["state"], "COOLDOWN")
        self.assertEqual(entry["cooldown_until_minute"], 39 + 10,
                         f"Cooldown deve durar 10 min após EXIT. Foi: {entry['cooldown_until_minute']}")


# ─────────────────────────────────────────────────────────────────────────


def _run_all():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestSentinelDoesNotTriggerExit))
    suite.addTests(loader.loadTestsFromTestCase(TestUpdateStateInitializesBcMinutes))
    suite.addTests(loader.loadTestsFromTestCase(TestAntiReentryOverBlocksWithoutNewBc))
    suite.addTests(loader.loadTestsFromTestCase(TestCooldownExtendedTo10Min))
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run_all())
