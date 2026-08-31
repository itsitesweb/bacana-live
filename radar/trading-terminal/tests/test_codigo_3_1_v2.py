"""
Testes obrigatórios da REGRA 3.1.2.0 — Código 3:1 com Níveis Operacionais.

Cobertura dos 21 casos exigidos pela especificação:

  OVER:
    1.  total_cc=3, rate=15, gols=0 → WATCH OVER
    2.  total_cc=3, rate=16, gols=0 → sem alerta
    3.  total_cc=4, rate=12, gols=0 → FORTE OVER
    4.  total_cc=6, rate=12, gols=1 → PREMIUM OVER
    5.  total_cc=6, rate=12, gols=2 → sem alerta (placar acompanhou)
    6.  total_cc=6, rate=12, xG≥2.5, gols=1 → PREMIUM OVER CC+xG

  BILATERAL:
    7.  home_cc=3, away_cc=3, gols abaixo → PREMIUM OVER BILATERAL
    8.  home_cc=3, away_cc=3, placar acompanhou → sem Telegram forte

  BACK:
    9.  dom_cc=3, opp_cc=0, diff=3, dom_goals=0 → WATCH BACK
    10. dom_cc=4, opp_cc=0, diff=4, dom_goals=0 → FORTE BACK
    11. dom_cc=6, opp_cc=0, dom_goals=1 → PREMIUM BACK
    12. dom_cc=6, opp_cc=0, dom_goals=2 → sem alerta (acompanhou)
    13. dom_cc=6, opp_cc=0, dominante já vencendo por 2+ → bloquear
    14. diff_cc<4 → não pode ser FORTE BACK

  ANTI-SPAM:
    15. mesmo bucket não repete alerta
    16. novo bucket pode alertar

  PRIORIDADE:
    17. bilateral premium ganha de forte over
    18. premium over ganha de watch back
"""
import os
import sys
import types
import unittest
from pathlib import Path

# Stub Playwright
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

from src.models import MatchState
from src import codigo_3_1 as c31


def make_ms(*, minute, home_score, away_score, home_bc, away_bc,
            home_xg=0.0, away_xg=0.0, home="HomeFC", away="AwayFC"):
    return MatchState(
        match_id="FS_TEST",
        home=home, away=away,
        minute=minute, status_raw="2nd Half",
        home_bc=home_bc, away_bc=away_bc,
        home_score=home_score, away_score=away_score,
        home_xg=home_xg, away_xg=away_xg,
    )


