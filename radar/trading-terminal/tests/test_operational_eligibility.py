"""
Testes do OPERATIONAL_ELIGIBILITY_FILTER + plug no live_daemon.

Cobertura (espec do usuário):
  T1. Minuto 90 com stats N/A → NÃO chama Turbo.
  T2. Jogo U19/U23/time 2/B → NÃO chama Turbo.
  T3. Todos _raw=None → no_stats cooldown (sem chamar Turbo).
  T4. 2 ciclos consecutivos missing_xgot → cooldown 30 min.
  T5. Jogo elegível (CC/xG/xGOT reais) → chama Turbo normalmente.
  T6. TRINCA continua sendo a 1ª regra esportiva DEPOIS da elegibilidade.
  T7. turbo_near_misses NÃO recebe jogos excluídos pelo OP filter.

Plus defensivos:
  TX1. Filtro detecta "Barcelona B", "Time 2", "Real Madrid II".
  TX2. Whitelist override funciona.
  TX3. Streak reseta após Turbo aprovar.
  TX4. Cooldown expira após N minutos.
  TX5. Log appenda em operational_excluded.jsonl.
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
from src import operational_eligibility_filter as OP  # noqa: E402
from src import turbo_enforcement as TE  # noqa: E402


def _ms(home="Liverpool", away="Brighton", minute=42,
         home_bc=3, away_bc=1, home_xg=1.20, away_xg=0.40,
         home_xgot=1.05, away_xgot=0.30,
         home_score=0, away_score=0, match_id="FS_TEST",
         status_raw="2º tempo", league="",
         home_bc_raw=None, away_bc_raw=None,
         home_xg_raw=None, away_xg_raw=None,
         home_xgot_raw=None, away_xgot_raw=None):
    # Default: _raw espelha os valores legacy (= dado presente no feed)
    if home_bc_raw is None: home_bc_raw = home_bc
    if away_bc_raw is None: away_bc_raw = away_bc
    if home_xg_raw is None: home_xg_raw = home_xg
    if away_xg_raw is None: away_xg_raw = away_xg
    if home_xgot_raw is None: home_xgot_raw = home_xgot
    if away_xgot_raw is None: away_xgot_raw = away_xgot
    ms = MatchState(
        match_id=match_id, home=home, away=away,
        minute=minute, home_score=home_score, away_score=away_score,
        home_bc=home_bc, away_bc=away_bc,
        home_xg=home_xg, away_xg=away_xg,
        home_xgot=home_xgot, away_xgot=away_xgot,
        status_raw=status_raw,
        home_bc_raw=home_bc_raw, away_bc_raw=away_bc_raw,
        home_xg_raw=home_xg_raw, away_xg_raw=away_xg_raw,
        home_xgot_raw=home_xgot_raw, away_xgot_raw=away_xgot_raw,
    )
    # league_name não é field do dataclass — set dinâmico
    if league:
        setattr(ms, "league_name", league)
    return ms


def _ms_no_stats(**kw):
    ms = _ms(**kw)
    ms.home_bc_raw = None; ms.away_bc_raw = None
    ms.home_xg_raw = None; ms.away_xg_raw = None
    ms.home_xgot_raw = None; ms.away_xgot_raw = None
    ms.home_bc = 0; ms.away_bc = 0
    ms.home_xg = 0.0; ms.away_xg = 0.0
    ms.home_xgot = 0.0; ms.away_xgot = 0.0
    return ms


def _decision(action="ENTER_OVER_PREMIUM", profile="STRONG"):
    return Decision(recommended_action=action, message_severity="URGENT",
                     market_target="Over 2.5", confidence_tier="A-",
                     game_profile=profile)


# === Isolação =============================================================
class _Isolated(unittest.TestCase):
    """Isola logs + reseta streak/cooldown entre testes."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (OP.LOG_PATH, TE.NEAR_MISS_LOG_PATH,
                       TE.APPROVED_SIGNALS_LOG_PATH)
        OP.LOG_PATH = self.tmp / "op_excluded.jsonl"
        TE.NEAR_MISS_LOG_PATH = self.tmp / "near.jsonl"
        TE.APPROVED_SIGNALS_LOG_PATH = self.tmp / "approved.jsonl"
        OP._reset_state()

    def tearDown(self):
        OP.LOG_PATH, TE.NEAR_MISS_LOG_PATH, TE.APPROVED_SIGNALS_LOG_PATH = self._orig
        OP._reset_state()
        shutil.rmtree(self.tmp, ignore_errors=True)


