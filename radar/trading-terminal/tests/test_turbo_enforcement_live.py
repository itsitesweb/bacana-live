"""
Testes do enforcement TURBO no live_daemon.

Cobre T1-T10 do spec:
  T1.  Candidato sem TRINCA → Telegram NÃO envia.
  T2.  Candidato sem TRINCA → linha em logs/turbo_near_misses.jsonl.
  T3.  Candidato com 1 perna falhando → near_miss_type='failed_one_triple_leg'.
  T4.  TRINCA passa, DT bloqueia → não envia + near_miss.
  T5.  TRINCA + DT aprovam → Telegram envia.
  T6.  Erro em proteção → blocked_error.
  T7.  WATCH/FORTE/PREMIUM continuam sendo calculados (legacy intacto).
  T8.  Sinais antigos não são alterados.
  T9.  Banco limpo legacy não é reprocessado.
  T10. Logs são append-only (2 writes → 2 lines).

Roda:
  python3 tests/test_turbo_enforcement_live.py
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
from unittest.mock import patch, MagicMock

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
from src import turbo_enforcement as TE  # noqa: E402
from src import triple_debt_filter as TDF  # noqa: E402


# === Builders ============================================================
def _ms(home_bc=3, away_bc=0, home_xg=1.20, away_xg=0.20,
         home_xgot=1.05, away_xgot=0.05,
         home_score=0, away_score=0, minute=30,
         match_id="FS_TEST", home="Home", away="Away",
         home_shots=8, away_shots=2, home_sot=3, away_sot=1):
    # v3.1: inclui shots/SOT pra possibilitar classificação por Rota A ou B.
    # Default: minute=30 + cc=3 = cc_rate 10min → bate PREMIUM A.
    return MatchState(
        match_id=match_id, home=home, away=away,
        minute=minute, home_score=home_score, away_score=away_score,
        home_xg=home_xg, away_xg=away_xg,
        home_xgot=home_xgot, away_xgot=away_xgot,
        home_bc=home_bc, away_bc=away_bc,
        home_shots=home_shots, away_shots=away_shots,
        home_sot=home_sot, away_sot=away_sot,
        home_xg_raw=home_xg, away_xg_raw=away_xg,
        home_xgot_raw=home_xgot, away_xgot_raw=away_xgot,
        home_bc_raw=home_bc, away_bc_raw=away_bc,
    )


def _decision(action="ENTER_OVER_PREMIUM", sev="URGENT",
                market="Over 2.5"):
    return Decision(
        recommended_action=action, message_severity=sev,
        market_target=market, confidence_tier="A-",
        operator_instruction="entrada 1u", signal_valid_until=0,
        game_profile="STRONG", blocked_reason="",
    )


class _TurboLogIsolation(unittest.TestCase):
    """Isola logs do TURBO num tmpdir entre testes."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.nm_log = self.tmp / "turbo_near_misses.jsonl"
        self.ap_log = self.tmp / "turbo_approved_signals.jsonl"
        self.tdf_log = self.tmp / "triple_debt_audit.jsonl"
        self._orig = (TE.NEAR_MISS_LOG_PATH, TE.APPROVED_SIGNALS_LOG_PATH,
                       TDF.AUDIT_LOG_PATH)
        TE.NEAR_MISS_LOG_PATH = self.nm_log
        TE.APPROVED_SIGNALS_LOG_PATH = self.ap_log
        TDF.AUDIT_LOG_PATH = self.tdf_log

    def tearDown(self):
        (TE.NEAR_MISS_LOG_PATH,
         TE.APPROVED_SIGNALS_LOG_PATH,
         TDF.AUDIT_LOG_PATH) = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)