# ════════════════════════════════════════════════════════════════════
# OVER (testes 1-6)
# ════════════════════════════════════════════════════════════════════
class TestOver(unittest.TestCase):

    def test_01_cc3_rate15_zero_goals_watch_over(self):
        """Total_cc=3, rate=90/3=30 → rate>15, SEM alerta.
        Mas rate=15 exato (cc=6 em min=90 ou cc=3 em min=45).
        Vamos usar cc=3, min=45 → rate=15. zero goals → WATCH OVER."""
        ms = make_ms(minute=45, home_score=0, away_score=0, home_bc=2, away_bc=1)
        out = c31.evaluate_codigo_3_1(ms, {})
        self.assertTrue(out["should_alert"],
                        f"Esperava WATCH OVER. Veio: {out}")
        self.assertEqual(out["alert_type"], c31.ALERT_OVER_WATCH)
        self.assertEqual(out["level"], "watch")
        self.assertEqual(out["market"], "over")

    def test_02_cc3_rate_gt_15_no_alert(self):
        """Total_cc=3, rate>15 → sem alerta.
        cc=3, min=48 → rate=16 > 15."""
        ms = make_ms(minute=48, home_score=0, away_score=0, home_bc=2, away_bc=1)
        out = c31.evaluate_codigo_3_1(ms, {})
        self.assertFalse(out["should_alert"])
        self.assertIn("rate", out["reason"])

    def test_03_cc4_rate12_zero_goals_forte_over(self):
        """cc=4, rate=90/4 → vamos forçar rate<=12: cc=4, min=48 → rate=12.
        gols=0 < esperado=1 → FORTE OVER."""
        ms = make_ms(minute=48, home_score=0, away_score=0, home_bc=2, away_bc=2)
        out = c31.evaluate_codigo_3_1(ms, {})
        self.assertTrue(out["should_alert"], f"Veio: {out}")
        # Bilateral 2x2 não atinge bilateral premium (precisa 3x3+). Espera FORTE.
        self.assertEqual(out["alert_type"], c31.ALERT_OVER_FORTE)
        self.assertEqual(out["level"], "forte")

    def test_04_cc6_rate12_1goal_premium_over(self):
        """cc=6, min=72 → rate=12. gols=1 < esperado=2 → PREMIUM OVER (3x3 → BILATERAL)."""
        # cc=6 (3x3) é BILATERAL → vira PREMIUM BILATERAL, prioridade 1
        ms = make_ms(minute=72, home_score=1, away_score=0, home_bc=3, away_bc=3)
        out = c31.evaluate_codigo_3_1(ms, {})
        self.assertTrue(out["should_alert"])
        # Bilateral pesado ganha prioridade
        self.assertEqual(out["alert_type"], c31.ALERT_OVER_BILATERAL_PREMIUM)
        self.assertEqual(out["level"], "premium")

    def test_04b_cc6_rate12_1goal_premium_over_NOT_bilateral(self):
        """cc=6 sem bilateral (5x1) e rate≤12 → PREMIUM OVER puro."""
        ms = make_ms(minute=72, home_score=1, away_score=0, home_bc=5, away_bc=1)
        out = c31.evaluate_codigo_3_1(ms, {})
        self.assertTrue(out["should_alert"])
        self.assertEqual(out["alert_type"], c31.ALERT_OVER_PREMIUM)

    def test_05_cc6_rate12_2goals_no_alert(self):
        """cc=6, gols=2, esperado=2 → placar acompanhou, sem alerta."""
        ms = make_ms(minute=72, home_score=1, away_score=1, home_bc=3, away_bc=3)
        out = c31.evaluate_codigo_3_1(ms, {})
        self.assertFalse(out["should_alert"])
        self.assertIn("goals", out["reason"])

    def test_06_cc6_rate12_xg25_1goal_premium_xg(self):
        """cc=6 (5x1, não bilateral), rate≤12, xG≥2.5, gols=1 → PREMIUM CC+xG."""
        ms = make_ms(minute=72, home_score=1, away_score=0, home_bc=5, away_bc=1,
                     home_xg=2.0, away_xg=0.6)  # total xG = 2.6
        out = c31.evaluate_codigo_3_1(ms, {})
        self.assertTrue(out["should_alert"])
        self.assertEqual(out["alert_type"], c31.ALERT_OVER_PREMIUM_XG,
                         f"Esperava PREMIUM_XG. Veio: {out['alert_type']}")


# ════════════════════════════════════════════════════════════════════
# BILATERAL (testes 7-8)
# ════════════════════════════════════════════════════════════════════
class TestBilateral(unittest.TestCase):

    def test_07_3x3_below_expected_premium_bilateral(self):
        """home_cc=3, away_cc=3, total=6, gols<2 → PREMIUM BILATERAL."""
        ms = make_ms(minute=80, home_score=0, away_score=1, home_bc=3, away_bc=3)
        out = c31.evaluate_codigo_3_1(ms, {})
        self.assertTrue(out["should_alert"])
        self.assertEqual(out["alert_type"], c31.ALERT_OVER_BILATERAL_PREMIUM)

    def test_08_3x3_placar_acompanhou_sem_alerta(self):
        """home_cc=3, away_cc=3, gols=2 (= esperado) → sem alerta."""
        ms = make_ms(minute=80, home_score=1, away_score=1, home_bc=3, away_bc=3)
        out = c31.evaluate_codigo_3_1(ms, {})
        self.assertFalse(out["should_alert"])