# === T1 — minuto 90 + stats N/A bloqueia ===================================
class T1_Min90StatsNA(_Isolated):

    def test_T1_min90_todos_raw_None_bloqueia_finished_min_90(self):
        ms = _ms_no_stats(minute=92, match_id="FS_T1")
        allowed, reason = live_daemon._operational_filter_or_skip(ms, _decision())
        self.assertFalse(allowed)
        self.assertIn("FINISHED_MINUTE_90", reason)
        # near_misses NÃO recebe nada
        self.assertFalse(TE.NEAR_MISS_LOG_PATH.exists() and
                          TE.NEAR_MISS_LOG_PATH.read_text().strip())
        # operational_excluded recebe
        self.assertTrue(OP.LOG_PATH.exists())
        rec = json.loads(OP.LOG_PATH.read_text().splitlines()[0])
        self.assertEqual(rec["reason"], OP.REASON_FINISHED_MIN_90)


# === T2 — reserva/youth bloqueia ==========================================
class T2_ReservaYouth(_Isolated):

    def test_T2a_U19_no_nome_do_time_bloqueia(self):
        ms = _ms(home="Brasil U19", match_id="FS_T2a")
        allowed, reason = live_daemon._operational_filter_or_skip(ms, _decision())
        self.assertFalse(allowed)
        self.assertIn("RESERVE_OR_YOUTH", reason)

    def test_T2b_Time2_sufixo_bloqueia(self):
        ms = _ms(home="Barcelona B", match_id="FS_T2b")
        allowed, reason = live_daemon._operational_filter_or_skip(ms, _decision())
        self.assertFalse(allowed)

    def test_T2c_Real_Madrid_II_bloqueia(self):
        ms = _ms(away="Real Madrid II", match_id="FS_T2c")
        allowed, reason = live_daemon._operational_filter_or_skip(ms, _decision())
        self.assertFalse(allowed)

    def test_T2d_liga_youth_bloqueia(self):
        ms = _ms(league="UEFA Youth League", match_id="FS_T2d")
        allowed, reason = live_daemon._operational_filter_or_skip(ms, _decision())
        self.assertFalse(allowed)


# === T3 — _raw all None → no_stats cooldown ===============================
class T3_AllRawNoneNoStats(_Isolated):

    def test_T3_all_raw_None_marca_missing_all_core_stats(self):
        ms = _ms_no_stats(minute=30, match_id="FS_T3")
        allowed, reason = live_daemon._operational_filter_or_skip(ms, _decision())
        self.assertFalse(allowed)
        self.assertIn("MISSING_ALL_CORE_STATS", reason)
        rec = json.loads(OP.LOG_PATH.read_text().splitlines()[0])
        self.assertEqual(rec["reason"], OP.REASON_MISSING_CORE_STATS)
        self.assertEqual(rec["action"], "mark_no_stats")