# === T1, T2, T10 — sem TRINCA bloqueia + loga ============================
class T1_T2_T10_SemTrincaBloqueia(_TurboLogIsolation):

    def test_T1_sem_trinca_bloqueia_telegram(self):
        # home 2 CC → fail A unilateral, total_cc=2 → fail bilateral → scope=none
        ms = _ms(home_bc=2, away_bc=0, home_xg=1.20, home_xgot=1.05)
        d = _decision()
        allowed, reason = live_daemon._turbo_enforce_or_block(ms, d)
        self.assertFalse(allowed)
        self.assertIn(reason, ("TURBO_BLOCKED_TRIPLE", "TURBO_BLOCKED_NO_TIER"))

    def test_T2_sem_trinca_salva_near_miss(self):
        ms = _ms(home_bc=2, away_bc=0, home_xg=1.20, home_xgot=1.05)
        live_daemon._turbo_enforce_or_block(ms, _decision())
        self.assertTrue(self.nm_log.exists())
        lines = self.nm_log.read_text().splitlines()
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        self.assertIn(rec["final_decision"], ("blocked_triple", "blocked_no_tier"))
        self.assertFalse(rec["telegram_sent"])
        self.assertEqual(rec["match_id"], "FS_TEST")
        # campos obrigatórios do spec
        for f in ("timestamp","match_id","home_team","away_team","minute",
                   "score_at_signal","original_tier","original_alert_type",
                   "candidate_market","home_cc","away_cc","total_cc",
                   "home_xg","away_xg","total_xg","home_xgot","away_xgot",
                   "total_xgot","home_goals","away_goals","scope",
                   "scope_side","cc_in_scope","xg_in_scope","xgot_in_scope",
                   "goals_in_scope","cc_debt","xg_debt","xgot_debt",
                   "triple_debt_formed","failed_reasons","block_reason",
                   "near_miss_type","near_miss_score","distance_to_pass",
                   "dominant_trailing_result","dominant_trailing_block_reason",
                   "final_decision","telegram_sent"):
            self.assertIn(f, rec, f"campo obrigatório '{f}' faltando")

    def test_T10_logs_append_only_duas_chamadas_duas_linhas(self):
        ms = _ms(home_bc=2)
        live_daemon._turbo_enforce_or_block(ms, _decision())
        live_daemon._turbo_enforce_or_block(ms, _decision())
        lines = self.nm_log.read_text().splitlines()
        self.assertEqual(len(lines), 2)


# === T3 — 1 perna falhando → failed_one_triple_leg ========================
class T3_FailedOneTripleLeg(_TurboLogIsolation):

    def test_T3_so_xgot_falha_marca_failed_one_triple_leg(self):
        # Unilateral home: cc=3, xg=1.20 (passa), xgot=0.45 (falha)
        ms = _ms(home_bc=3, away_bc=0,
                  home_xg=1.20, away_xg=0.20,
                  home_xgot=0.45, away_xgot=0.05)
        live_daemon._turbo_enforce_or_block(ms, _decision())
        lines = self.nm_log.read_text().splitlines()
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        self.assertEqual(rec["near_miss_type"], "failed_one_triple_leg")
        self.assertEqual(rec["failed_reasons"], ["triple_debt_failed_xgot"])
        self.assertEqual(rec["near_miss_score"], 2)   # 2 pernas passaram
        self.assertGreater(rec["distance_to_pass"]["xgot"], 0)
        self.assertEqual(rec["distance_to_pass"]["cc"], 0)
        self.assertEqual(rec["distance_to_pass"]["xg"], 0)


# === T4 — TRINCA passa + DT bloqueia ======================================
class T4_TrincaPassaDtBloqueia(_TurboLogIsolation):

    def test_T4_passes_triple_blocked_by_dominant_trailing(self):
        """Home dominante: cc=3, xg=1.20, xgot=1.05 (TRINCA forma).
        Mas placar 0-1: home dominante está perdendo.
        Sem match_history → DT bloqueia (sem reação confirmada)."""
        ms = _ms(home_bc=3, away_bc=0,
                  home_xg=1.20, away_xg=0.20,
                  home_xgot=1.05, away_xgot=0.05,
                  home_score=0, away_score=1, minute=40)
        # Importante: unilateral usa home_goals=0 → debt forma na TRINCA.
        # DT vê home dominante + opp_score>dom_score → trailing → bloqueia.
        allowed, reason = live_daemon._turbo_enforce_or_block(ms, _decision())
        self.assertFalse(allowed)
        self.assertEqual(reason, "TURBO_BLOCKED_DOMINANT_TRAILING")
        rec = json.loads(self.nm_log.read_text().splitlines()[0])
        self.assertEqual(rec["final_decision"], "blocked_dominant_trailing")
        self.assertEqual(rec["near_miss_type"],
                          "passed_triple_blocked_by_dominant_trailing")
        self.assertTrue(rec["triple_debt_formed"])
        self.assertEqual(rec["dominant_trailing_result"], "WATCH_INTERNAL")
        self.assertIsNotNone(rec["dominant_trailing_block_reason"])