# ════════════════════════════════════════════════════════════════════
# BACK (testes 9-14)
# ════════════════════════════════════════════════════════════════════
class TestBack(unittest.TestCase):

    def test_09_dom3_opp0_diff3_dom0_watch_back(self):
        """dom=3, opp=0, diff=3, dom_goals=0 → WATCH BACK.
        Atenção: também pode disparar OVER WATCH (cc≥3, rate≤15, gols<expected).
        Pelo ranking de prioridade, OVER WATCH (prio 7) > BACK WATCH (prio 8)."""
        ms = make_ms(minute=44, home_score=0, away_score=0, home_bc=3, away_bc=0)
        out = c31.evaluate_codigo_3_1(ms, {})
        self.assertTrue(out["should_alert"])
        # Como tem TANTO OVER WATCH (cc=3 + rate=15 + gol=0) QUANTO BACK WATCH,
        # OVER vem antes pela prioridade. Se quisermos BACK puro, precisa
        # condição que só BACK aceite.
        # Vamos forçar BACK puro: minute alto (rate>15) elimina OVER WATCH
        ms2 = make_ms(minute=80, home_score=0, away_score=0, home_bc=3, away_bc=0)
        out2 = c31.evaluate_codigo_3_1(ms2, {})
        self.assertTrue(out2["should_alert"])
        # rate=80/3=26.7 > 15, então OVER WATCH não bate.
        # BACK WATCH bate: dom=3, opp=0, diff=3, dom_goals=0.
        self.assertEqual(out2["alert_type"], c31.ALERT_BACK_WATCH)
        self.assertEqual(out2["market"], "back")

    def test_10_dom4_opp0_diff4_dom0_forte_back(self):
        """dom=4, opp=0, diff=4, dom_goals=0 → FORTE BACK.
        Pra evitar OVER FORTE ganhar (cc=4+rate≤12), forçar rate>12: min>=49.
        Ex: cc=4, min=60 → rate=15. rate>12 elimina OVER FORTE."""
        ms = make_ms(minute=60, home_score=0, away_score=0, home_bc=4, away_bc=0)
        out = c31.evaluate_codigo_3_1(ms, {})
        self.assertTrue(out["should_alert"])
        # rate=15 → OVER WATCH bate. Vamos elevar min pra rate>15
        ms2 = make_ms(minute=70, home_score=0, away_score=0, home_bc=4, away_bc=0)
        out2 = c31.evaluate_codigo_3_1(ms2, {})
        # rate=17.5 > 15 → OVER eliminado. BACK FORTE deve bater (dom=4, opp=0, diff=4)
        self.assertTrue(out2["should_alert"])
        self.assertEqual(out2["alert_type"], c31.ALERT_BACK_FORTE)

    def test_11_dom6_opp0_dom1_premium_back(self):
        """dom=6, opp=0, dom_goals=1, esperado=2 → PREMIUM BACK.
        Pra evitar OVER ganhar: min alto pra rate>12."""
        ms = make_ms(minute=85, home_score=1, away_score=0, home_bc=6, away_bc=0)
        out = c31.evaluate_codigo_3_1(ms, {})
        # cc total=6, rate=85/6=14.2 > 12 → OVER PREMIUM/FORTE não batem.
        # OVER WATCH: cc=6, rate≤15 → bate (mas WATCH = prio 7).
        # BACK PREMIUM: dom=6, opp=0, diff=6, gols=1<2 → prio 4, ganha.
        self.assertTrue(out["should_alert"])
        self.assertEqual(out["alert_type"], c31.ALERT_BACK_PREMIUM)

    def test_12_dom6_opp0_dom2_no_alert(self):
        """dom=6, opp=0, dom_goals=2 = esperado → placar acompanhou."""
        ms = make_ms(minute=80, home_score=2, away_score=0, home_bc=6, away_bc=0)
        out = c31.evaluate_codigo_3_1(ms, {})
        self.assertFalse(out["should_alert"])

    def test_13_dominante_vencendo_2plus_bloqueia_back(self):
        """dom=6, opp=0, dom 2-0, esperado=2. Mesmo cenário Q12 mas com
        FILTRO explícito: se dominante vencendo por 2+, bloquear BACK.
        Caso ainda haja OVER possível, OVER pode disparar; mas BACK não pode."""
        # cc=6, dom_goals=3 (>= 2 de lead), expected=2 → placar já acompanhou
        # então mesmo OVER não dispara
        ms = make_ms(minute=85, home_score=3, away_score=0, home_bc=6, away_bc=0)
        out = c31.evaluate_codigo_3_1(ms, {})
        self.assertFalse(out["should_alert"])
        # Cenário onde BACK seria bloqueado mas há outros sinais:
        # cc=9 (6x3), esperado=3, dom 3-0 → placar acompanhou, sem alerta
        ms2 = make_ms(minute=85, home_score=3, away_score=0, home_bc=6, away_bc=3)
        out2 = c31.evaluate_codigo_3_1(ms2, {})
        self.assertFalse(out2["should_alert"])

    def test_14_diff_cc_lt_4_no_forte_back(self):
        """diff_cc<4 → não pode ser FORTE BACK.
        Cenário: dom=4, opp=1 → diff=3 → FORTE BACK bloqueado.
        Mas WATCH BACK pode disparar se dom_cc>=3 e opp<=1 e diff>=3.
        """
        # cc total=5, min=80 → rate=16 → OVER bloqueado
        ms = make_ms(minute=80, home_score=0, away_score=0, home_bc=4, away_bc=1)
        out = c31.evaluate_codigo_3_1(ms, {})
        # WATCH BACK: dom=4, opp=1, diff=3 (>=3), dom_goals=0 < 1 → bate
        # FORTE BACK: dom=4, opp=1<=1, diff=3 (NÃO >=4) → NÃO bate
        self.assertTrue(out["should_alert"])
        self.assertEqual(out["alert_type"], c31.ALERT_BACK_WATCH,
                         f"Diff=3 não pode virar FORTE. Veio: {out['alert_type']}")
        self.assertNotEqual(out["alert_type"], c31.ALERT_BACK_FORTE)