# === T4 — 2 ciclos missing_xgot → cooldown 30 min =========================
class T4_RepeatedMissingXgot(_Isolated):

    def test_T4_2_ciclos_consecutivos_ativam_cooldown_30min(self):
        mid = "FS_T4"
        # Ciclo 1: Turbo bloqueia com missing_xgot → streak=1
        OP.record_turbo_result(mid, "TURBO_BLOCKED_MISSING_XGOT")
        # Ciclo 2: streak=2 → OP bloqueia ANTES da Turbo
        OP.record_turbo_result(mid, "TURBO_BLOCKED_MISSING_XGOT")
        self.assertEqual(OP.get_missing_xgot_streak(mid), 2)
        # Próxima avaliação:
        ms = _ms(match_id=mid)
        allowed, reason = live_daemon._operational_filter_or_skip(ms, _decision())
        self.assertFalse(allowed)
        self.assertIn("REPEATED_MISSING_XGOT", reason)
        # Cooldown ativo
        self.assertTrue(OP.is_in_cooldown(mid))

    def test_T4b_um_ciclo_so_NAO_ativa_cooldown(self):
        mid = "FS_T4b"
        OP.record_turbo_result(mid, "TURBO_BLOCKED_MISSING_XGOT")
        self.assertEqual(OP.get_missing_xgot_streak(mid), 1)
        ms = _ms(match_id=mid)
        allowed, _ = live_daemon._operational_filter_or_skip(ms, _decision())
        # Streak=1 não bate ≥2 → ainda passa pra Turbo (mas como o ms é
        # válido, OP aprova; a Turbo é quem decidirá)
        self.assertTrue(allowed)


# === T5 — Jogo elegível chama Turbo ========================================
class T5_ElegivelChamaTurbo(_Isolated):

    def test_T5_jogo_elegivel_passa_pra_Turbo(self):
        ms = _ms(match_id="FS_T5", minute=35, home_bc=3, away_bc=0,
                  home_xg=1.20, away_xg=0.20,
                  home_xgot=1.05, away_xgot=0.05,
                  home_score=0, away_score=0)
        allowed, reason = live_daemon._operational_filter_or_skip(ms, _decision())
        self.assertTrue(allowed)
        self.assertEqual(reason, "OP_ELIGIBLE")
        # Nada loga em operational_excluded
        self.assertFalse(OP.LOG_PATH.exists() and
                          OP.LOG_PATH.read_text().strip())


# === T6 — Ordem TRINCA continua primeira regra esportiva ==================
class T6_OrdemTrincaPreservada(_Isolated):
    """Após o OP aprovar, a 1ª regra esportiva chamada é a TRINCA."""

    def test_T6_OP_passa_TRINCA_eh_chamada_antes_de_DT(self):
        ms = _ms(match_id="FS_T6")
        # Patch TRINCA pra detectar chamada + bloquear (pra DT NÃO ser chamado)
        from src import triple_debt_filter as TDF
        from src import turbo_enforcement
        trinca_called = []
        dt_called = []
        def fake_trinca(state):
            trinca_called.append(True)
            return {"triple_debt_formed": False, "block_reason": "test",
                    "scope": "none", "failed_reasons": [],
                    "cc_in_scope": 0, "xg_in_scope": 0,
                    "xgot_in_scope": 0, "goals_in_scope": 0}
        def fake_dt(*a, **kw):
            dt_called.append(True)
            return {"entry_allowed": True}
        with patch.object(turbo_enforcement, "validate_triple_debt_filter",
                            side_effect=fake_trinca), \
             patch.object(turbo_enforcement, "validate_dominant_trailing",
                            side_effect=fake_dt):
            op_ok, _ = live_daemon._operational_filter_or_skip(ms, _decision())
            self.assertTrue(op_ok)
            allowed, reason = live_daemon._turbo_enforce_or_block(ms, _decision())
        self.assertFalse(allowed)
        self.assertEqual(len(trinca_called), 1,
            f"TRINCA esperava ser chamada 1x; foi {len(trinca_called)}")
        self.assertEqual(len(dt_called), 0,
            "DT foi chamada antes da TRINCA — ordem violada")


# === T7 — near_misses NÃO recebe jogos excluídos pelo OP ===================
class T7_NearMissesLimpo(_Isolated):

    def test_T7_jogo_OP_excluded_NAO_vai_pra_near_misses(self):
        # Reserve → OP bloqueia
        ms = _ms(home="Sub-19 Brasil", match_id="FS_T7")
        live_daemon._operational_filter_or_skip(ms, _decision())
        # near_misses fica vazio
        self.assertFalse(TE.NEAR_MISS_LOG_PATH.exists() and
                          TE.NEAR_MISS_LOG_PATH.read_text().strip(),
                          "near_misses recebeu jogo bloqueado pelo OP")
        # operational_excluded recebeu
        self.assertTrue(OP.LOG_PATH.exists())