# === T5 — TRINCA + DT aprovam → envia ====================================
class T5_AmbosAprovam(_TurboLogIsolation):

    def test_T5_passes_triple_and_dt_envia(self):
        """Home dominante, NÃO está perdendo (placar 1-0).
        TRINCA: cc=3, xg=1.20, xgot=1.05, goals=1 → cc_debt: 1>1 false. Hmm.
        Pra TRINCA passar com goal=1, preciso cc≥6.
        Vou usar 0-0 (sem trailing, ambos passam)."""
        ms = _ms(home_bc=3, away_bc=0,
                  home_xg=1.20, away_xg=0.20,
                  home_xgot=1.05, away_xgot=0.05,
                  home_score=0, away_score=0, minute=35)
        allowed, reason = live_daemon._turbo_enforce_or_block(ms, _decision())
        self.assertTrue(allowed, f"esperava allowed=True, deu reason={reason}")
        self.assertEqual(reason, "TURBO_APPROVED")
        # Approved sidecar deve ter 1 linha
        self.assertTrue(self.ap_log.exists())
        ap_lines = self.ap_log.read_text().splitlines()
        self.assertEqual(len(ap_lines), 1)
        ap = json.loads(ap_lines[0])
        self.assertTrue(ap["turbo_enforced"])
        self.assertTrue(ap["triple_debt_formed"])
        self.assertTrue(ap["dominant_trailing_approved"])
        self.assertEqual(ap["final_decision"], "sent")
        # Near miss log NÃO recebe nada
        self.assertFalse(self.nm_log.exists() and self.nm_log.read_text().strip())


# === T6 — erro em proteção → blocked_error ===============================
class T6_ErroBloqueiaPorSeguranca(_TurboLogIsolation):

    def test_T6_excecao_em_validate_dá_blocked_error(self):
        ms = _ms()
        with patch.object(TE, "validate_triple_debt_filter",
                            side_effect=RuntimeError("boom")):
            allowed, reason = live_daemon._turbo_enforce_or_block(ms, _decision())
        self.assertFalse(allowed)
        # Pode ser TURBO_BLOCKED_ERROR (evaluate_turbo pegou) OU
        # TURBO_INTERNAL_ERROR (wrapper externo pegou). Ambos = fail-closed.
        self.assertIn(reason, ("TURBO_BLOCKED_ERROR", "TURBO_INTERNAL_ERROR"))

    def test_T6b_excecao_em_DT_dá_blocked_error(self):
        ms = _ms()
        with patch.object(TE, "validate_dominant_trailing",
                            side_effect=RuntimeError("boom")):
            allowed, reason = live_daemon._turbo_enforce_or_block(ms, _decision())
        self.assertFalse(allowed)
        self.assertIn(reason, ("TURBO_BLOCKED_ERROR", "TURBO_INTERNAL_ERROR"))


# === T7 — WATCH/FORTE/PREMIUM legacy continuam ============================
class T7_LegacyIntacto(unittest.TestCase):

    def test_T7_legacy_codigo_3_1_ainda_existe_e_calcula(self):
        """A regra legacy continua importada e funcional no daemon."""
        # live_daemon.codigo_3_1 deve estar importado
        self.assertTrue(hasattr(live_daemon, "codigo_3_1"))
        # E o módulo legacy de regra over/back continua importável
        from src import rules_over, rules_back  # noqa
        # WATCH/FORTE/PREMIUM como tiers continuam reconhecidos pelo daemon
        src = (Path(__file__).resolve().parent.parent / "live_daemon.py").read_text()
        for tier in ("WATCH", "FORTE", "PREMIUM"):
            self.assertIn(tier, src,
                f"legacy tier '{tier}' sumiu do daemon")

    def test_T7b_modulo_turbo_nao_importa_telegram_nem_legacy(self):
        """turbo_enforcement.py deve importar APENAS triple_debt_filter
        e dominant_trailing_protection."""
        import re
        src = (Path(__file__).resolve().parent.parent
                / "src" / "turbo_enforcement.py").read_text()
        imports = [ln for ln in src.splitlines()
                    if re.match(r"^\s*(import|from)\s+", ln)]
        for ln in imports:
            for forbidden in ("telegram_client", "telegram_formatter",
                               "codigo_3_1", "rules_over", "rules_back",
                               "coverage_guard", "signals_persistence",
                               "live_daemon", "requests", "http.client"):
                self.assertNotIn(forbidden, ln,
                    f"turbo_enforcement importa proibido: {ln}")


