"""
Telegram Client — Motor V1.2 Seção 23 (Protocolo de Notificação)

Regras de envio (Seção 23 + ajustes operacionais):
  SEMPRE envia: ENTER_*, EXIT_*, REDUCE_*, LOCK_PROFIT
  Envia condicionalmente:
    - MANUAL_REVIEW: só se novo (match_id+reason diferente do último)
    - YELLOW_ALERT_*: só se posição aberta (já garantido pelo engine)
    - SIGNAL_EXPIRED: só se houve sinal anterior real (last_signal_action)
  NUNCA envia:
    - NO_ACTION, HOLD_*, WATCH_*, COOLDOWN, SIGNAL_MAINTAINED
    - BLOCKED comum (NO_NEW_ENTRY_AFTER_83, NO_NEW_OVER_AFTER_75,
      SCORE_KILLED_GAME sem posição, DATA_DELAY, MIN_BC_ZERO_BLOCKS_OVER)
    - BLOCKED só envia se posição aberta OU cancela sinal ativo
  Anti-spam:
    - match_id + action + blocked_reason repetido em 5 min → filtrado
    - MANUAL_REVIEW repetido com mesmo motivo → filtrado
    - ENTER_* repetido → 🔁 SINAL MANTIDO (1 vez, depois silêncio)

Modo teste:
    python3 -m src.telegram_client --test
"""
import os
import json
import urllib.request
import urllib.error
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from .models import Decision, MatchState, DerivedVars
from .telegram_formatter import _translate_reason


@dataclass
class SendResult:
    """
    Retorno explícito de TelegramClient.send_decision().

    Truthy quando a mensagem foi efetivamente entregue ao Telegram.
    Falsy quando foi filtrada/erro — `reason` explica o motivo (logado no JSONL).

    Razões possíveis (campo `reason`):
      SENT                       — mensagem entregue
      MANUAL_REVIEW_LOG_ONLY     — bloqueio absoluto (defense-in-depth)
      NOT_READY                  — token/chat_id ausentes ou enabled=false
      STALE_MATCH                — jogo stale (min 1-2 com placar repetido)
      NO_DATA_EVOLUTION          — scan idêntico ao anterior
      FILTERED_NEVER_SEND        — action está em NEVER_SEND
      FILTERED_BLOCKED_SILENT    — BLOCKED comum sem posição/sinal ativo
      FILTERED_SIGNAL_EXPIRED    — SIGNAL_EXPIRED sem sinal anterior
      FILTERED_UNKNOWN_ACTION    — action desconhecida → silêncio
      SPAM_FILTERED              — duplicado dentro do cooldown
      HTTP_ERROR                 — falha na entrega
    """
    sent: bool
    reason: str

    def __bool__(self) -> bool:  # compat com `if sent:`
        return self.sent


# ─── Classificação de actions para filtro Telegram ────────────────────

# Actions que SEMPRE disparam notificação Telegram (acção do operador necessária)
ALWAYS_SEND = {
    # 23.5 Entrada Back
    "ENTER_BACK_T1_EARLY", "ENTER_BACK_T1_MAIN", "ENTER_BACK_T1_LATE",
    "ENTER_BACK_T2", "ENTER_BACK_SMALL",
    # 23.6 Entrada Over
    "ENTER_OVER_PREMIUM", "ENTER_OVER_BILATERAL_FORTE",
    "ENTER_OVER_SMALL", "ENTER_OVER_GOL_LIMITE",
    # 23.7 Gestão Back (posição aberta)
    "EXIT_BACK", "REDUCE_BACK", "YELLOW_ALERT_BACK",
    # 23.8 Gestão Over (posição aberta)
    "EXIT_OVER", "REDUCE_OVER", "YELLOW_ALERT_OVER", "LOCK_PROFIT",
}

# Actions condicionais — lógica em should_send()
CONDITIONAL_SEND = {"SIGNAL_EXPIRED", "BLOCKED"}

# NUNCA enviar (silêncio total — log only)
NEVER_SEND = {
    "NO_ACTION", "COOLDOWN", "SIGNAL_MAINTAINED",
    "HOLD_BACK", "HOLD_OVER", "HOLD_BACK_WITH_CAUTION", "HOLD_OVER_WITH_CAUTION",
    "WATCH_BACK_LATE", "WATCH_OVER",
    "MANUAL_REVIEW",
}

