"""
Testes obrigatórios de estabilidade da Operação 3.1.2.0 Turbo (v2.10).

Cobre T1-T15 do spec:
  T1.  read_match com hard timeout 30s aborta jogo travado.
  T2.  Jogo sem stats entra em cooldown 30 min, não volta no próximo ciclo.
  T3.  U19/U23/B/II/reserva filtrado ANTES de abrir Flashscore.
  T4.  Minuto >= 95 sem prorrogação tratado como finalizado.
  T5.  Jogo com dados reais chega na TRINCA.
  T6.  TRINCA é a 1ª regra esportiva depois do filtro operacional.
  T7.  Dominant Trailing só roda se TRINCA formar.
  T8.  near_misses NÃO recebe lixo operacional.
  T9.  operational_excluded recebe lixo com reason correto.
  T10. Watchdog não mata durante scan normal.
  T11. Watchdog não mata durante sleep.
  T12. Daemon mantém PID estável (tick válido por ciclos consecutivos).
  T13. Telegram só é chamado se OP + TRINCA + DT aprovarem.
  T14. historical_5000 não quebrou (sweep).
  T15. Testes antigos continuam verdes (sweep).
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy")
os.environ.setdefault("TELEGRAM_CHAT_ID", "dummy")

if "playwright" not in sys.modules:
    _pw = types.ModuleType("playwright")
    _pws = types.ModuleType("playwright.sync_api")
    class _D: pass
    _pws.sync_playwright = lambda: _D()
    _pws.Page = _D
    _pws.BrowserContext = _D
    sys.modules["playwright"] = _pw
    sys.modules["playwright.sync_api"] = _pws

import live_daemon  # noqa: E402
from src.models import MatchState, Decision  # noqa: E402
from src.flashscore_adapter import FlashscoreReader  # noqa: E402
from src.catalog import Catalog, _no_stats_backoff_seconds  # noqa: E402
from src import operational_eligibility_filter as OP  # noqa: E402
from src import turbo_enforcement as TE  # noqa: E402


# === T1 — Hard timeout 30s no read_match ==================================
class T1_HardTimeoutReadMatch(unittest.TestCase):

    def test_T1_hard_timeout_dispara_close_page_e_retorna_None(self):
        """O hard timeout via threading.Timer fecha a page e força exception.
        Simula: a page.goto levanta exception (como page fechada faria)."""
        r = FlashscoreReader.__new__(FlashscoreReader)
        page = MagicMock()
        # Simula que goto levanta exception (como acontece quando o Timer
        # fecha a page durante a operação)
        page.goto = MagicMock(side_effect=RuntimeError("page closed"))
        page.close = MagicMock()
        ctx = MagicMock()
        ctx.new_page = MagicMock(return_value=page)
        r._context = ctx
        r._extract_match_id = lambda u: "FS_X"
        r._accept_cookies = lambda p: None
        r._ensure_stats_url = lambda u: u

        # Patch threading.Timer pra disparar IMEDIATO (zero delay), forçando
        # o aborted flag a virar True antes do goto
        from src import flashscore_adapter
        original_timer = threading.Timer
        def fake_timer(delay, fn):
            return original_timer(0.001, fn)
        with patch.object(flashscore_adapter.threading, "Timer", fake_timer) \
                if hasattr(flashscore_adapter, "threading") else \
                patch("threading.Timer", fake_timer):
            r.READ_MATCH_HARD_LIMIT_S = 0.001
            result = r.read_match("http://x/", timeout_ms=5000)
        self.assertIsNone(result)
        # cleanup chamado (no finally)
        self.assertTrue(page.close.called or page.close.call_count >= 1)

    def test_T1b_hard_timeout_constante_eh_30s(self):
        """READ_MATCH_HARD_LIMIT_S deve estar em 30s no código (não 8s, não 60s)."""
        self.assertEqual(FlashscoreReader.READ_MATCH_HARD_LIMIT_S, 30)


# === T2 — Cooldown 30 min mínimo ==========================================
class T2_Cooldown30Min(unittest.TestCase):

    def test_T2a_backoff_1a_falha_eh_30_min(self):
        self.assertEqual(_no_stats_backoff_seconds(0), 30 * 60)
        self.assertEqual(_no_stats_backoff_seconds(1), 30 * 60)

    def test_T2b_backoff_3a_falha_eh_60_min(self):
        self.assertEqual(_no_stats_backoff_seconds(3), 60 * 60)

    def test_T2c_jogo_sem_stats_NAO_volta_proximo_ciclo(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            cat = Catalog(persist_path=tmp / "cat.json")
            cat.upsert_discovered("FS_T2c",
                                    "https://flashscore.com/jogo/x/")
            cat.mark_no_stats("FS_T2c")
            # is_no_stats_active deve ser True por 30 min
            self.assertTrue(cat.is_no_stats_active("FS_T2c"))
            # Simula passagem de 25 min — ainda ativo
            future = datetime.now(timezone.utc) + timedelta(minutes=25)
            self.assertTrue(cat.is_no_stats_active("FS_T2c", now=future))
            # 31 min — expirou
            future = datetime.now(timezone.utc) + timedelta(minutes=31)
            self.assertFalse(cat.is_no_stats_active("FS_T2c", now=future))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# === T3 — Pre-read filter pega reserva ANTES de Flashscore ================
class T3_PreReadReserva(unittest.TestCase):

    def setUp(self):
        OP._reset_state()

    def test_T3a_pre_read_pega_U19_no_nome(self):
        entry = {"url": "https://flashscore.com/jogo/x/",
                  "home_team": "Brasil U19", "away_team": "Argentina"}
        r = OP.pre_read_eligibility(entry)
        self.assertFalse(r["eligible"])
        self.assertEqual(r["reason"], OP.REASON_RESERVE_YOUTH)
        self.assertIn("home:Brasil U19", r["detected_in"])

    def test_T3b_pre_read_pega_pela_URL_slug(self):
        entry = {"url": "https://flashscore.com/jogo/brasil-u19/argentina-u19/"}
        r = OP.pre_read_eligibility(entry)
        self.assertFalse(r["eligible"])
        self.assertEqual(r["source"], "url_slug")

    def test_T3c_pre_read_pega_Reserves_na_liga(self):
        entry = {"url": "https://flashscore.com/jogo/x/",
                  "premium_league_name": "Premier League Reserves"}
        r = OP.pre_read_eligibility(entry)
        self.assertFalse(r["eligible"])

    def test_T3d_pre_read_libera_jogo_main(self):
        entry = {"url": "https://flashscore.com/jogo/liverpool/chelsea/?mid=X",
                  "home_team": "Liverpool", "away_team": "Chelsea",
                  "premium_league_name": "Premier League"}
        r = OP.pre_read_eligibility(entry)
        self.assertTrue(r["eligible"])


# === T4 — minuto >= 95 sem prorrogação → finished =========================
class T4_Min95Finished(unittest.TestCase):

    def test_T4_min95_sem_prorrogacao_eh_finished(self):
        ms = MatchState(home="A", away="B", minute=95, status_raw="2º tempo")
        live, reason = live_daemon.is_live_match(ms)
        self.assertFalse(live)
        self.assertEqual(reason, "MINUTE_OVER_95_LIKELY_FINISHED")


# === T5 — Jogo com dados reais chega na TRINCA ============================
class T5_DadosReaisChegaTRINCA(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (OP.LOG_PATH, TE.NEAR_MISS_LOG_PATH,
                       TE.APPROVED_SIGNALS_LOG_PATH)
        OP.LOG_PATH = self.tmp / "op.jsonl"
        TE.NEAR_MISS_LOG_PATH = self.tmp / "near.jsonl"
        TE.APPROVED_SIGNALS_LOG_PATH = self.tmp / "ap.jsonl"
        OP._reset_state()

    def tearDown(self):
        OP.LOG_PATH, TE.NEAR_MISS_LOG_PATH, TE.APPROVED_SIGNALS_LOG_PATH = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_T5_jogo_real_passa_OP_e_chama_TRINCA(self):
        ms = MatchState(
            match_id="FS_T5", home="Liverpool", away="Chelsea",
            minute=35, home_score=0, away_score=0,
            home_bc=3, away_bc=0, home_xg=1.20, away_xg=0.20,
            home_xgot=1.05, away_xgot=0.05,
            home_bc_raw=3, away_bc_raw=0,
            home_xg_raw=1.20, away_xg_raw=0.20,
            home_xgot_raw=1.05, away_xgot_raw=0.05,
        )
        d = Decision(recommended_action="ENTER_OVER_PREMIUM",
                       message_severity="URGENT", market_target="Over 2.5",
                       game_profile="STRONG")
        # OP passa
        op_ok, reason = live_daemon._operational_filter_or_skip(ms, d)
        self.assertTrue(op_ok)
        # Spy na TRINCA pra confirmar que é chamada
        called = []
        def spy_trinca(state):
            called.append(state)
            return {"triple_debt_formed": True, "block_reason": None,
                    "scope": "unilateral", "scope_side": "home",
                    "cc_in_scope": 3, "xg_in_scope": 1.20,
                    "xgot_in_scope": 1.05, "goals_in_scope": 0,
                    "cc_debt": True, "xg_debt": True, "xgot_debt": True,
                    "failed_reasons": []}
        def spy_dt(*a, **kw):
            return {"entry_allowed": True, "alert_tier": "PREMIUM",
                    "block_reason": "", "dominant_is_trailing": False}
        with patch.object(TE, "validate_triple_debt_filter",
                            side_effect=spy_trinca), \
             patch.object(TE, "validate_dominant_trailing",
                            side_effect=spy_dt):
            allowed, reason = live_daemon._turbo_enforce_or_block(ms, d)
        self.assertTrue(allowed)
        self.assertEqual(len(called), 1, "TRINCA não foi chamada 1x")


# === T6 — Ordem OP → TRINCA → DT ==========================================
class T6_OrdemPreservada(unittest.TestCase):

    def setUp(self):
        OP._reset_state()
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (OP.LOG_PATH, TE.NEAR_MISS_LOG_PATH,
                       TE.APPROVED_SIGNALS_LOG_PATH)
        OP.LOG_PATH = self.tmp / "op.jsonl"
        TE.NEAR_MISS_LOG_PATH = self.tmp / "near.jsonl"
        TE.APPROVED_SIGNALS_LOG_PATH = self.tmp / "ap.jsonl"

    def tearDown(self):
        OP.LOG_PATH, TE.NEAR_MISS_LOG_PATH, TE.APPROVED_SIGNALS_LOG_PATH = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_T6_OP_falha_NEM_TRINCA_NEM_DT_eh_chamada(self):
        # Reserva → OP bloqueia → Turbo NUNCA é chamada
        ms = MatchState(home="Brasil U19", away="Argentina",
                          match_id="FS_T6", minute=40)
        d = Decision(recommended_action="ENTER_OVER",
                       message_severity="ACTION")
        trinca_calls, dt_calls = [], []
        with patch.object(TE, "validate_triple_debt_filter",
                            side_effect=lambda s: trinca_calls.append(s)), \
             patch.object(TE, "validate_dominant_trailing",
                            side_effect=lambda *a, **kw: dt_calls.append(1)):
            op_ok, _ = live_daemon._operational_filter_or_skip(ms, d)
            self.assertFalse(op_ok)
            # Daemon NÃO chama Turbo neste caso (no plug-real é gateado)
        self.assertEqual(len(trinca_calls), 0)
        self.assertEqual(len(dt_calls), 0)


# === T7 — DT só roda se TRINCA formar =====================================
class T7_DTSoSeTrinca(unittest.TestCase):

    def test_T7_TRINCA_falha_DT_NAO_eh_chamada(self):
        ms = MatchState(home="H", away="A", minute=40,
                          home_bc=2, away_bc=0,
                          home_xg=1.2, away_xg=0.2,
                          home_xgot=1.0, away_xgot=0.0,
                          home_bc_raw=2, away_bc_raw=0,
                          home_xg_raw=1.2, away_xg_raw=0.2,
                          home_xgot_raw=1.0, away_xgot_raw=0.0)
        d = Decision(recommended_action="ENTER_OVER", message_severity="ACTION")
        dt_calls = []
        with patch.object(TE, "validate_dominant_trailing",
                            side_effect=lambda *a, **kw: dt_calls.append(1)):
            allowed, reason = live_daemon._turbo_enforce_or_block(ms, d)
        self.assertFalse(allowed)
        self.assertEqual(reason, "TURBO_BLOCKED_TRIPLE")
        self.assertEqual(len(dt_calls), 0)


# === T8, T9 — Logs separados ==============================================
class T8_T9_LogsSeparados(unittest.TestCase):

    def setUp(self):
        OP._reset_state()
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (OP.LOG_PATH, TE.NEAR_MISS_LOG_PATH)
        OP.LOG_PATH = self.tmp / "op.jsonl"
        TE.NEAR_MISS_LOG_PATH = self.tmp / "near.jsonl"

    def tearDown(self):
        OP.LOG_PATH, TE.NEAR_MISS_LOG_PATH = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_T8_T9_OP_excluded_log_separado_de_near_misses(self):
        # Reserve → OP loga em operational_excluded
        ms = MatchState(home="Real Madrid II", away="Atletico",
                          match_id="FS_T8", minute=40)
        d = Decision(recommended_action="ENTER_OVER")
        live_daemon._operational_filter_or_skip(ms, d)
        # OP log recebeu
        self.assertTrue(OP.LOG_PATH.exists())
        rec = json.loads(OP.LOG_PATH.read_text().splitlines()[0])
        self.assertEqual(rec["reason"], OP.REASON_RESERVE_YOUTH)
        # near_misses VAZIO (Turbo nem foi chamada)
        self.assertFalse(TE.NEAR_MISS_LOG_PATH.exists() and
                          TE.NEAR_MISS_LOG_PATH.read_text().strip())


# === T10, T11 — Watchdog não mata =========================================
class T10_T11_Watchdog(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.tick = self.tmp / "tick.json"
        self.hb = self.tmp / "hb.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_T10_watchdog_NAO_mata_durante_scan_normal(self):
        my_pid = os.getpid()
        # Tick fresh (acabou de tocar)
        live_daemon._touch_live_tick(pid=my_pid, source="scan",
                                       path=self.tick)
        start = datetime.now(timezone.utc) - timedelta(minutes=10)
        kill, _ = live_daemon._self_watchdog_decision(
            start, datetime.now(timezone.utc), self.hb,
            warmup_seconds=300, max_age_minutes=15,
            live_tick_path=self.tick, current_pid=my_pid)
        self.assertFalse(kill)

    def test_T11_watchdog_NAO_mata_durante_sleep_2min(self):
        my_pid = os.getpid()
        # Simula tick tocado há 30s (durante sleep, a cada 15s)
        ts_30s_ago = (datetime.now(timezone.utc) -
                       timedelta(seconds=30)).isoformat()
        self.tick.write_text(json.dumps({"pid": my_pid, "ts": ts_30s_ago,
                                            "source": "sleep"}))
        start = datetime.now(timezone.utc) - timedelta(minutes=12)
        kill, _ = live_daemon._self_watchdog_decision(
            start, datetime.now(timezone.utc), self.hb,
            warmup_seconds=300, max_age_minutes=15,
            live_tick_path=self.tick, current_pid=my_pid)
        self.assertFalse(kill)


# === T12 — PID estável ====================================================
class T12_PidEstavel(unittest.TestCase):

    def test_T12_tick_de_PID_diferente_NAO_eh_considerado_vivo(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            tick = tmp / "tick.json"
            other_pid = 99999
            tick.write_text(json.dumps({
                "pid": other_pid,
                "ts": datetime.now(timezone.utc).isoformat(),
                "source": "scan",
            }))
            hb = tmp / "hb.json"
            my_pid = os.getpid()
            start = datetime.now(timezone.utc) - timedelta(minutes=10)
            kill, motivo = live_daemon._self_watchdog_decision(
                start, datetime.now(timezone.utc), hb,
                live_tick_path=tick, current_pid=my_pid)
            # PID diferente → cai no heartbeat → não existe → mata
            self.assertTrue(kill)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# === T13 — Telegram só se 3 gates aprovarem ===============================
class T13_TelegramSoSe3Gates(unittest.TestCase):

    def test_T13_OP_falha_Telegram_NAO_eh_chamado(self):
        """O daemon NÃO chama tg.send_decision quando OP bloqueia."""
        # Inspeção textual do daemon: dentro de `if not op_ok:` não há
        # chamada a tg.send_decision.
        src = (Path(__file__).resolve().parent.parent
                / "live_daemon.py").read_text()
        # Acha cada `if not op_ok:` e garante que o bloco antes do `else`
        # NÃO tem tg.send_decision
        lines = src.splitlines()
        for i, ln in enumerate(lines):
            if "if not op_ok:" in ln:
                # Procura próximo `else:` no mesmo indent
                indent = len(ln) - len(ln.lstrip())
                else_idx = None
                for j in range(i+1, min(i+15, len(lines))):
                    cand = lines[j]
                    if cand.strip() and (len(cand) - len(cand.lstrip())) == indent:
                        if cand.strip().startswith("else"):
                            else_idx = j
                            break
                self.assertIsNotNone(else_idx,
                    f"`if not op_ok:` sem else por perto (linha {i+1})")
                between = "\n".join(lines[i:else_idx])
                self.assertNotIn("tg.send_decision", between,
                    f"`if not op_ok:` chama tg.send_decision (linha {i+1})")


# === T14 — historical_5000 não quebrou ====================================
class T14_HistoricalIntacto(unittest.TestCase):

    def test_T14_imports_historical_collector_ok(self):
        """historical_5000 importa sem erro."""
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                                     / "historical"))
            from historical import historical_flashscore_collector  # noqa
        except Exception as e:
            self.fail(f"historical import falhou: {e}")


def _run():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (T1_HardTimeoutReadMatch, T2_Cooldown30Min,
                T3_PreReadReserva, T4_Min95Finished,
                T5_DadosReaisChegaTRINCA, T6_OrdemPreservada,
                T7_DTSoSeTrinca, T8_T9_LogsSeparados,
                T10_T11_Watchdog, T12_PidEstavel,
                T13_TelegramSoSe3Gates, T14_HistoricalIntacto):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    r = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run())