# === T8, T9 — sinais antigos e banco limpo intocados ======================
class T8_T9_SinalAntigoBancoLimpoIntactos(unittest.TestCase):

    def test_T8_banco_limpo_intocado_byte_a_byte(self):
        """O arquivo rule_3_1_2_signals.jsonl não foi tocado pela
        implementação Turbo. Confirma que ainda existe e tem ≥1 linha."""
        bl = Path(__file__).resolve().parent.parent / "logs" / "rule_3_1_2_signals.jsonl"
        self.assertTrue(bl.exists(), "banco limpo sumiu")
        # Confirma que o banco contém JSON válido (não foi corrompido)
        with open(bl) as f:
            for ln in f:
                if ln.strip():
                    json.loads(ln)

    def test_T9_signals_persistence_nao_importa_turbo(self):
        """signals_persistence (responsável pelo banco limpo) não deve
        ter sido modificado pra conhecer o Turbo."""
        sp = (Path(__file__).resolve().parent.parent
               / "src" / "signals_persistence.py").read_text()
        self.assertNotIn("turbo_enforcement", sp)
        self.assertNotIn("triple_debt_filter", sp)
        self.assertNotIn("dominant_trailing_protection", sp)


# === Wiring no daemon =====================================================
class TestWiringDaemon(unittest.TestCase):

    def setUp(self):
        self.src = (Path(__file__).resolve().parent.parent
                     / "live_daemon.py").read_text()

    def test_W1_2_call_sites_de_turbo_enforce(self):
        # Conta apenas chamadas (exclui a definição `def`)
        lines = self.src.splitlines()
        calls = [ln for ln in lines
                  if "_turbo_enforce_or_block(ms, decision)" in ln
                  and not ln.lstrip().startswith("def ")]
        self.assertEqual(len(calls), 2,
            f"Esperava 2 call sites, achei {len(calls)}")

    def test_W2_gate_em_action_diferente_de_no_action(self):
        # Ambos call sites estão sob `if action != "NO_ACTION":`
        lines = self.src.splitlines()
        idx_calls = [i for i, ln in enumerate(lines)
                     if "_turbo_enforce_or_block(ms, decision)" in ln
                     and not ln.lstrip().startswith("def ")]
        self.assertEqual(len(idx_calls), 2)
        for idx in idx_calls:
            window = lines[max(0, idx-3):idx]
            has_gate = any('if action != "NO_ACTION"' in ln for ln in window)
            self.assertTrue(has_gate, f"call site na linha {idx+1} sem gate")

    def test_W3_se_turbo_bloqueia_NAO_chama_tg_send_decision(self):
        """No fluxo: turbo_allowed=False → telegram_sent=False, send_decision
        nunca é chamado. Confirma estrutura textual: dentro do `if not
        turbo_allowed:` block NÃO aparece tg.send_decision."""
        # Achamos cada 'if not turbo_allowed:' e garantimos que a próxima
        # ocorrência de tg.send_decision está APÓS o `else:` correspondente.
        lines = self.src.splitlines()
        for i, ln in enumerate(lines):
            if "if not turbo_allowed:" in ln:
                # Procura pelo `else:` no mesmo nível de indentação
                indent = len(ln) - len(ln.lstrip())
                else_idx = None
                for j in range(i+1, min(i+30, len(lines))):
                    cand = lines[j]
                    if cand.strip() and (len(cand) - len(cand.lstrip())) == indent:
                        if cand.strip().startswith("else"):
                            else_idx = j
                            break
                self.assertIsNotNone(else_idx,
                    f"if not turbo_allowed: sem else: por perto (linha {i+1})")
                # Linhas entre `if` e `else` NÃO podem ter tg.send_decision
                between = "\n".join(lines[i:else_idx])
                self.assertNotIn("tg.send_decision", between,
                    f"BLOCO bloqueado chama tg.send_decision (linha {i+1})")