# ════════════════════════════════════════════════════════════════════
# ANTI-SPAM (testes 15-16)
# ════════════════════════════════════════════════════════════════════
class TestAntiSpam(unittest.TestCase):

    def test_15_mesmo_bucket_nao_repete(self):
        """Bucket já alertado não dispara de novo."""
        ms = make_ms(minute=80, home_score=0, away_score=1, home_bc=3, away_bc=3)
        prev = {"main_bucket": 2, "unilateral_bucket": 0}  # bucket=2 já alertado
        out = c31.evaluate_codigo_3_1(ms, prev)
        # cc=6, expected=2, bucket=2. last_main=2 → bucket<=last → NÃO alerta
        self.assertFalse(out["should_alert"])

    def test_16_novo_bucket_pode_alertar(self):
        """Bucket NOVO (maior que último) dispara."""
        ms = make_ms(minute=80, home_score=0, away_score=1, home_bc=4, away_bc=5)
        prev = {"main_bucket": 2, "unilateral_bucket": 0}  # cc=9, bucket=3 > 2 → ok
        out = c31.evaluate_codigo_3_1(ms, prev)
        self.assertTrue(out["should_alert"])
        self.assertEqual(out["bucket"], 3)


# ════════════════════════════════════════════════════════════════════
# PRIORIDADE (testes 17-18)
# ════════════════════════════════════════════════════════════════════
class TestPriority(unittest.TestCase):

    def test_17_bilateral_premium_ganha_de_forte_over(self):
        """Cenário que batem AMBOS: bilateral premium (prio 1) > forte over (prio 5)."""
        # cc=6 (3x3) — bilateral; rate=12 (min=72); gols=1 → bate AMBOS
        ms = make_ms(minute=72, home_score=1, away_score=0, home_bc=3, away_bc=3)
        out = c31.evaluate_codigo_3_1(ms, {})
        self.assertTrue(out["should_alert"])
        self.assertEqual(out["alert_type"], c31.ALERT_OVER_BILATERAL_PREMIUM)

    def test_18_premium_over_ganha_de_watch_back(self):
        """Premium over (prio 3) > watch back (prio 8)."""
        # cc=6 (5x1, NÃO bilateral), rate=12, gols=1 → PREMIUM OVER
        # Também tem dom=5, opp=1, diff=4, dom_goals=1<1 (5//3=1) — NÃO é watch back
        # Vamos forçar: cc=6 (5x1), gols=1, dom=5, expected=1, dom_goals=1 → NÃO dispara back
        # Reformula: dom_cc=5, opp=1, dom_goals=0 (esperado=1) → dispara back
        ms = make_ms(minute=72, home_score=0, away_score=1, home_bc=5, away_bc=1)
        out = c31.evaluate_codigo_3_1(ms, {})
        # OVER PREMIUM: cc=6, rate=12, gols=1<2 ✅
        # BACK WATCH: dom=5(home), opp=1, diff=4, dom_goals=0 < 1 ✅
        # PRIORIDADE → PREMIUM OVER (prio 3) ganha de WATCH BACK (prio 8)
        self.assertTrue(out["should_alert"])
        self.assertEqual(out["alert_type"], c31.ALERT_OVER_PREMIUM)