# === Defensivos ===========================================================
class TX_Defensivos(_Isolated):

    def test_TX1_filtro_reserve_pega_variantes(self):
        for n in ("Barcelona B", "Time 2", "Real Madrid II",
                  "Brasil U17", "Argentina U23",
                  "Liverpool Reserves", "Borussia Youth",
                  "Borussia Mönchengladbach Junioren"):
            ms = _ms(home=n, match_id=f"FS_R_{n[:5]}")
            ok, _ = live_daemon._operational_filter_or_skip(ms, _decision())
            self.assertFalse(ok, f"Esperava bloquear '{n}'")

    def test_TX2_jogos_main_NAO_disparam_reserve(self):
        """False positive guard — nomes normais não podem cair em reserve."""
        for n in ("Barcelona", "Liverpool", "Real Madrid",
                  "Manchester United", "Internazionale",
                  "Atlético Madrid", "Bayern München"):
            ms = _ms(home=n, away="Chelsea", match_id=f"FS_M_{n[:5]}",
                      minute=40)
            ok, reason = live_daemon._operational_filter_or_skip(
                ms, _decision())
            self.assertTrue(ok, f"'{n}' classificado como reserve: {reason}")

    def test_TX3_streak_reseta_apos_Turbo_aprovar(self):
        mid = "FS_TX3"
        OP.record_turbo_result(mid, "TURBO_BLOCKED_MISSING_XGOT")
        self.assertEqual(OP.get_missing_xgot_streak(mid), 1)
        OP.record_turbo_result(mid, "TURBO_APPROVED")
        self.assertEqual(OP.get_missing_xgot_streak(mid), 0)

    def test_TX4_cooldown_expira_apos_30min(self):
        mid = "FS_TX4"
        OP.add_cooldown(mid, minutes=30)
        self.assertTrue(OP.is_in_cooldown(mid))
        # Força expiração mexendo no dict interno
        OP._op_cooldown[mid] = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.assertFalse(OP.is_in_cooldown(mid))

    def test_TX5_log_appenda_uma_linha_por_chamada(self):
        ms = _ms(home="Brasil U19", match_id="FS_TX5")
        live_daemon._operational_filter_or_skip(ms, _decision())
        live_daemon._operational_filter_or_skip(ms, _decision())
        # 1ª chamada loga; 2ª já está em cooldown → não loga de novo
        lines = OP.LOG_PATH.read_text().splitlines()
        self.assertEqual(len(lines), 1,
            "OP deveria logar apenas 1x; segunda chamada estava em cooldown")

    def test_TX6_stale_pre_fake(self):
        # minute=0 + status pre, mas com _raw populado (zero real)
        ms = _ms(minute=0, status_raw="Agendado", match_id="FS_TX6",
                  home_bc=0, away_bc=0,
                  home_xg=0.0, away_xg=0.0,
                  home_xgot=0.0, away_xgot=0.0,
                  home_bc_raw=0, away_bc_raw=0,
                  home_xg_raw=0.0, away_xg_raw=0.0,
                  home_xgot_raw=0.0, away_xgot_raw=0.0)
        ok, reason = live_daemon._operational_filter_or_skip(ms, _decision())
        self.assertFalse(ok)
        self.assertIn("STALE_PRE_FAKE", reason)


def _run():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (T1_Min90StatsNA, T2_ReservaYouth, T3_AllRawNoneNoStats,
                T4_RepeatedMissingXgot, T5_ElegivelChamaTurbo,
                T6_OrdemTrincaPreservada, T7_NearMissesLimpo,
                TX_Defensivos):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    r = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run())