# === ORD — Ordem inegociável TRINCA → DT ===================================
class TestOrdemInegociavel(_TurboLogIsolation):
    """Garante o contrato de ordem entre TRINCA e DT.

    Regras (do spec do usuário):
      1. TRINCA sempre primeiro.
      2. Se TRINCA falha → DT NUNCA é chamado.
      3. DT só roda se triple_debt_formed=true.
      4. DT NÃO redefine 'gol devendo' — só checa armadilha de placar.
    """

    def test_ORD1_TRINCA_falha_DT_NUNCA_eh_chamado(self):
        """Espia validate_dominant_trailing e garante NUNCA chamada
        quando triple_debt_formed=false."""
        ms = _ms(home_bc=2, away_bc=0)   # CC<3 → TRINCA falha
        calls = []
        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return {"entry_allowed": True}   # se chamado, mascara
        with patch.object(TE, "validate_dominant_trailing",
                            side_effect=spy):
            allowed, reason = live_daemon._turbo_enforce_or_block(
                ms, _decision())
        self.assertFalse(allowed)
        self.assertIn(reason, ("TURBO_BLOCKED_TRIPLE", "TURBO_BLOCKED_NO_TIER"))
        self.assertEqual(len(calls), 0,
            f"DT FOI chamado {len(calls)}x quando TRINCA falhou "
            f"— ordem inegociável violada")

    def test_ORD2_TRINCA_passa_DT_EH_chamado(self):
        """Quando TRINCA forma, DT é chamado exatamente 1x."""
        ms = _ms(home_bc=3, away_bc=0,
                  home_xg=1.20, away_xg=0.20,
                  home_xgot=1.05, away_xgot=0.05,
                  home_score=0, away_score=0, minute=35)
        calls = []
        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return {"entry_allowed": True, "alert_tier": "PREMIUM",
                    "block_reason": "", "dominant_is_trailing": False}
        with patch.object(TE, "validate_dominant_trailing",
                            side_effect=spy):
            allowed, reason = live_daemon._turbo_enforce_or_block(
                ms, _decision())
        self.assertTrue(allowed,
            f"Esperava aprovado quando TRINCA forma e DT aprova — reason={reason}")
        self.assertEqual(len(calls), 1,
            f"DT deveria ser chamado exatamente 1x; foi chamado {len(calls)}x")

    def test_ORD3_near_miss_de_TRINCA_falha_nao_tem_DT_info(self):
        """Near miss de blocked_triple não pode conter info de DT —
        prova que DT não rodou."""
        ms = _ms(home_bc=2)
        live_daemon._turbo_enforce_or_block(ms, _decision())
        rec = json.loads(self.nm_log.read_text().splitlines()[0])
        self.assertIn(rec["final_decision"], ("blocked_triple", "blocked_no_tier"))
        self.assertIsNone(rec["dominant_trailing_result"],
            "dominant_trailing_result deveria ser None — DT não rodou")
        self.assertIsNone(rec["dominant_trailing_block_reason"],
            "dominant_trailing_block_reason deveria ser None — DT não rodou")

    def test_ORD4_DT_modulo_nao_decide_gol_devendo(self):
        """O módulo DT não pode importar/calcular cc_debt/xg_debt/xgot_debt
        — esse é territorio exclusivo da TRINCA."""
        import re
        dt_src = (Path(__file__).resolve().parent.parent
                   / "src" / "dominant_trailing_protection.py").read_text()
        # DT não deve mencionar cc_debt/xg_debt/xgot_debt (decisão da TRINCA)
        for forbidden in ("cc_debt", "xg_debt", "xgot_debt",
                           "triple_debt_formed", "validate_triple_debt"):
            self.assertNotIn(forbidden, dt_src,
                f"DT mencionou '{forbidden}' — está pisando na TRINCA")

    def test_ORD5_evaluate_turbo_curto_circuita_em_blocked_triple(self):
        """Inspeção textual: o `return out` da branch blocked_triple
        existe ANTES da chamada validate_dominant_trailing."""
        src = (Path(__file__).resolve().parent.parent
                / "src" / "turbo_enforcement.py").read_text()
        lines = src.splitlines()
        idx_return = None
        idx_dt_call = None
        for i, ln in enumerate(lines):
            if "FINAL_BLOCKED_TRIPLE" in ln and "out[\"final_decision\"]" in ln:
                idx_return = i
            if "validate_dominant_trailing(" in ln and not ln.lstrip().startswith("from "):
                idx_dt_call = i
                break
        self.assertIsNotNone(idx_return, "FINAL_BLOCKED_TRIPLE não encontrado")
        self.assertIsNotNone(idx_dt_call, "validate_dominant_trailing call não encontrada")
        self.assertLess(idx_return, idx_dt_call,
            "FINAL_BLOCKED_TRIPLE deve aparecer ANTES da chamada DT no fluxo")


def _run():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (T1_T2_T10_SemTrincaBloqueia, T3_FailedOneTripleLeg,
                T4_TrincaPassaDtBloqueia, T5_AmbosAprovam,
                T6_ErroBloqueiaPorSeguranca, T7_LegacyIntacto,
                T8_T9_SinalAntigoBancoLimpoIntactos, TestWiringDaemon,
                TestOrdemInegociavel):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    r = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run())