# ════════════════════════════════════════════════════════════════════
# REGRESSÃO (testes 19-21) — confirmam que NÃO mexemos no resto
# ════════════════════════════════════════════════════════════════════
class TestRegression(unittest.TestCase):

    def test_19_supervisor_module_exists(self):
        """codigo31_supervisor.py continua existindo e importável."""
        import codigo31_supervisor as sup
        self.assertTrue(hasattr(sup, "Codigo31Supervisor"))
        self.assertTrue(hasattr(sup, "evaluate_supervisor_state"))

    def test_20_telegram_does_not_send_v12_terms(self):
        """format_telegram_message NUNCA emite ENTER_OVER, EXIT_OVER, etc."""
        for alert_type in [c31.ALERT_OVER_BILATERAL_PREMIUM, c31.ALERT_OVER_PREMIUM_XG,
                            c31.ALERT_OVER_PREMIUM, c31.ALERT_BACK_PREMIUM,
                            c31.ALERT_OVER_FORTE, c31.ALERT_BACK_FORTE,
                            c31.ALERT_OVER_WATCH, c31.ALERT_BACK_WATCH]:
            decision = {
                "should_alert": True, "alert_type": alert_type,
                "market": "back" if "back" in alert_type else "over",
                "telegram_message_fields": {
                    "home": "A", "away": "B", "home_bc": 3, "away_bc": 3,
                    "home_score": 0, "away_score": 0, "minute": 60,
                    "total_cc": 6, "total_goals": 0, "cc_rate": 10.0,
                    "expected_goals_by_cc": 2,
                    "dominant_name": "A", "dom_cc": 5, "opp_cc": 1, "cc_diff": 4,
                    "dominant_score": 0, "expected_dominant_goals_by_cc": 1,
                    "total_xg": 2.6,
                },
            }
            msg = c31.format_telegram_message(decision)
            for forbidden in ["ENTER_OVER", "EXIT_OVER", "ENTER_BACK", "EXIT_BACK",
                              "MANUAL_REVIEW", "REDUCE", "LOCK_PROFIT", "HOLD"]:
                self.assertNotIn(forbidden, msg,
                                  f"Termo V1.2 '{forbidden}' vazou em {alert_type}")

    def test_21_radar13_not_touched(self):
        """Arquivos do Radar13 não foram modificados (estrutural)."""
        radar_py = Path(__file__).resolve().parent.parent / "radar13" / "radar13.py"
        watchdog = Path(__file__).resolve().parent.parent / "radar13" / "radar13_watchdog.py"
        self.assertTrue(radar_py.exists())
        self.assertTrue(watchdog.exists())
        # Sanity: codigo_3_1.py não importa nada de radar13
        # (menções em docstring são OK; o que NÃO pode é import/from radar13)
        cod = (Path(__file__).resolve().parent.parent / "src" / "codigo_3_1.py").read_text().lower()
        self.assertNotIn("import radar13", cod,
                          "src/codigo_3_1.py importou radar13 — proibido")
        self.assertNotIn("from radar13", cod,
                          "src/codigo_3_1.py importou de radar13 — proibido")


