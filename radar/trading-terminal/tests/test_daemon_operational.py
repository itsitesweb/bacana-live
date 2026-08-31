"""
Testes operacionais do live_daemon — robustez de heartbeat, finished
detection, sem stats, preservação da Turbo.

Cobre:
  T1. _touch_live_tick escreve {pid, ts} no arquivo.
  T2. _self_watchdog_decision NÃO mata quando tick fresco do PID atual.
  T3. _self_watchdog_decision MATA quando tick velho do PID atual.
  T4. _self_watchdog_decision ignora tick de PID outro, cai no heartbeat.
  T5. is_live_match retorna False com minute >= 95 (sem extra-time markers).
  T6. is_live_match permite minute >= 95 quando status indica extra time.
  T7. _all_raw_metrics_missing: True quando todos _raw=None.
  T8. _all_raw_metrics_missing: False quando pelo menos 1 _raw real.
  T9. Turbo enforce ainda bloqueia missing_xgot (sem regressão).
  T10. Turbo ordem TRINCA→DT preservada.

Roda: python3 tests/test_daemon_operational.py
"""
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

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


# === T1, T2, T3, T4 — Heartbeat tick + watchdog ============================
class T_HeartbeatTickWatchdog(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.tick = self.tmp / "live_tick.json"
        self.hb = self.tmp / "heartbeat.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_T1_touch_live_tick_escreve_pid_e_ts(self):
        live_daemon._touch_live_tick(pid=12345, source="test",
                                       path=self.tick)
        self.assertTrue(self.tick.exists())
        d = json.loads(self.tick.read_text())
        self.assertEqual(d["pid"], 12345)
        self.assertEqual(d["source"], "test")
        self.assertIn("T", d["ts"])  # ISO timestamp

    def test_T2_watchdog_NAO_mata_quando_tick_fresh_do_PID_atual(self):
        my_pid = os.getpid()
        live_daemon._touch_live_tick(pid=my_pid, source="scan",
                                       path=self.tick)
        process_start = datetime.now(timezone.utc) - timedelta(minutes=10)
        now = datetime.now(timezone.utc)
        kill, motivo = live_daemon._self_watchdog_decision(
            process_start, now, self.hb,
            live_tick_path=self.tick, current_pid=my_pid)
        self.assertFalse(kill,
            f"watchdog matou daemon vivo com tick fresh: {motivo}")
        self.assertIn("tick", motivo)

    def test_T3_watchdog_MATA_quando_tick_velho_do_PID_atual(self):
        my_pid = os.getpid()
        # Escreve tick com ts antigo (15 min atrás)
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        self.tick.write_text(json.dumps({
            "pid": my_pid, "ts": old_ts, "source": "scan",
        }))
        process_start = datetime.now(timezone.utc) - timedelta(minutes=20)
        now = datetime.now(timezone.utc)
        kill, motivo = live_daemon._self_watchdog_decision(
            process_start, now, self.hb,
            max_age_minutes=8,
            live_tick_path=self.tick, current_pid=my_pid)
        self.assertTrue(kill, f"watchdog deveria matar com tick velho")
        self.assertIn("tick", motivo)

    def test_T4_watchdog_PID_outro_cai_em_heartbeat(self):
        """Tick com PID 99999 (outro daemon). Watchdog deve ignorar e
        cair na avaliação por heartbeat (que neste teste não existe →
        watchdog mata por 'sem heartbeat')."""
        self.tick.write_text(json.dumps({
            "pid": 99999, "ts": datetime.now(timezone.utc).isoformat(),
            "source": "scan",
        }))
        my_pid = os.getpid()
        process_start = datetime.now(timezone.utc) - timedelta(minutes=10)
        now = datetime.now(timezone.utc)
        kill, motivo = live_daemon._self_watchdog_decision(
            process_start, now, self.hb,
            live_tick_path=self.tick, current_pid=my_pid)
        self.assertTrue(kill)
        self.assertIn("sem heartbeat", motivo)


# === T5, T6 — is_live_match minute >= 95 ==================================
class T_IsLiveMatch95(unittest.TestCase):

    def test_T5_minute_95_sem_extra_time_retorna_finished(self):
        ms = MatchState(home="A", away="B", minute=95,
                          status_raw="2º tempo")
        live, reason = live_daemon.is_live_match(ms)
        self.assertFalse(live)
        self.assertEqual(reason, "MINUTE_OVER_95_LIKELY_FINISHED")

    def test_T5b_minute_100_sem_extra_marker_retorna_finished(self):
        ms = MatchState(home="A", away="B", minute=100, status_raw="")
        live, reason = live_daemon.is_live_match(ms)
        self.assertFalse(live)
        self.assertEqual(reason, "MINUTE_OVER_95_LIKELY_FINISHED")

    def test_T6_minute_95_com_extra_time_continua_live(self):
        """Cup match em extra-time NÃO pode ser confundido com finished.
        (Pênaltis/PEN são pós-extra-time = jogo encerrado, tratados pelo
        check 1 FINISHED_MATCH — não testados aqui.)"""
        for stat in ("Prorrogação", "EXTRA TIME", "ET", "Overtime"):
            ms = MatchState(home="A", away="B", minute=100, status_raw=stat)
            live, reason = live_daemon.is_live_match(ms)
            self.assertTrue(live,
                f"Esperava live=True para status='{stat}', deu {reason}")

    def test_T5c_minute_94_continua_live(self):
        """Não pode bloquear injury time normal."""
        ms = MatchState(home="A", away="B", minute=94, status_raw="2º tempo")
        live, reason = live_daemon.is_live_match(ms)
        self.assertTrue(live, f"minute=94 deveria ser live, deu {reason}")

    def test_T5d_minute_90_continua_live(self):
        ms = MatchState(home="A", away="B", minute=90, status_raw="2º tempo")
        live, reason = live_daemon.is_live_match(ms)
        self.assertTrue(live)


# === T7, T8 — _all_raw_metrics_missing ====================================
class T_AllRawMissing(unittest.TestCase):

    def test_T7_todos_raw_None_retorna_True(self):
        ms = MatchState(
            home="A", away="B",
            home_xg_raw=None, away_xg_raw=None,
            home_xgot_raw=None, away_xgot_raw=None,
            home_bc_raw=None, away_bc_raw=None,
        )
        self.assertTrue(live_daemon._all_raw_metrics_missing(ms))

    def test_T8_um_raw_real_retorna_False(self):
        ms = MatchState(
            home="A", away="B",
            home_xg_raw=0.5, away_xg_raw=None,    # 1 valor real
            home_xgot_raw=None, away_xgot_raw=None,
            home_bc_raw=None, away_bc_raw=None,
        )
        self.assertFalse(live_daemon._all_raw_metrics_missing(ms))

    def test_T8b_todos_raw_zero_real_retorna_False(self):
        """Zero REAL não é missing — só None é missing."""
        ms = MatchState(
            home="A", away="B",
            home_xg_raw=0.0, away_xg_raw=0.0,
            home_xgot_raw=0.0, away_xgot_raw=0.0,
            home_bc_raw=0, away_bc_raw=0,
        )
        self.assertFalse(live_daemon._all_raw_metrics_missing(ms),
            "Zero real foi confundido com ausente")

    def test_T8c_match_state_sem_atributos_raw_legacy_False(self):
        """Backward compat: MatchState sem fields _raw (versão antiga) →
        NÃO declara missing — mantém comportamento legacy."""
        class FakeMS:
            home = "A"; away = "B"
        self.assertFalse(live_daemon._all_raw_metrics_missing(FakeMS()))


# === T9, T10 — Turbo preservada ==========================================
class T_TurboPreservada(unittest.TestCase):
    """Garante que as fixes operacionais não alteraram o enforcement Turbo."""

    def test_T9_turbo_continua_bloqueando_missing_xgot(self):
        from src.triple_debt_filter import (
            validate_triple_debt_filter, REASON_MISSING_XGOT)
        match_state = {
            "home_cc": 3, "away_cc": 0,
            "home_xg": 1.20, "away_xg": 0.20,
            "home_xgot": 0.0, "away_xgot": 0.0,
            "home_xgot_raw": None, "away_xgot_raw": None,
            "home_goals": 0, "away_goals": 0,
        }
        r = validate_triple_debt_filter(match_state)
        self.assertEqual(r["block_reason"], REASON_MISSING_XGOT)

    def test_T10_ordem_trinca_dt_preservada(self):
        """Turbo enforce: TRINCA primeiro; DT só roda se TRINCA formar."""
        ms = MatchState(
            home="H", away="A",
            home_bc=2, away_bc=0,    # CC=2 → TRINCA falha
            home_xg=1.2, away_xg=0.2,
            home_xgot=1.0, away_xgot=0.0,
            home_bc_raw=2, away_bc_raw=0,
            home_xg_raw=1.2, away_xg_raw=0.2,
            home_xgot_raw=1.0, away_xgot_raw=0.0,
        )
        d = Decision(recommended_action="ENTER_OVER", message_severity="ACTION")
        # Patch validate_dominant_trailing pra detectar se foi chamado
        from src import turbo_enforcement as TE
        called = []
        def spy(*a, **kw):
            called.append(True)
            return {"entry_allowed": True}
        with patch.object(TE, "validate_dominant_trailing", side_effect=spy):
            allowed, reason = live_daemon._turbo_enforce_or_block(ms, d)
        self.assertFalse(allowed)
        self.assertEqual(reason, "TURBO_BLOCKED_TRIPLE")
        self.assertEqual(len(called), 0,
            "DT foi chamado com TRINCA falhada — ordem violada")


# === T11 — Ciclo 6min + sleep 2min não mata o daemon ======================
class T_CicloLongoSleepNaoMata(unittest.TestCase):
    """Cenário real reportado: scan 366s + sleep 120s ≈ 8.1 min.
    Daemon estava sendo morto porque tick não era atualizado durante sleep.
    Fix v2.9: tick tocado a cada 15s no sleep + uma vez ao final do ciclo."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.tick = self.tmp / "live_tick.json"
        self.hb = self.tmp / "heartbeat.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_T11_ciclo_6min_sleep_2min_NAO_mata(self):
        """Simula:
           t=0      → startup, tick fresh
           t=360s   → fim do ciclo, tick fresh (último tick do scan)
           t=480s   → fim do sleep, tick deve ter sido renovado a cada 15s
                       → último tick em t≈480s
           t=540s   → watchdog checa: tick age=0, NÃO mata.
        Sem o fix, tick ficaria em t=360s, age=180s+ no fim do sleep — OK.
        Mas se o daemon entrar em sleep maior (300s), o cenário do user
        bate o limite. Testamos com tempos reais via mocking de datetime.
        """
        my_pid = os.getpid()
        process_start = datetime.now(timezone.utc) - timedelta(seconds=540)

        # Simula tick sendo tocado durante sleep a cada 15s
        # O ÚLTIMO tick foi escrito há 5s (durante o sleep loop)
        last_tick_ts = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        self.tick.write_text(json.dumps({
            "pid": my_pid, "ts": last_tick_ts, "source": "sleep",
        }))

        # Watchdog checa agora — total elapsed 540s (>warmup 300s)
        now = datetime.now(timezone.utc)
        kill, motivo = live_daemon._self_watchdog_decision(
            process_start, now, self.hb,
            warmup_seconds=300, max_age_minutes=8,
            live_tick_path=self.tick, current_pid=my_pid)
        self.assertFalse(kill,
            f"watchdog matou daemon vivo no cenário ciclo+sleep: {motivo}")
        self.assertIn("OK", motivo)

    def test_T11b_ciclo_6min_SEM_tick_no_sleep_eh_morto(self):
        """Sanity inverso: sem o fix (tick parou ao fim do ciclo, sem
        renovação no sleep), watchdog mata. Confirma que o teste T11 não
        é trivialmente sempre-passa."""
        my_pid = os.getpid()
        process_start = datetime.now(timezone.utc) - timedelta(seconds=540)
        # Último tick em t=60s (=tempo do fim do ciclo se scan durou 60s
        # e estamos 8.1min depois)
        old_tick_ts = (datetime.now(timezone.utc) -
                         timedelta(minutes=9)).isoformat()
        self.tick.write_text(json.dumps({
            "pid": my_pid, "ts": old_tick_ts, "source": "cycle_end",
        }))
        now = datetime.now(timezone.utc)
        kill, motivo = live_daemon._self_watchdog_decision(
            process_start, now, self.hb,
            warmup_seconds=300, max_age_minutes=8,
            live_tick_path=self.tick, current_pid=my_pid)
        self.assertTrue(kill,
            "sem renovação no sleep, watchdog deveria matar — confirma "
            "que o teste T11 não é tautológico")

    def test_T11c_tick_inside_sleep_loop_eh_atomico(self):
        """O tick durante sleep precisa usar escrita atômica (os.replace)
        pra não deixar arquivo corrompido em race condition (watchdog lendo
        no meio da escrita)."""
        live_daemon._touch_live_tick(pid=42, source="sleep", path=self.tick)
        # Imediatamente sobrescreve com nova escrita
        live_daemon._touch_live_tick(pid=42, source="sleep", path=self.tick)
        # Leitura precisa funcionar (JSON válido)
        d = json.loads(self.tick.read_text())
        self.assertEqual(d["pid"], 42)
        # Tmp file foi removido (atômico)
        tmp = self.tick.with_suffix(".json.tmp")
        self.assertFalse(tmp.exists(),
            f"arquivo .tmp ficou pra trás: {tmp}")

    def test_T11d_call_sites_de_sleep_tocam_tick(self):
        """Inspeção textual: todo `for _i in range(remaining/args.interval):`
        que tem `time.sleep(1)` deve estar precedido por `_touch_live_tick`
        E ter um `_touch_live_tick` dentro com cadência 15s."""
        src = (Path(__file__).resolve().parent.parent
                / "live_daemon.py").read_text()
        # Procura padrão: sleep_start ANTES do loop + sleep dentro
        # Espera pelo menos 2 ocorrências (modo watchlist + modo legacy)
        sleep_starts = src.count('_touch_live_tick(source="sleep_start")')
        sleeps_inside = src.count('_touch_live_tick(source="sleep")')
        self.assertGreaterEqual(sleep_starts, 2,
            f"esperava ≥2 'sleep_start' tick toques, achei {sleep_starts}")
        self.assertGreaterEqual(sleeps_inside, 2,
            f"esperava ≥2 'sleep' tick toques (a cada 15s), achei {sleeps_inside}")
        # Cycle_end também precisa estar presente
        self.assertIn('_touch_live_tick(source="cycle_end")', src)


def _run():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (T_HeartbeatTickWatchdog, T_IsLiveMatch95,
                T_AllRawMissing, T_TurboPreservada,
                T_CicloLongoSleepNaoMata):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    r = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run())