# Blocked reasons que são comuns e NUNCA geram Telegram
SILENT_BLOCKED_REASONS = {
    "NO_NEW_ENTRY_AFTER_83",
    "NO_NEW_OVER_AFTER_75",
    "SCORE_KILLED_GAME",
    "DATA_DELAY",
    "DATA_INVALID",
    "MIN_BC_ZERO_BLOCKS_OVER",
    "DRAW_BLOCKS_GOL_LIMITE",
    "LAST_BC_TOO_OLD",
    "NO_NEW_BC_SINCE_OVER_EXIT",  # Anti-reentry: silent block
    "STALE_MATCH",
    "NO_DATA_EVOLUTION",
    "DUPLICATE_MANUAL_REVIEW",
}


class TelegramClient:
    """Client for sending Telegram notifications."""

    def __init__(self, cfg: dict):
        tg_cfg = cfg.get("telegram", {})

        self.enabled = tg_cfg.get("enabled", False)
        self.simulation_tag = tg_cfg.get("simulation_tag", "[SIMULAÇÃO]")
        self.send_info = tg_cfg.get("send_info_messages", False)
        self.send_hold = tg_cfg.get("send_hold_messages", False)
        self.anti_spam_minutes = tg_cfg.get("anti_spam_minutes", 5)
        self.manual_review_cooldown_minutes = tg_cfg.get("manual_review_cooldown_minutes", 30)

        # Read token/chat_id from env vars
        token_env = tg_cfg.get("bot_token_env", "TELEGRAM_BOT_TOKEN")
        chat_id_env = tg_cfg.get("chat_id_env", "TELEGRAM_CHAT_ID")

        self.bot_token = os.environ.get(token_env, "")
        self.chat_id = os.environ.get(chat_id_env, "")

        # State file path (persists across daemon restarts)
        self._state_file = Path(tg_cfg.get("state_file", "")) or None
        if not self._state_file or str(self._state_file) == "":
            # Default: logs/telegram_sent_state.json relative to project root
            base = Path(__file__).parent.parent / "logs"
            self._state_file = base / "telegram_sent_state.json"

        # Load persisted state or start fresh
        persisted = self._load_persisted_state()

        # Anti-spam tracker: {spam_key: (last_real_ts_iso, last_minute, sent_maintained)}
        self._last_signal = persisted.get("last_signal", {})

        # Stale/evolution tracker: {stable_key: {field: value}}
        self._last_scan_state = persisted.get("last_scan_state", {})

        # Stats
        self.messages_sent = 0
        self.messages_skipped = 0
        self.errors = 0

    def _load_persisted_state(self) -> dict:
        """Load anti-spam state from file (survives daemon restart)."""
        try:
            if self._state_file and self._state_file.exists():
                with open(self._state_file, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_persisted_state(self):
        """Save anti-spam state to file."""
        try:
            if self._state_file:
                self._state_file.parent.mkdir(parents=True, exist_ok=True)
                data = {
                    "last_signal": self._last_signal,
                    "last_scan_state": self._last_scan_state,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                with open(self._state_file, "w") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    @staticmethod
    def _stable_key(ms: MatchState) -> str:
        """Generate a stable match key independent of match_id.
        Uses normalized team names — survives URL/ID changes."""
        home = ms.home.strip().lower()
        away = ms.away.strip().lower()
        return f"{home}|{away}"

    def is_ready(self) -> bool:
        """Check if Telegram is configured and ready to send."""
        return bool(self.enabled and self.bot_token and self.chat_id)

    def get_status(self) -> str:
        """Return human-readable status string."""
        if not self.enabled:
            return "Telegram DESABILITADO (telegram.enabled=false)"
        if not self.bot_token:
            return "Telegram ERRO: TELEGRAM_BOT_TOKEN não definido"
        if not self.chat_id:
            return "Telegram ERRO: TELEGRAM_CHAT_ID não definido"
        return "Telegram PRONTO"

    def should_send(self, decision, ms: MatchState = None) -> bool:
        """
        Filtro Telegram conforme Seção 23 + regras operacionais.

        SEMPRE envia: ENTER_*, EXIT_*, REDUCE_*, LOCK_PROFIT, YELLOW_ALERT_*
        CONDICIONAL:
          - SIGNAL_EXPIRED: só se houve sinal anterior real
          - BLOCKED: só se posição aberta OU cancela sinal ativo
        NUNCA: NO_ACTION, HOLD_*, WATCH_*, COOLDOWN, SIGNAL_MAINTAINED, MANUAL_REVIEW
        """
        action = decision.recommended_action if hasattr(decision, 'recommended_action') else decision

        # 1. NUNCA enviar
        if action in NEVER_SEND:
            return False

        # 2. SEMPRE enviar
        if action in ALWAYS_SEND:
            return True

        # 3. CONDICIONAL: BLOCKED
        if action == "BLOCKED":
            reason = getattr(decision, 'blocked_reason', '') or ''
            # Prioridade 1: posição aberta → SEMPRE enviar (risco operacional)
            if ms and ms.position_type in ("BACK", "OVER"):
                return True
            # Prioridade 2: cancela sinal ativo → enviar
            if ms and ms.last_signal_action and ms.last_signal_action.startswith("ENTER_"):
                return True
            # Sem posição e sem sinal ativo → silêncio (log only)
            return False

        # 4. CONDICIONAL: SIGNAL_EXPIRED
        if action == "SIGNAL_EXPIRED":
            # Só se houve sinal anterior real
            if ms and ms.last_signal_action and ms.last_signal_action.startswith("ENTER_"):
                return True
            return False

        # 6. Qualquer outro action desconhecido → não enviar
        return False

    def check_anti_spam(self, match_id: str, action: str, minute: int,
                        blocked_reason: str = "",
                        ms: MatchState = None) -> str:
        """
        Anti-spam expandido — usa TEMPO REAL (não game minute) e CHAVE ESTÁVEL.

        Chave primária: stable_key(home|away) + action + blocked_reason
        Fallback: match_id + action + blocked_reason
        Janelas de cooldown (em minutos reais):
          - MANUAL_REVIEW: 30 min
          - ENTER_*: 5 min — primeira repetição = SIGNAL_MAINTAINED, depois silêncio
          - Qualquer outro: 5 min

        Returns:
          - Original action se OK
          - "SIGNAL_MAINTAINED" se ENTER repetido (1 vez)
          - "SPAM_FILTERED" se qualquer repetido dentro do cooldown
        """
        # Chave estável baseada em nomes dos times (não depende de match_id)
        if ms:
            stable = self._stable_key(ms)
        else:
            stable = match_id
        spam_key = f"{stable}|{action}|{blocked_reason}"

        # Determinar janela de cooldown (minutos reais)
        if action == "MANUAL_REVIEW":
            cooldown = self.manual_review_cooldown_minutes
        else:
            cooldown = self.anti_spam_minutes

        now = datetime.now(timezone.utc)

        if spam_key in self._last_signal:
            entry = self._last_signal[spam_key]
            # Parse last timestamp
            last_ts_str = entry[0] if isinstance(entry, list) else entry.get("ts", "")
            sent_maintained = entry[1] if isinstance(entry, list) else entry.get("maintained", False)
            try:
                last_ts = datetime.fromisoformat(last_ts_str)
                elapsed_minutes = (now - last_ts).total_seconds() / 60.0
            except (ValueError, TypeError):
                elapsed_minutes = 9999  # force pass on parse error

            if elapsed_minutes < cooldown:
                if action.startswith("ENTER_") and not sent_maintained:
                    self._last_signal[spam_key] = [now.isoformat(), True]
                    self._save_persisted_state()
                    return "SIGNAL_MAINTAINED"
                else:
                    return "SPAM_FILTERED"

        # Registar este sinal com timestamp real
        self._last_signal[spam_key] = [now.isoformat(), False]
        self._save_persisted_state()
        return action

    def check_stale_match(self, ms: MatchState, decision) -> str:
        """
        Detecta jogo stale / sem evolução. Usa chave estável (home|away).

        Compara scan atual com scan anterior.
        Se minute, score, CC, xGOT e action são todos iguais → NO_DATA_EVOLUTION.
        Se minute <= 2 e score > 0 repetido → STALE_MATCH (dado suspeito).

        Returns:
          - "" se OK (pode enviar)
          - "NO_DATA_EVOLUTION" se sem evolução
          - "STALE_MATCH" se dado stale/suspeito
        """
        action = decision.recommended_action if hasattr(decision, 'recommended_action') else str(decision)
        blocked_reason = getattr(decision, 'blocked_reason', '') or ''
        mid = self._stable_key(ms)

        current_state = {
            "minute": ms.minute,
            "home_score": ms.home_score,
            "away_score": ms.away_score,
            "home_bc": ms.home_bc,
            "away_bc": ms.away_bc,
            "home_xgot": round(ms.home_xgot, 2),
            "away_xgot": round(ms.away_xgot, 2),
            "action": action,
            "reason": blocked_reason,
        }

        # Minuto <= 2 com gol → dado suspeito se repetido
        if ms.minute <= 2 and (ms.home_score + ms.away_score) > 0:
            if mid in self._last_scan_state:
                prev = self._last_scan_state[mid]
                if prev.get("minute", -1) <= 2 and (prev.get("home_score", 0) + prev.get("away_score", 0)) > 0:
                    self._last_scan_state[mid] = current_state
                    self._save_persisted_state()
                    return "STALE_MATCH"

        # Comparar com scan anterior
        if mid in self._last_scan_state:
            prev = self._last_scan_state[mid]
            if current_state == prev:
                return "NO_DATA_EVOLUTION"

        self._last_scan_state[mid] = current_state
        self._save_persisted_state()
        return ""

    def format_message(self, decision: Decision, ms: MatchState,
                       d: DerivedVars, is_maintained: bool = False) -> str:
        """
        Format Telegram message seguindo Seção 23 do Motor V1.2 EXATAMENTE.
        Cada action type tem template próprio (23.5–23.12).
        """
        action = decision.recommended_action
        lines = []

        # Tag opcional (vazio = modo definitivo)
        if self.simulation_tag:
            lines.append(f"{self.simulation_tag}")
            lines.append("")

        # Helpers locais
        dom_name = ""
        if d and d.dominant_team:
            dom_name = ms.home if d.dominant_team == "home" else ms.away
        score = f"{ms.home_score}-{ms.away_score}"
        dom_bc = d.dominant_bc if d else ms.home_bc
        opp_bc = d.opponent_bc if d else ms.away_bc
        dom_xgot = d.dominant_xgot if d else ms.home_xgot
        opp_xgot = d.opponent_xgot if d else ms.away_xgot

        # ─── 23.12 SINAL MANTIDO (anti-spam) ──────────────────
        if is_maintained:
            lines.append("🔁 SINAL MANTIDO")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Ação: {ms.last_signal_action or action}")
            lines.append(f"Min {ms.minute} | Válido até min {decision.signal_valid_until}")
            lines.append(f"Comando: MESMO SINAL. NÃO DUPLICAR ENTRADA.")
            return "\n".join(lines)

        # ─── 23.5 Entradas Back ───────────────────────────────
        if action in ("ENTER_BACK_T1_MAIN", "ENTER_BACK_T1_EARLY"):
            team = dom_name or ms.home
            tier = decision.confidence_tier or ("A-" if "EARLY" in action else "A")
            lines.append(f"🟢 ACTION | ENTRAR BACK — {team}")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"CC {dom_bc}x{opp_bc} | xGOT {dom_xgot:.2f}x{opp_xgot:.2f}")
            lines.append(f"Mercado: BACK {team} | Tier {tier}")
            lines.append(f"Válido até: min {decision.signal_valid_until}")
            lines.append(f"Comando: ENTRAR AGORA.")
            lines.append(f"Motivo: CC unilateral + adversário zerado + xGOT confirmado.")
            return "\n".join(lines)

        if action == "ENTER_BACK_T1_LATE":
            team = dom_name or ms.home
            tier = decision.confidence_tier or "B+"
            lines.append(f"🟢 ACTION | ENTRAR BACK LATE — {team}")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"CC {dom_bc}x{opp_bc} | xGOT {dom_xgot:.2f}x{opp_xgot:.2f}")
            lines.append(f"Mercado: BACK {team} | Tier {tier}")
            lines.append(f"Válido até: min {decision.signal_valid_until}")
            lines.append(f"Comando: ENTRAR COM CAUTELA.")
            lines.append(f"Motivo: CC unilateral confirmada, mas janela 51-65 min.")
            return "\n".join(lines)

        if action == "ENTER_BACK_T2":
            team = dom_name or ms.home
            lines.append(f"🟢 ACTION | ENTRAR BACK T2 — {team}")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"CC {dom_bc}x{opp_bc} | xGOT {dom_xgot:.2f}x{opp_xgot:.2f}")
            lines.append(f"Mercado: BACK {team} | Tier B")
            lines.append(f"Válido até: min {decision.signal_valid_until}")
            lines.append(f"Comando: ENTRAR COM CAUTELA.")
            lines.append(f"Motivo: 2 CC, adv zerado, xGOT confirmado. Inferior ao T1.")
            return "\n".join(lines)

        if action == "ENTER_BACK_SMALL":
            team = dom_name or ms.home
            tier = decision.confidence_tier or "B"
            lines.append(f"🟡 ACTION | BACK SMALL — {team}")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"CC {dom_bc}x{opp_bc} | xGOT {dom_xgot:.2f}x{opp_xgot:.2f}")
            lines.append(f"Mercado: BACK {team} | Tier {tier}")
            lines.append(f"Válido até: min {decision.signal_valid_until}")
            lines.append(f"Comando: ENTRADA REDUZIDA OU REVISÃO RÁPIDA.")
            lines.append(f"Motivo: dominante forte, mas adv já tem 1 CC.")
            return "\n".join(lines)

        # ─── 23.6 Entradas Over ───────────────────────────────
        if action == "ENTER_OVER_PREMIUM":
            total_bc = d.total_bc if d else (ms.home_bc + ms.away_bc)
            min_bc = d.min_bc if d else min(ms.home_bc, ms.away_bc)
            rate = f"{d.match_bc_rate:.1f}" if d else "?"
            lines.append(f"🟢 ACTION | ENTRAR OVER 2.5")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"CC {ms.home_bc}x{ms.away_bc} | Total {total_bc} | MinCC {min_bc}")
            lines.append(f"Mercado: OVER 2.5 | Rate {rate}")
            lines.append(f"Válido até: min {decision.signal_valid_until}")
            lines.append(f"Comando: ENTRAR OVER 2.5 AGORA.")
            lines.append(f"Motivo: CC bilateral + ritmo premium + jogo vivo.")
            return "\n".join(lines)

        if action == "ENTER_OVER_BILATERAL_FORTE":
            min_bc = d.min_bc if d else min(ms.home_bc, ms.away_bc)
            lines.append(f"🟢 ACTION | OVER BILATERAL FORTE")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"CC {ms.home_bc}x{ms.away_bc} | MinCC {min_bc}")
            lines.append(f"Mercado: OVER 2.5 / BTS | Tier B+")
            lines.append(f"Válido até: min {decision.signal_valid_until}")
            lines.append(f"Comando: ENTRAR OVER 2.5 / AVALIAR BTS.")
            lines.append(f"Motivo: ambos os times já criaram 2+ CC.")
            return "\n".join(lines)

        if action == "ENTER_OVER_SMALL":
            mins_since = d.minutes_since_last_match_bc if d else 0
            mkt = decision.market_target or "OVER_2_5"
            lines.append(f"🟡 ACTION | OVER SMALL")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"CC {ms.home_bc}x{ms.away_bc} | Última CC há {mins_since} min")
            lines.append(f"Mercado: {mkt}")
            lines.append(f"Válido até: min {decision.signal_valid_until}")
            lines.append(f"Comando: ENTRADA REDUZIDA.")
            lines.append(f"Motivo: volume alto + bilateralidade, mas janela tardia.")
            return "\n".join(lines)

        if action == "ENTER_OVER_GOL_LIMITE":
            total_bc = d.total_bc if d else (ms.home_bc + ms.away_bc)
            mins_since = d.minutes_since_last_match_bc if d else 0
            bts_str = "SIM" if (d and d.bts) else "NÃO"
            diff = d.score_diff if d else abs(ms.home_score - ms.away_score)
            alt_mkt = decision.alternative_market or "—"
            lines.append(f"🔥 ACTION | OVER GOL LIMITE — +1 GOL")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"CC {ms.home_bc}x{ms.away_bc} | Total {total_bc} | Última CC {mins_since} min")
            lines.append(f"BTS: {bts_str} | Diff: {diff}")
            lines.append(f"Mercado: NEXT_GOAL | Alt: {alt_mkt}")
            lines.append(f"Válido até: min {decision.signal_valid_until}")
            lines.append(f"Comando: ENTRAR RÁPIDO OU IGNORAR SE PREÇO CORRIGIU.")
            lines.append(f"Motivo: CC extremo + BTS + placar desigual + jogo vivo.")
            return "\n".join(lines)

        # ─── 23.7 Gestão Back ─────────────────────────────────
        if action == "HOLD_BACK":
            team = ms.position_team or dom_name or ms.home
            bc_since_team = d.team_bc_since_entry if d else 0
            bc_since_opp = d.opponent_bc_since_entry if d else 0
            mins_since_dom = d.minutes_since_team_last_bc if d else 0
            lines.append(f"🔵 HOLD BACK — {team}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"CC desde entrada: Dom {bc_since_team} x Adv {bc_since_opp}")
            lines.append(f"Última CC dom: {mins_since_dom} min")
            lines.append(f"Comando: MANTER POSIÇÃO.")
            lines.append(f"Motivo: dominante respondeu e tese segue viva.")
            return "\n".join(lines)

        if action == "YELLOW_ALERT_BACK":
            team = ms.position_team or dom_name or ms.home
            bc_since_opp = d.opponent_bc_since_entry if d else 0
            mins_since_dom = d.minutes_since_team_last_bc if d else 0
            lines.append(f"🟡 ALERTA BACK — {team}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"Adv CC desde entrada: {bc_since_opp}")
            lines.append(f"Dom sem CC há: {mins_since_dom} min")
            lines.append(f"Comando: NÃO AUMENTAR. MONITORAR SAÍDA.")
            lines.append(f"Motivo: adv acordou ou dominante perdeu ritmo.")
            return "\n".join(lines)

        if action == "REDUCE_BACK":
            team = ms.position_team or dom_name or ms.home
            mins_since_dom = d.minutes_since_team_last_bc if d else 0
            xgot_since = d.team_xgot_since_entry if d else 0.0
            lines.append(f"🟠 REDUZIR BACK — {team}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"Dom sem CC há {mins_since_dom} min")
            lines.append(f"xGOT desde entrada: {xgot_since:.2f}")
            lines.append(f"Comando: REDUZIR EXPOSIÇÃO.")
            lines.append(f"Motivo: dominante perdeu ritmo e não gerou xGOT novo.")
            return "\n".join(lines)

        if action == "EXIT_BACK":
            team = ms.position_team or dom_name or ms.home
            bc_since_team = d.team_bc_since_entry if d else 0
            bc_since_opp = d.opponent_bc_since_entry if d else 0
            # Traduz tokens internos (RED_CARD, etc.) pra pt-BR.
            # Fallback NÃO usa operator_instruction pra não duplicar com "Comando: ...".
            reason = _translate_reason(decision.blocked_reason) or "tese invalidada"
            lines.append(f"🔴 URGENT | SAIR DO BACK — {team}")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"CC desde entrada: Dom {bc_since_team} x Adv {bc_since_opp}")
            lines.append(f"Motivo: {reason}")
            lines.append(f"Comando: FECHAR POSIÇÃO AGORA.")
            return "\n".join(lines)

        # ─── 23.8 Gestão Over ─────────────────────────────────
        if action == "HOLD_OVER":
            mins_since = d.minutes_since_last_match_bc if d else 0
            lines.append(f"🔵 HOLD OVER")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"Última CC há {mins_since} min")
            lines.append(f"Comando: MANTER POSIÇÃO.")
            lines.append(f"Motivo: ritmo de CC ainda vivo.")
            return "\n".join(lines)

        if action == "YELLOW_ALERT_OVER":
            mins_since = d.minutes_since_last_match_bc if d else 0
            lines.append(f"🟡 ALERTA OVER")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"Sem CC há {mins_since} min")
            lines.append(f"Comando: NÃO AUMENTAR. MONITORAR REDUÇÃO.")
            lines.append(f"Motivo: ritmo de CC começou a cair.")
            return "\n".join(lines)

        if action == "REDUCE_OVER":
            mins_since = d.minutes_since_last_match_bc if d else 0
            lines.append(f"🟠 REDUZIR OVER")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"Sem CC há {mins_since} min")
            lines.append(f"Comando: REDUZIR EXPOSIÇÃO.")
            lines.append(f"Motivo: 15+ min sem nova CC.")
            return "\n".join(lines)

        if action == "EXIT_OVER":
            # Traduz tokens internos (SCORE_KILLED_GAME, etc.) pra pt-BR.
            # Fallback NÃO usa operator_instruction pra não duplicar com "Comando: ...".
            reason = _translate_reason(decision.blocked_reason) or "tese invalidada"
            lines.append(f"🔴 URGENT | SAIR DO OVER")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"Motivo: {reason}")
            lines.append(f"Comando: FECHAR POSIÇÃO AGORA.")
            return "\n".join(lines)

        if action == "LOCK_PROFIT":
            target_line = decision.target_over_line or ms.target_over_line or 2.5
            lines.append(f"💰 LOCK PROFIT — OVER")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"Linha: Over {target_line}")
            lines.append(f"Comando: TRAVAR LUCRO / ENCERRAR POSIÇÃO.")
            lines.append(f"Motivo: mercado já bateu.")
            return "\n".join(lines)

        # ─── 23.9 Watch e Manual Review ───────────────────────
        if action == "WATCH_BACK_LATE":
            team = dom_name or ms.home
            lines.append(f"👀 WATCH BACK — {team}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"CC {dom_bc}x{opp_bc} | xGOT {dom_xgot:.2f}x{opp_xgot:.2f}")
            lines.append(f"Comando: NÃO ENTRAR AINDA.")
            lines.append(f"Motivo: sinal existe, mas falta confirmação.")
            return "\n".join(lines)

        if action == "WATCH_OVER":
            total_bc = d.total_bc if d else (ms.home_bc + ms.away_bc)
            lines.append(f"👀 WATCH OVER")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"CC {ms.home_bc}x{ms.away_bc} | Total {total_bc}")
            lines.append(f"Comando: NÃO ENTRAR AINDA.")
            lines.append(f"Motivo: jogo aproxima perfil Over, mas falta confirmação.")
            return "\n".join(lines)

        if action == "MANUAL_REVIEW":
            profile = decision.game_profile or "MIXED"
            reason = decision.blocked_reason or "cenário misto ou dados insuficientes"
            lines.append(f"⚠️ ACTION | MANUAL REVIEW")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"Perfil: {profile}")
            lines.append(f"Motivo: {reason}")
            lines.append(f"Comando: DECISÃO MANUAL. NÃO ENTRAR AUTOMÁTICO.")
            return "\n".join(lines)

        # ─── 23.10 Bloqueio ───────────────────────────────────
        if action == "BLOCKED":
            reason = decision.blocked_reason or "condição de bloqueio ativa"
            lines.append(f"⛔ BLOQUEADO")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Min {ms.minute} | Placar {score}")
            lines.append(f"Motivo: {reason}")
            lines.append(f"Comando: NÃO ENTRAR.")
            return "\n".join(lines)

        # ─── 23.11 Sinal Expirado ─────────────────────────────
        if action == "SIGNAL_EXPIRED":
            last_signal = ms.last_signal_action or "—"
            valid_until = decision.signal_valid_until or 0
            lines.append(f"⚫ SINAL EXPIRADO")
            lines.append(f"Jogo: {ms.home} x {ms.away}")
            lines.append(f"Sinal: {last_signal}")
            lines.append(f"Validade era até min {valid_until} | Min atual: {ms.minute}")
            lines.append(f"Comando: NÃO ENTRAR ATRASADO.")
            lines.append(f"Motivo: janela operacional passou.")
            return "\n".join(lines)

        # ─── Fallback (NO_ACTION, COOLDOWN, etc.) ─────────────
        lines.append(f"ℹ️ {action}")
        lines.append(f"Jogo: {ms.home} x {ms.away}")
        lines.append(f"Min {ms.minute} | Placar {score}")
        if decision.blocked_reason:
            lines.append(f"Motivo: {decision.blocked_reason}")
        if decision.operator_instruction:
            lines.append(f"Comando: {decision.operator_instruction}")
        return "\n".join(lines)

    def send_decision(self, decision: Decision, ms: MatchState,
                      d: DerivedVars) -> SendResult:
        """
        Send a decision notification to Telegram.

        Returns SendResult(sent: bool, reason: str). Truthy when delivered.
        Backwards-compatible: `if tg.send_decision(...):` still works.

        Fluxo:
          0. Bloqueio absoluto MANUAL_REVIEW (defense-in-depth)
          1. check_stale_match() → detecta jogo stale / sem evolução
          2. should_send() → filtro por tipo de action + contexto
          3. check_anti_spam() → dedup match+action+reason
          4. format_message() → template Seção 23
          5. _send_raw() → HTTP POST
        """
        action = decision.recommended_action

        # 0. PROTEÇÃO ABSOLUTA — MANUAL_REVIEW NUNCA envia Telegram.
        #    Defense-in-depth: live_daemon.py também bloqueia, mas se
        #    qualquer chamador esquecer o guard, este short-circuit garante.
        if action == "MANUAL_REVIEW":
            self.messages_skipped += 1
            return SendResult(False, "MANUAL_REVIEW_LOG_ONLY")

        if not self.is_ready():
            return SendResult(False, "NOT_READY")

        # 1. Stale / sem evolução → silêncio
        stale_result = self.check_stale_match(ms, decision)
        if stale_result:
            self.messages_skipped += 1
            return SendResult(False, stale_result)

        # 2. Filtro de action type + contexto
        if not self.should_send(decision, ms):
            self.messages_skipped += 1
            if action in NEVER_SEND:
                return SendResult(False, "FILTERED_NEVER_SEND")
            if action == "BLOCKED":
                return SendResult(False, "FILTERED_BLOCKED_SILENT")
            if action == "SIGNAL_EXPIRED":
                return SendResult(False, "FILTERED_SIGNAL_EXPIRED")
            return SendResult(False, "FILTERED_UNKNOWN_ACTION")

        # 3. Anti-spam (5 min geral, 30 min MANUAL_REVIEW) — chave estável
        blocked_reason = decision.blocked_reason or ""
        effective_action = self.check_anti_spam(
            ms.match_id, action, ms.minute, blocked_reason, ms=ms
        )

        # SPAM_FILTERED → silêncio total (nem SINAL MANTIDO)
        if effective_action == "SPAM_FILTERED":
            self.messages_skipped += 1
            return SendResult(False, "SPAM_FILTERED")

        is_maintained = (effective_action == "SIGNAL_MAINTAINED")

        # 4. Format e send
        text = self.format_message(decision, ms, d, is_maintained)
        success = self._send_raw(text)

        if success:
            self.messages_sent += 1
            return SendResult(True, "SENT")
        self.errors += 1
        return SendResult(False, "HTTP_ERROR")

    def send_test(self) -> bool:
        """Send a test message to verify Telegram connection."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        text = (
            f"{self.simulation_tag}\n"
            f"\n"
            f"✅ Teste de conexão Telegram — Motor V1.2\n"
            f"Timestamp: {now}\n"
            f"\n"
            f"Bot conectado e pronto para notificações."
        )
        return self._send_raw(text)

    def send_text(self, text: str) -> bool:
        """Public adapter para envio de texto plano (alerts operacionais como
        Coverage Guard). Não passa por should_send / anti-spam — uso restrito a
        alertas críticos do daemon, NÃO para decisões da Regra 3.1.2.0."""
        if not self.is_ready():
            return False
        return self._send_raw(text)

    def send_document(self, file_path, caption: str = "") -> bool:
        """Envia um arquivo (PDF, etc.) como documento via Telegram Bot API.

        Usa multipart/form-data (sem dependências externas).
        Retorna True se entregue.
        """
        if not self.is_ready():
            return False
        from pathlib import Path as _P
        p = _P(str(file_path))
        if not p.exists():
            print(f"  ⚠️  Telegram send_document: arquivo não existe: {p}")
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendDocument"
        # Multipart manual
        import uuid, mimetypes
        boundary = f"----coworkboundary{uuid.uuid4().hex}"
        ctype, _ = mimetypes.guess_type(str(p))
        ctype = ctype or "application/octet-stream"
        with open(p, "rb") as f:
            file_bytes = f.read()

        def _field(name, value):
            return (
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"{name}\"\r\n\r\n"
                f"{value}\r\n"
            ).encode("utf-8")

        body = b""
        body += _field("chat_id", self.chat_id)
        if caption:
            body += _field("caption", caption[:1000])
        # arquivo
        body += (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"document\"; "
            f"filename=\"{p.name}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode("utf-8")
        body += file_bytes + b"\r\n"
        body += f"--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return bool(result.get("ok", False))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            print(f"  ⚠️  Telegram doc HTTP {e.code}: {err_body[:200]}")
            return False
        except Exception as e:
            print(f"  ⚠️  Telegram doc erro: {e}")
            return False

    def _send_raw(self, text: str) -> bool:
        """Send raw text via Telegram Bot API using urllib (no dependencies)."""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "",  # plain text
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("ok", False)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"  ⚠️  Telegram HTTP {e.code}: {body[:200]}")
            return False
        except urllib.error.URLError as e:
            print(f"  ⚠️  Telegram erro de rede: {e.reason}")
            return False
        except Exception as e:
            print(f"  ⚠️  Telegram erro: {e}")
            return False


# === CLI: python3 -m src.telegram_client --test ===
def _cli_main():
    import argparse
    from .decision_engine import load_config

    parser = argparse.ArgumentParser(
        description="Telegram Client — Motor V1.2"
    )
    parser.add_argument("--test", action="store_true", help="Enviar mensagem de teste")
    parser.add_argument(
        "--config", "-c", default=None,
        help="Caminho do config.yaml"
    )
    args = parser.parse_args()

    cfg = load_config(args.config)

    # Force enabled for test
    cfg.setdefault("telegram", {})
    cfg["telegram"]["enabled"] = True

    client = TelegramClient(cfg)

    print(f"\n  Status: {client.get_status()}")

    if not client.bot_token:
        print("\n  ❌ TELEGRAM_BOT_TOKEN não definido.")
        print("  Execute: export TELEGRAM_BOT_TOKEN='seu_token_aqui'")
        return

    if not client.chat_id:
        print("\n  ❌ TELEGRAM_CHAT_ID não definido.")
        print("  Execute: export TELEGRAM_CHAT_ID='seu_chat_id_aqui'")
        return

    if args.test:
        print("  Enviando mensagem de teste...")
        ok = client.send_test()
        if ok:
            print("  ✅ Mensagem enviada com sucesso!")
        else:
            print("  ❌ Falha ao enviar. Verifique token e chat_id.")
    else:
        print("  Use --test para enviar mensagem de teste.")


if __name__ == "__main__":
    _cli_main()