class TestWatchLogOnly(unittest.TestCase):
    """Política Regra 3.1.2.0 v2.8 (atualizada pelo Tiago):
       WATCH OVER/BACK ENVIA Telegram, MAS com dedup por
       (match_id, alert_type, bucket) — só na primeira ocorrência.
       O dedup é feito pelo CALLER (live_daemon) via signals_persistence;
       send_alert() em si envia para todos os tipos quando chamada.
       FORTE/PREMIUM/BILATERAL = aposta. Envia + consome bucket.
       WATCH NÃO consome bucket — não bloqueia FORTE/PREMIUM no mesmo bucket."""

    def _mk_tg(self):
        from unittest.mock import MagicMock
        tg = MagicMock()
        tg.is_ready = MagicMock(return_value=True)
        tg._send_raw = MagicMock(return_value=True)
        return tg

    def test_TG01_over_watch_sends_telegram_with_radar_title(self):
        """v2.8: WATCH OVER volta a enviar Telegram (radar)."""
        d = c31.evaluate_codigo_3_1(
            make_ms(minute=45, home_bc=1, away_bc=2, home_score=0, away_score=0), {})
        self.assertEqual(d["alert_type"], c31.ALERT_OVER_WATCH)
        tg = self._mk_tg()
        sent = c31.send_alert(tg, d)
        self.assertTrue(sent, "v2.8: WATCH OVER DEVE enviar Telegram")
        tg._send_raw.assert_called_once()
        msg = tg._send_raw.call_args[0][0]
        self.assertIn("📡 WATCH 3.1.2 — RADAR DE GOL", msg)
        self.assertIn("Radar ativo", msg)
        self.assertIn("Não é entrada automática", msg)

    def test_TG02_back_watch_sends_telegram_with_radar_title(self):
        """v2.8: WATCH BACK volta a enviar Telegram (radar)."""
        d = c31.evaluate_codigo_3_1(
            make_ms(minute=65, home_bc=3, away_bc=0, home_score=0, away_score=0), {})
        self.assertEqual(d["alert_type"], c31.ALERT_BACK_WATCH)
        tg = self._mk_tg()
        sent = c31.send_alert(tg, d)
        self.assertTrue(sent, "v2.8: WATCH BACK DEVE enviar Telegram")
        tg._send_raw.assert_called_once()
        msg = tg._send_raw.call_args[0][0]
        self.assertIn("📡 WATCH 3.1.2 — RADAR DE BACK DOMINANTE", msg)
        self.assertIn("Radar ativo", msg)

    def test_TG01b_watch_message_format_completo(self):
        """A mensagem WATCH continua disponível pra terminal/log via
        format_telegram_message — útil pra dedup mostrar texto suprimido."""
        d = c31.evaluate_codigo_3_1(
            make_ms(minute=45, home_bc=1, away_bc=2, home_score=0, away_score=0), {})
        msg = c31.format_telegram_message(d)
        self.assertIn("📡 WATCH 3.1.2 — RADAR DE GOL", msg)
        self.assertIn("Radar ativo", msg)

    def test_TG03_over_watch_does_not_consume_bucket(self):
        """update_state_after_alert NÃO grava bucket pra over_watch."""
        d = c31.evaluate_codigo_3_1(
            make_ms(minute=45, home_bc=1, away_bc=2, home_score=0, away_score=0), {})
        self.assertEqual(d["alert_type"], c31.ALERT_OVER_WATCH)
        entry = {}
        c31.update_state_after_alert(entry, d)
        # state não deve registrar bucket
        cc = entry.get("codigo_3_1") or {}
        self.assertEqual(cc.get("main_bucket_last", 0), 0,
                          "WATCH OVER não pode consumir bucket")

    def test_TG04_back_watch_does_not_consume_bucket(self):
        """update_state_after_alert NÃO grava bucket pra back_watch."""
        d = c31.evaluate_codigo_3_1(
            make_ms(minute=65, home_bc=3, away_bc=0, home_score=0, away_score=0), {})
        self.assertEqual(d["alert_type"], c31.ALERT_BACK_WATCH)
        entry = {}
        c31.update_state_after_alert(entry, d)
        cc = entry.get("codigo_3_1") or {}
        self.assertEqual(cc.get("unilateral_bucket_last", 0), 0,
                          "WATCH BACK não pode consumir bucket")

    def test_TG05_over_forte_sends_telegram(self):
        """FORTE OVER envia TG com texto oficial 'FORTE 3.1.2 — GOL DEVENDO'."""
        d = c31.evaluate_codigo_3_1(
            make_ms(minute=48, home_bc=3, away_bc=1, home_score=0, away_score=0), {})
        self.assertEqual(d["alert_type"], c31.ALERT_OVER_FORTE)
        tg = self._mk_tg()
        sent = c31.send_alert(tg, d)
        self.assertTrue(sent, "FORTE OVER deve enviar Telegram")
        tg._send_raw.assert_called_once()
        msg = tg._send_raw.call_args[0][0]
        self.assertIn("🟠 FORTE 3.1.2 — GOL DEVENDO", msg)
        self.assertIn("Sinal operacional", msg)

    def test_TG06_back_forte_sends_telegram(self):
        """FORTE BACK envia TG com texto oficial 'FORTE 3.1.2 — BACK DOMINANTE'."""
        d = c31.evaluate_codigo_3_1(
            make_ms(minute=88, home_bc=5, away_bc=1, home_score=0, away_score=0), {})
        self.assertEqual(d["alert_type"], c31.ALERT_BACK_FORTE,
                          f"Cenário esperado: BACK FORTE; veio: {d['alert_type']}")
        tg = self._mk_tg()
        sent = c31.send_alert(tg, d)
        self.assertTrue(sent, "FORTE BACK deve enviar Telegram")
        tg._send_raw.assert_called_once()
        msg = tg._send_raw.call_args[0][0]
        self.assertIn("🟠 FORTE 3.1.2 — BACK DOMINANTE", msg)
        self.assertIn("Sinal operacional para Back do dominante", msg)

    def test_TG07_premium_over_sends_telegram(self):
        """PREMIUM OVER envia TG com texto oficial 'PREMIUM 3.1.2 — GOL MUITO DEVENDO'."""
        d = c31.evaluate_codigo_3_1(
            make_ms(minute=72, home_bc=5, away_bc=1, home_score=1, away_score=0), {})
        self.assertEqual(d["alert_type"], c31.ALERT_OVER_PREMIUM)
        tg = self._mk_tg()
        sent = c31.send_alert(tg, d)
        self.assertTrue(sent, "PREMIUM OVER deve enviar Telegram")
        tg._send_raw.assert_called_once()
        msg = tg._send_raw.call_args[0][0]
        self.assertIn("🟢 PREMIUM 3.1.2 — GOL MUITO DEVENDO", msg)
        self.assertIn("Prioridade alta", msg)

    def test_TG08_premium_back_sends_telegram(self):
        """PREMIUM BACK envia TG com texto 'PREMIUM 3.1.2 — BACK DOMINANTE EXTREMO'."""
        d = c31.evaluate_codigo_3_1(
            make_ms(minute=90, home_bc=6, away_bc=0, home_score=1, away_score=0), {})
        self.assertEqual(d["alert_type"], c31.ALERT_BACK_PREMIUM)
        tg = self._mk_tg()
        sent = c31.send_alert(tg, d)
        self.assertTrue(sent, "PREMIUM BACK deve enviar Telegram")
        tg._send_raw.assert_called_once()
        msg = tg._send_raw.call_args[0][0]
        self.assertIn("🟢 PREMIUM 3.1.2 — BACK DOMINANTE EXTREMO", msg)
        self.assertIn("reação do dominante", msg)

    def test_TG08b_premium_xg_sends_telegram(self):
        """PREMIUM CC+xG envia TG com 'CC + xG CONFIRMADOS' e linha 'xG total'."""
        d = c31.evaluate_codigo_3_1(
            make_ms(minute=72, home_bc=5, away_bc=1, home_score=1, away_score=0,
                    home_xg=2.0, away_xg=0.6), {})
        self.assertEqual(d["alert_type"], c31.ALERT_OVER_PREMIUM_XG)
        tg = self._mk_tg()
        sent = c31.send_alert(tg, d)
        self.assertTrue(sent, "PREMIUM xG deve enviar Telegram")
        msg = tg._send_raw.call_args[0][0]
        self.assertIn("🟢 PREMIUM 3.1.2 — CC + xG CONFIRMADOS", msg)
        self.assertIn("xG total:", msg)
        self.assertIn("Prioridade máxima", msg)

    def test_TG08c_bilateral_sends_telegram(self):
        """BILATERAL envia TG com 'OVER BILATERAL PESADO' e leitura de jogo aberto."""
        d = c31.evaluate_codigo_3_1(
            make_ms(minute=58, home_bc=3, away_bc=3, home_score=0, away_score=0), {})
        self.assertEqual(d["alert_type"], c31.ALERT_OVER_BILATERAL_PREMIUM)
        tg = self._mk_tg()
        sent = c31.send_alert(tg, d)
        self.assertTrue(sent, "BILATERAL deve enviar Telegram")
        msg = tg._send_raw.call_args[0][0]
        self.assertIn("🟢 PREMIUM 3.1.2 — OVER BILATERAL PESADO", msg)
        self.assertIn("jogo aberto", msg)
        self.assertIn("Não é sinal de Back", msg)

    def test_TG09_watch_first_then_forte_same_bucket_still_sends(self):
        """Sequência: WATCH bucket=1 → depois evolui pra FORTE bucket=1 → TG deve ir.
        WATCH NÃO consumiu bucket, então o anti-spam não bloqueia o FORTE."""
        # Cenário 1: WATCH OVER (cc=3, min 45, rate=15, bucket=1)
        ms1 = make_ms(minute=45, home_bc=1, away_bc=2, home_score=0, away_score=0)
        entry = {}
        prev = c31.get_previous_alert_state(entry)
        d1 = c31.evaluate_codigo_3_1(ms1, prev)
        self.assertEqual(d1["alert_type"], c31.ALERT_OVER_WATCH)
        self.assertEqual(d1["bucket"], 1)
        c31.update_state_after_alert(entry, d1)
        # state segue sem bucket consumido
        cc = entry.get("codigo_3_1") or {}
        self.assertEqual(cc.get("main_bucket_last", 0), 0)

        # Cenário 2: evolui pra FORTE OVER (cc=4, min 48, rate=12, bucket=1)
        ms2 = make_ms(minute=48, home_bc=2, away_bc=2, home_score=0, away_score=0)
        prev = c31.get_previous_alert_state(entry)
        d2 = c31.evaluate_codigo_3_1(ms2, prev)
        self.assertEqual(d2["alert_type"], c31.ALERT_OVER_FORTE)
        self.assertEqual(d2["bucket"], 1, "Bucket continua 1 (4//3=1)")
        # send_alert dispara (anti-spam não bloqueia, pois WATCH não consumiu)
        tg = self._mk_tg()
        sent = c31.send_alert(tg, d2)
        self.assertTrue(sent, "FORTE depois de WATCH no mesmo bucket DEVE disparar TG")

    def test_TG10_watch_first_then_premium_same_bucket_still_sends(self):
        """WATCH bucket=2 → PREMIUM bucket=2 → TG deve ir."""
        # WATCH bucket=2: cc=6, rate exatamente 15 (min 90, total 6)
        ms1 = make_ms(minute=90, home_bc=3, away_bc=3, home_score=0, away_score=0)
        # 3x3 = bilateral premium pego primeiro. Para forçar WATCH puro:
        # cc=6, rate>12 (pra bloquear PREMIUM/FORTE), mas <=15. Min 90/total 6 = 15.
        # Pra evitar BILATERAL: home_bc < 3. Tenta 2x4: bilateral exige AMBOS>=3 → 2x4 falha.
        # min 90, 2x4 (total=6): rate=15, expected=2, gols=0 → bilateral? 2<3 não. FORTE? rate<=12? não. WATCH ✓
        ms1 = make_ms(minute=90, home_bc=2, away_bc=4, home_score=0, away_score=0)
        entry = {}
        prev = c31.get_previous_alert_state(entry)
        d1 = c31.evaluate_codigo_3_1(ms1, prev)
        # Esse cenário também pode bater BACK FORTE (away=4, home=2, diff=2 — não, diff>=4 obrig)
        # diff=2 não satisfaz BACK FORTE. WATCH BACK? dom_cc=4, opp=2 (não≤1). Também não.
        # Então WATCH OVER puro.
        self.assertEqual(d1["alert_type"], c31.ALERT_OVER_WATCH)
        self.assertEqual(d1["bucket"], 2)
        c31.update_state_after_alert(entry, d1)

        # Agora evolui pra PREMIUM OVER: cc=6, rate≤12 (min 72), bucket=2
        ms2 = make_ms(minute=72, home_bc=2, away_bc=4, home_score=0, away_score=0)
        # 2x4=6, rate=12, gols=0<2 → PREMIUM OVER (não bilateral pq 2<3)
        prev = c31.get_previous_alert_state(entry)
        d2 = c31.evaluate_codigo_3_1(ms2, prev)
        self.assertEqual(d2["alert_type"], c31.ALERT_OVER_PREMIUM)
        self.assertEqual(d2["bucket"], 2)
        tg = self._mk_tg()
        sent = c31.send_alert(tg, d2)
        self.assertTrue(sent, "PREMIUM depois de WATCH no mesmo bucket DEVE disparar TG")

    def test_TG11_no_v12_leak_in_watch_log_pipeline(self):
        """WATCH não pode arrastar termos do Motor V1.2 mesmo no caminho de log."""
        d = c31.evaluate_codigo_3_1(
            make_ms(minute=45, home_bc=1, away_bc=2, home_score=0, away_score=0), {})
        self.assertEqual(d["alert_type"], c31.ALERT_OVER_WATCH)
        # Mesmo que não envie TG, format_telegram_message não pode vazar V1.2
        msg = c31.format_telegram_message(d)
        for forbidden in ["ENTER_OVER", "EXIT_OVER", "ENTER_BACK", "EXIT_BACK",
                          "MANUAL_REVIEW", "REDUCE", "LOCK_PROFIT", "HOLD"]:
            self.assertNotIn(forbidden, msg,
                              f"Termo V1.2 '{forbidden}' vazou no WATCH log-only")


def _run():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (TestOver, TestBilateral, TestBack,
                TestAntiSpam, TestPriority, TestRegression,
                TestWatchLogOnly):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run())
