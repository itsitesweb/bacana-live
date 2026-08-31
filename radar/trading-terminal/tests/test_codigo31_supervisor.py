"""
Testes do SUPERVISOR EXTERNO do CÓDIGO 3:1.

Cobre TODOS os 8 critérios obrigatórios da especificação:

  S1. Supervisor inicia daemon filho
  S2. Se heartbeat NÃO existe após startup_timeout → mata e reinicia
  S3. Se heartbeat está stale (> stale_threshold) → mata e reinicia
  S4. Se heartbeat recente → NÃO reinicia
  S5. Kill mata o process group inteiro (SIGTERM → SIGKILL)
  S6. Não spamma Telegram (1 alerta por travamento)
  S7. Envia alerta crítico no restart por travamento
  S8. Envia recuperação UMA vez quando heartbeat volta
  S9. Respeita max_restarts_per_hour

Bonus:
  S10. Heartbeat anterior ao daemon_start é tratado corretamente
  S11. Função pura evaluate_supervisor_state cobre 5 estados
"""
import json
import os
import signal
import sys
import tempfile
import unittest
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codigo31_supervisor import (
    Codigo31Supervisor,
    evaluate_supervisor_state,
    is_rate_limited,
)


# ════════════════════════════════════════════════════════════════════════
# FUNÇÃO PURA: evaluate_supervisor_state
# ════════════════════════════════════════════════════════════════════════
class TestEvaluateSupervisorState(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.hb = self.tmp / "heartbeat.json"
        self.now = datetime.now(timezone.utc)

    def test_E1_daemon_not_started(self):
        kill, reason = evaluate_supervisor_state(
            now_utc=self.now, daemon_start_utc=None,
            heartbeat_path=self.hb,
            startup_timeout_s=420, stale_heartbeat_s=600)
        self.assertTrue(kill)
        self.assertEqual(reason, "not_started")

    def test_E2_starting_up_no_heartbeat_yet(self):
        ds = self.now - timedelta(seconds=60)  # daemon há 60s
        kill, reason = evaluate_supervisor_state(
            now_utc=self.now, daemon_start_utc=ds,
            heartbeat_path=self.hb,
            startup_timeout_s=420, stale_heartbeat_s=600)
        self.assertFalse(kill)
        self.assertEqual(reason, "starting_up")

    def test_E3_startup_timeout_no_heartbeat_KILL(self):
        """BUG QUE PARALISOU O DAEMON — startup_timeout passou sem heartbeat."""
        ds = self.now - timedelta(seconds=500)  # 8min sem heartbeat
        kill, reason = evaluate_supervisor_state(
            now_utc=self.now, daemon_start_utc=ds,
            heartbeat_path=self.hb,
            startup_timeout_s=420, stale_heartbeat_s=600)
        self.assertTrue(kill)
        self.assertEqual(reason, "startup_timeout_no_heartbeat")

    def test_E4_heartbeat_pre_start_still_in_startup(self):
        """Heartbeat antigo + ainda em startup_timeout → não mata ainda."""
        ds = self.now - timedelta(seconds=60)
        old_ts = (ds - timedelta(minutes=30)).isoformat()
        self.hb.write_text(json.dumps({"last_scan_at": old_ts}))
        kill, reason = evaluate_supervisor_state(
            now_utc=self.now, daemon_start_utc=ds,
            heartbeat_path=self.hb,
            startup_timeout_s=420, stale_heartbeat_s=600)
        self.assertFalse(kill)
        self.assertEqual(reason, "starting_up_old_heartbeat")

    def test_E5_heartbeat_pre_start_after_timeout(self):
        """Heartbeat antigo + startup_timeout passou → mata."""
        ds = self.now - timedelta(seconds=500)
        old_ts = (ds - timedelta(minutes=30)).isoformat()
        self.hb.write_text(json.dumps({"last_scan_at": old_ts}))
        kill, reason = evaluate_supervisor_state(
            now_utc=self.now, daemon_start_utc=ds,
            heartbeat_path=self.hb,
            startup_timeout_s=420, stale_heartbeat_s=600)
        self.assertTrue(kill)
        self.assertEqual(reason, "stale_pre_start")

    def test_E6_heartbeat_healthy_no_kill(self):
        """Heartbeat fresco do daemon atual → não mata."""
        ds = self.now - timedelta(minutes=30)
        fresh_ts = (self.now - timedelta(minutes=2)).isoformat()
        self.hb.write_text(json.dumps({"last_scan_at": fresh_ts}))
        kill, reason = evaluate_supervisor_state(
            now_utc=self.now, daemon_start_utc=ds,
            heartbeat_path=self.hb,
            startup_timeout_s=420, stale_heartbeat_s=600)
        self.assertFalse(kill)
        self.assertEqual(reason, "healthy")

    def test_E7_heartbeat_stale_kill(self):
        """Heartbeat > stale_threshold → mata."""
        ds = self.now - timedelta(minutes=30)
        stale_ts = (self.now - timedelta(minutes=15)).isoformat()
        self.hb.write_text(json.dumps({"last_scan_at": stale_ts}))
        kill, reason = evaluate_supervisor_state(
            now_utc=self.now, daemon_start_utc=ds,
            heartbeat_path=self.hb,
            startup_timeout_s=420, stale_heartbeat_s=600)
        self.assertTrue(kill)
        self.assertIn("heartbeat_stale", reason)

    def test_E8_heartbeat_unreadable_kill(self):
        ds = self.now - timedelta(minutes=30)
        self.hb.write_text("{ NOT JSON")
        kill, reason = evaluate_supervisor_state(
            now_utc=self.now, daemon_start_utc=ds,
            heartbeat_path=self.hb,
            startup_timeout_s=420, stale_heartbeat_s=600)
        self.assertTrue(kill)
        self.assertIn("heartbeat_unreadable", reason)

    def test_E9_heartbeat_no_timestamp_kill(self):
        ds = self.now - timedelta(minutes=30)
        self.hb.write_text(json.dumps({"status": "alive"}))
        kill, reason = evaluate_supervisor_state(
            now_utc=self.now, daemon_start_utc=ds,
            heartbeat_path=self.hb,
            startup_timeout_s=420, stale_heartbeat_s=600)
        self.assertTrue(kill)
        self.assertEqual(reason, "heartbeat_no_timestamp")


# ════════════════════════════════════════════════════════════════════════
# RATE LIMIT
# ════════════════════════════════════════════════════════════════════════
class TestRateLimit(unittest.TestCase):

    def test_R1_under_limit_allows(self):
        now = datetime.now(timezone.utc)
        times = deque([now - timedelta(minutes=10), now - timedelta(minutes=5)])
        self.assertFalse(is_rate_limited(times, now, max_per_hour=10))

    def test_R2_at_limit_blocks(self):
        now = datetime.now(timezone.utc)
        times = deque([now - timedelta(minutes=i) for i in range(10)])
        self.assertTrue(is_rate_limited(times, now, max_per_hour=10))

    def test_R3_old_restarts_expire(self):
        """Restart de >1h atrás não conta no limite."""
        now = datetime.now(timezone.utc)
        times = deque([now - timedelta(hours=2)] * 5 + [now - timedelta(minutes=30)] * 3)
        self.assertFalse(is_rate_limited(times, now, max_per_hour=10))
        # após chamar, os antigos devem ter sido removidos
        self.assertEqual(len(times), 3)


# ════════════════════════════════════════════════════════════════════════
# SUPERVISOR — comportamento integrado
# ════════════════════════════════════════════════════════════════════════
class TestCodigo31Supervisor(unittest.TestCase):
    """Critérios S1-S9 da spec — TG técnico habilitado via env (debug)."""

    def setUp(self):
        # Habilita TG técnico só pra estes testes (verificam o mecanismo).
        # Default em produção é off (TestSupervisorTechnicalTGSuppression).
        os.environ["TECHNICAL_TELEGRAM_ENABLED"] = "1"
        self.tmp = Path(tempfile.mkdtemp())
        self.hb = self.tmp / "heartbeat.json"
        self.now_holder = [datetime.now(timezone.utc)]
        self.now_fn = lambda: self.now_holder[0]
        self.sent_telegram = []
        self.kills = []
        self.spawns = []

        # Mock subprocess.Popen
        self.fake_pid_counter = [1000]
        def fake_spawn():
            pid = self.fake_pid_counter[0]
            self.fake_pid_counter[0] += 1
            mock_proc = MagicMock()
            mock_proc.pid = pid
            mock_proc.poll = MagicMock(return_value=None)  # vivo
            self.spawns.append(pid)
            return mock_proc

        def fake_kill(proc):
            self.kills.append(proc.pid)
            proc.poll = MagicMock(return_value=0)
            return "sigterm_ok"

        def fake_send(msg):
            self.sent_telegram.append(msg)
            return True

        self.sup = Codigo31Supervisor(
            startup_timeout_s=420,
            stale_heartbeat_s=600,
            restart_sleep_s=0,  # sem sleep nos testes
            max_restarts_per_hour=10,
            check_interval_s=30,
            heartbeat_path=self.hb,
            telegram_sender=fake_send,
            now_fn=self.now_fn,
            spawn_fn=fake_spawn,
            kill_fn=fake_kill,
        )

    def tearDown(self):
        os.environ.pop("TECHNICAL_TELEGRAM_ENABLED", None)

    # ─── v2.5: TG técnico DESLIGADO por default (separado do mecanismo) ──

    # ─── S1 ───
    def test_S1_supervisor_starts_daemon(self):
        """Primeira chamada → starts daemon."""
        result = self.sup.check_once()
        self.assertEqual(result["action"], "started")
        self.assertEqual(len(self.spawns), 1)
        self.assertIsNotNone(self.sup.proc)

    # ─── S2 ───
    def test_S2_no_heartbeat_after_timeout_kills_and_restarts(self):
        """Sem heartbeat após startup_timeout → mata e reinicia."""
        self.sup.check_once()  # start
        # avança 8 minutos sem heartbeat
        self.now_holder[0] += timedelta(seconds=500)
        result = self.sup.check_once()
        self.assertEqual(result["action"], "restarted")
        self.assertEqual(result["reason"], "startup_timeout_no_heartbeat")
        self.assertEqual(len(self.kills), 1, "Deve ter matado o daemon travado")
        self.assertEqual(len(self.spawns), 2, "Deve ter spawnado um novo")

    # ─── S3 ───
    def test_S3_stale_heartbeat_kills_and_restarts(self):
        """Heartbeat fresco depois fica stale → mata e reinicia."""
        self.sup.check_once()  # start
        # heartbeat OK
        self.now_holder[0] += timedelta(minutes=2)
        self.hb.write_text(json.dumps({"last_scan_at": self.now_fn().isoformat()}))
        r1 = self.sup.check_once()
        self.assertEqual(r1["action"], "ok")
        # Avança 15min sem novo heartbeat → stale
        self.now_holder[0] += timedelta(minutes=15)
        r2 = self.sup.check_once()
        self.assertEqual(r2["action"], "restarted")
        self.assertIn("heartbeat_stale", r2["reason"])
        self.assertEqual(len(self.kills), 1)
        self.assertEqual(len(self.spawns), 2)

    # ─── S4 ───
    def test_S4_healthy_heartbeat_does_not_restart(self):
        """Heartbeat fresco → não reinicia."""
        self.sup.check_once()  # start
        self.now_holder[0] += timedelta(minutes=2)
        for _ in range(5):
            self.hb.write_text(json.dumps({"last_scan_at": self.now_fn().isoformat()}))
            r = self.sup.check_once()
            self.assertEqual(r["action"], "ok")
            self.assertEqual(r["reason"], "healthy")
            self.now_holder[0] += timedelta(minutes=1)
        self.assertEqual(len(self.kills), 0, "Não pode ter matado nenhum daemon saudável")

    # ─── S5 ───
    def test_S5_kill_invokes_process_group_kill(self):
        """O kill_fn (passado ao supervisor) é chamado — em produção mata o group."""
        self.sup.check_once()  # start daemon 1
        self.now_holder[0] += timedelta(seconds=500)
        self.sup.check_once()  # restart
        # O fake_kill foi chamado — em produção é _kill_process_group que faz SIGTERM→SIGKILL no grupo
        self.assertEqual(len(self.kills), 1)
        # Verifica que o kill_fn padrão (em produção) faz SIGTERM + SIGKILL — assinatura existe
        self.assertTrue(hasattr(self.sup, '_kill_process_group'))

    # ─── S6 + S7 ───
    def test_S6_S7_critical_alert_sent_once_per_restart(self):
        """Alerta crítico enviado 1x por restart, sem spam."""
        self.sup.check_once()  # start
        # 1º travamento
        self.now_holder[0] += timedelta(seconds=500)
        self.sup.check_once()  # restart 1
        critical_msgs = [m for m in self.sent_telegram if "🔴" in m and "SUPERVISOR" in m]
        self.assertEqual(len(critical_msgs), 1, "1 crítico por restart")
        self.assertIn("Motivo:", critical_msgs[0])
        self.assertIn("Restart nº: 2", critical_msgs[0])  # 1 inicial + 1 travamento

    # ─── S8 ───
    def test_S8_recovery_sent_once_when_heartbeat_returns(self):
        """Após travamento + restart, heartbeat volta → 1 recovery."""
        self.sup.check_once()  # start
        # Trava
        self.now_holder[0] += timedelta(seconds=500)
        self.sup.check_once()  # restart 1 → critical alert
        # Daemon novo escreve heartbeat
        self.now_holder[0] += timedelta(minutes=2)
        self.hb.write_text(json.dumps({"last_scan_at": self.now_fn().isoformat()}))
        # Próximo check → recovery
        r = self.sup.check_once()
        recoveries = [m for m in self.sent_telegram if "🟢" in m and "RECUPERADO" in m]
        self.assertEqual(len(recoveries), 1, "1 recovery por travamento")
        # Próximos checks → não envia recovery de novo
        for _ in range(3):
            self.now_holder[0] += timedelta(seconds=30)
            self.hb.write_text(json.dumps({"last_scan_at": self.now_fn().isoformat()}))
            self.sup.check_once()
        recoveries2 = [m for m in self.sent_telegram if "🟢" in m and "RECUPERADO" in m]
        self.assertEqual(len(recoveries2), 1, "Recovery não pode repetir")

    # ─── S9 ───
    def test_S9_rate_limit_respected(self):
        """Após 10 restarts em 1h, supervisor para de matar."""
        sup = Codigo31Supervisor(
            startup_timeout_s=420, stale_heartbeat_s=600,
            restart_sleep_s=0, max_restarts_per_hour=3,
            check_interval_s=30, heartbeat_path=self.hb,
            telegram_sender=lambda m: True,
            now_fn=self.now_fn,
            spawn_fn=lambda: MagicMock(pid=999, poll=MagicMock(return_value=None)),
            kill_fn=lambda p: "sigterm_ok",
        )
        # 3 restarts seguidos por travamento — passa
        for i in range(3):
            sup.check_once()
            self.now_holder[0] += timedelta(seconds=500)  # travado
        # 4º deveria ser rate-limited
        r = sup.check_once()
        self.assertEqual(r["action"], "rate_limited")

    # ─── S10: dedup recovery por travamento ───
    def test_S10_recovery_dedup_per_restart_cycle(self):
        """Cada novo travamento permite 1 nova recovery."""
        self.sup.check_once()  # start
        # 1º trava
        self.now_holder[0] += timedelta(seconds=500)
        self.sup.check_once()  # restart 1
        # heartbeat volta
        self.now_holder[0] += timedelta(minutes=2)
        self.hb.write_text(json.dumps({"last_scan_at": self.now_fn().isoformat()}))
        self.sup.check_once()  # recovery 1
        # 2º trava
        self.now_holder[0] += timedelta(minutes=15)
        self.sup.check_once()  # restart 2
        # heartbeat volta de novo
        self.now_holder[0] += timedelta(minutes=2)
        self.hb.write_text(json.dumps({"last_scan_at": self.now_fn().isoformat()}))
        self.sup.check_once()  # recovery 2
        recoveries = [m for m in self.sent_telegram if "🟢" in m and "RECUPERADO" in m]
        self.assertEqual(len(recoveries), 2, "Cada travamento permite 1 nova recovery")

    # ─── S11: silêncio quando OK (não spamma) ───
    def test_S11_no_telegram_when_healthy(self):
        """Sistema saudável = ZERO mensagens positivas recorrentes."""
        self.sup.check_once()  # start
        self.now_holder[0] += timedelta(minutes=2)
        # Vários checks com heartbeat saudável
        for _ in range(20):
            self.hb.write_text(json.dumps({"last_scan_at": self.now_fn().isoformat()}))
            self.sup.check_once()
            self.now_holder[0] += timedelta(seconds=30)
        # Não pode ter NENHUMA mensagem (não houve travamento)
        self.assertEqual(self.sent_telegram, [],
                         "Sistema saudável NUNCA envia Telegram (anti-spam)")


# ════════════════════════════════════════════════════════════════════════
# KILL PROCESS GROUP — comportamento real
# ════════════════════════════════════════════════════════════════════════
class TestKillProcessGroup(unittest.TestCase):
    """Garante que _kill_process_group manda SIGTERM no group, e SIGKILL se preciso."""

    def test_K1_sigterm_to_pgid(self):
        sup = Codigo31Supervisor(send_telegram_enabled=False)
        proc = MagicMock()
        proc.pid = 12345
        # 1ª chamada de poll() retorna None (vivo), depois 0 (morreu após SIGTERM)
        poll_results = [None] + [0] * 100
        proc.poll.side_effect = lambda: poll_results.pop(0)

        with patch('os.getpgid', return_value=12345), \
             patch('os.killpg') as mock_killpg, \
             patch('time.sleep'):
            result = sup._kill_process_group(proc)
        mock_killpg.assert_any_call(12345, signal.SIGTERM)
        self.assertEqual(result, "sigterm_ok")

    def test_K2_sigkill_when_sigterm_ignored(self):
        sup = Codigo31Supervisor(send_telegram_enabled=False)
        proc = MagicMock()
        proc.pid = 12345
        proc.poll.return_value = None  # nunca morre por SIGTERM
        proc.wait.return_value = 0

        with patch('os.getpgid', return_value=12345), \
             patch('os.killpg') as mock_killpg, \
             patch('time.sleep'):
            result = sup._kill_process_group(proc)
        # Deve ter mandado SIGTERM e depois SIGKILL
        calls = [c.args for c in mock_killpg.call_args_list]
        self.assertIn((12345, signal.SIGTERM), calls)
        self.assertIn((12345, signal.SIGKILL), calls)
        self.assertEqual(result, "sigkill_required")

    def test_K3_already_dead(self):
        sup = Codigo31Supervisor(send_telegram_enabled=False)
        proc = MagicMock()
        proc.poll.return_value = 0  # já morto
        result = sup._kill_process_group(proc)
        self.assertEqual(result, "already_dead")


class TestSupervisorTechnicalTGSuppression(unittest.TestCase):
    """v2.5 — TG técnico do supervisor DESLIGADO por padrão.

    Default em produção: nenhum 🔴/🟢 técnico vai pro Telegram. Logs
    suppressed_* registram a supressão. Override via env var
    TECHNICAL_TELEGRAM_ENABLED=1 (debug only).
    """

    def setUp(self):
        # Garante ambiente padrão (env não setada)
        os.environ.pop("TECHNICAL_TELEGRAM_ENABLED", None)
        self.tmp = Path(tempfile.mkdtemp())
        self.hb = self.tmp / "heartbeat.json"
        self.now_holder = [datetime.now(timezone.utc)]
        self.now_fn = lambda: self.now_holder[0]
        self.sent_telegram = []
        self.spawns = []
        self.kills = []
        self.fake_pid_counter = [9000]

        def fake_spawn():
            pid = self.fake_pid_counter[0]
            self.fake_pid_counter[0] += 1
            mock_proc = MagicMock()
            mock_proc.pid = pid
            mock_proc.poll = MagicMock(return_value=None)
            self.spawns.append(pid)
            return mock_proc

        def fake_kill(proc):
            self.kills.append(proc.pid)
            proc.poll = MagicMock(return_value=0)
            return "sigterm_ok"

        def fake_send(msg):
            self.sent_telegram.append(msg)
            return True

        self.sup = Codigo31Supervisor(
            startup_timeout_s=420, stale_heartbeat_s=600,
            restart_sleep_s=0, max_restarts_per_hour=10, check_interval_s=30,
            heartbeat_path=self.hb,
            telegram_sender=fake_send,
            now_fn=self.now_fn,
            spawn_fn=fake_spawn,
            kill_fn=fake_kill,
        )

    def test_T1_supervisor_critical_alert_NOT_sent_by_default(self):
        """Default: TG técnico suprimido — nenhum 🔴 enviado."""
        self.sup.check_once()  # start
        self.now_holder[0] += timedelta(seconds=500)
        self.sup.check_once()  # restart por travamento
        critical = [m for m in self.sent_telegram
                     if "🔴" in m and "SUPERVISOR" in m]
        self.assertEqual(len(critical), 0,
                          "TG técnico crítico NÃO pode ser enviado por default")

    def test_T2_supervisor_recovered_alert_NOT_sent_by_default(self):
        """Default: TG técnico de recuperação suprimido."""
        self.sup.check_once()
        self.now_holder[0] += timedelta(seconds=500)
        self.sup.check_once()  # restart
        self.now_holder[0] += timedelta(minutes=2)
        self.hb.write_text(json.dumps({"last_scan_at": self.now_fn().isoformat()}))
        self.sup.check_once()  # heartbeat voltou
        recovered = [m for m in self.sent_telegram
                      if "🟢" in m and "RECUPERADO" in m]
        self.assertEqual(len(recovered), 0,
                          "TG técnico de recovery NÃO pode ser enviado por default")

    def test_T3_supervisor_enabled_via_env_var_sends(self):
        """Com TECHNICAL_TELEGRAM_ENABLED=1, mecanismo SIM envia (debug)."""
        os.environ["TECHNICAL_TELEGRAM_ENABLED"] = "1"
        try:
            self.sup.check_once()
            self.now_holder[0] += timedelta(seconds=500)
            self.sup.check_once()
            critical = [m for m in self.sent_telegram
                         if "🔴" in m and "SUPERVISOR" in m]
            self.assertEqual(len(critical), 1)
        finally:
            os.environ.pop("TECHNICAL_TELEGRAM_ENABLED", None)


class TestOperationalConfigFlag(unittest.TestCase):
    """v2.5 — flag operacional centralizada."""

    def setUp(self):
        os.environ.pop("TECHNICAL_TELEGRAM_ENABLED", None)

    def tearDown(self):
        os.environ.pop("TECHNICAL_TELEGRAM_ENABLED", None)

    def test_OC1_default_off(self):
        from src.operational_config import is_technical_telegram_enabled
        self.assertFalse(is_technical_telegram_enabled())

    def test_OC2_env_var_on(self):
        os.environ["TECHNICAL_TELEGRAM_ENABLED"] = "1"
        from src.operational_config import is_technical_telegram_enabled
        self.assertTrue(is_technical_telegram_enabled())

    def test_OC3_env_var_explicit_off(self):
        os.environ["TECHNICAL_TELEGRAM_ENABLED"] = "0"
        from src.operational_config import is_technical_telegram_enabled
        self.assertFalse(is_technical_telegram_enabled())

    def test_OC4_aliases_share_default(self):
        from src.operational_config import (
            coverage_guard_telegram_enabled,
            supervisor_telegram_enabled,
            watchdog_telegram_enabled,
        )
        self.assertFalse(coverage_guard_telegram_enabled())
        self.assertFalse(supervisor_telegram_enabled())
        self.assertFalse(watchdog_telegram_enabled())


def _run():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (TestEvaluateSupervisorState, TestRateLimit,
                TestCodigo31Supervisor, TestKillProcessGroup,
                TestSupervisorTechnicalTGSuppression, TestOperationalConfigFlag):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_run())
