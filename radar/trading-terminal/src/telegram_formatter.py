"""
Telegram notification metadata — Section 23 of V1.2.
Enriches Decision with severity, priority, operator_instruction, etc.
"""
from .models import Decision


# === Severity mapping ===
SEVERITY_MAP = {
    "ENTER_BACK_T1_EARLY": "ACTION",
    "ENTER_BACK_T1_MAIN": "ACTION",
    "ENTER_BACK_T1_LATE": "ACTION",
    "ENTER_BACK_T2": "ACTION",
    "ENTER_BACK_SMALL": "ACTION",
    "ENTER_OVER_PREMIUM": "ACTION",
    "ENTER_OVER_BILATERAL_FORTE": "ACTION",
    "ENTER_OVER_SMALL": "ACTION",
    "ENTER_OVER_GOL_LIMITE": "ACTION",
    "EXIT_BACK": "URGENT",
    "EXIT_OVER": "URGENT",
    "LOCK_PROFIT": "URGENT",
    "REDUCE_BACK": "ACTION",
    "REDUCE_OVER": "ACTION",
    "YELLOW_ALERT_BACK": "WATCH",
    "YELLOW_ALERT_OVER": "WATCH",
    "HOLD_BACK": "INFO",
    "HOLD_OVER": "INFO",
    "HOLD_BACK_WITH_CAUTION": "INFO",
    "HOLD_OVER_WITH_CAUTION": "INFO",
    "WATCH_BACK_LATE": "WATCH",
    "MANUAL_REVIEW": "ACTION",
    "BLOCKED": "BLOCKED",
    "SIGNAL_EXPIRED": "EXPIRED",
    "SIGNAL_MAINTAINED": "INFO",
    "COOLDOWN": "INFO",
    "NO_ACTION": "INFO",
}

# === Operator instruction mapping ===
INSTRUCTION_MAP = {
    "ENTER_BACK_T1_EARLY": "ENTRAR AGORA.",
    "ENTER_BACK_T1_MAIN": "ENTRAR AGORA.",
    "ENTER_BACK_T1_LATE": "ENTRAR COM CAUTELA.",
    "ENTER_BACK_T2": "ENTRAR COM CAUTELA.",
    "ENTER_BACK_SMALL": "ENTRADA REDUZIDA OU REVISÃO RÁPIDA.",
    "ENTER_OVER_PREMIUM": "ENTRAR OVER 2.5 AGORA.",
    "ENTER_OVER_BILATERAL_FORTE": "ENTRAR OVER 2.5 / AVALIAR BTS.",
    "ENTER_OVER_SMALL": "ENTRADA REDUZIDA.",
    "ENTER_OVER_GOL_LIMITE": "ENTRAR RÁPIDO OU IGNORAR SE PREÇO CORRIGIU.",
    "EXIT_BACK": "FECHAR POSIÇÃO AGORA.",
    "EXIT_OVER": "FECHAR POSIÇÃO AGORA.",
    "LOCK_PROFIT": "TRAVAR LUCRO / ENCERRAR POSIÇÃO.",
    "REDUCE_BACK": "REDUZIR EXPOSIÇÃO.",
    "REDUCE_OVER": "REDUZIR EXPOSIÇÃO.",
    "YELLOW_ALERT_BACK": "NÃO AUMENTAR. MONITORAR SAÍDA.",
    "YELLOW_ALERT_OVER": "NÃO AUMENTAR. MONITORAR REDUÇÃO.",
    "HOLD_BACK": "MANTER POSIÇÃO.",
    "HOLD_OVER": "MANTER POSIÇÃO.",
    "HOLD_BACK_WITH_CAUTION": "MANTER POSIÇÃO.",
    "HOLD_OVER_WITH_CAUTION": "MANTER POSIÇÃO.",
    "WATCH_BACK_LATE": "NÃO ENTRAR AINDA.",
    "MANUAL_REVIEW": "DECISÃO MANUAL. NÃO ENTRAR AUTOMÁTICO.",
    "BLOCKED": "NÃO ENTRAR.",
    "SIGNAL_EXPIRED": "NÃO ENTRAR ATRASADO.",
    "SIGNAL_MAINTAINED": "MESMO SINAL. NÃO DUPLICAR ENTRADA.",
    "COOLDOWN": "AGUARDAR COOLDOWN.",
    "NO_ACTION": "",
}

# === Action required ===
ACTION_REQUIRED = {
    "ENTER_BACK_T1_EARLY": True,
    "ENTER_BACK_T1_MAIN": True,
    "ENTER_BACK_T1_LATE": True,
    "ENTER_BACK_T2": True,
    "ENTER_BACK_SMALL": True,
    "ENTER_OVER_PREMIUM": True,
    "ENTER_OVER_BILATERAL_FORTE": True,
    "ENTER_OVER_SMALL": True,
    "ENTER_OVER_GOL_LIMITE": True,
    "EXIT_BACK": True,
    "EXIT_OVER": True,
    "LOCK_PROFIT": True,
    "REDUCE_BACK": True,
    "REDUCE_OVER": True,
    "YELLOW_ALERT_BACK": True,
    "YELLOW_ALERT_OVER": True,
    "MANUAL_REVIEW": True,
    "SIGNAL_EXPIRED": True,
    "HOLD_BACK": False,
    "HOLD_OVER": False,
    "HOLD_BACK_WITH_CAUTION": False,
    "HOLD_OVER_WITH_CAUTION": False,
    "WATCH_BACK_LATE": False,
    "BLOCKED": False,
    "SIGNAL_MAINTAINED": False,
    "COOLDOWN": False,
    "NO_ACTION": False,
}

# === Priority ===
PRIORITY_MAP = {
    "ENTER_BACK_T1_EARLY": "HIGH",
    "ENTER_BACK_T1_MAIN": "HIGH",
    "ENTER_BACK_T1_LATE": "HIGH",
    "ENTER_BACK_T2": "HIGH",
    "ENTER_BACK_SMALL": "HIGH",
    "ENTER_OVER_PREMIUM": "HIGH",
    "ENTER_OVER_BILATERAL_FORTE": "HIGH",
    "ENTER_OVER_SMALL": "HIGH",
    "ENTER_OVER_GOL_LIMITE": "HIGH",
    "EXIT_BACK": "CRITICAL",
    "EXIT_OVER": "CRITICAL",
    "LOCK_PROFIT": "CRITICAL",
    "REDUCE_BACK": "HIGH",
    "REDUCE_OVER": "HIGH",
    "MANUAL_REVIEW": "HIGH",
    "SIGNAL_EXPIRED": "HIGH",
    "YELLOW_ALERT_BACK": "NORMAL",
    "YELLOW_ALERT_OVER": "NORMAL",
    "BLOCKED": "NORMAL",
    "WATCH_BACK_LATE": "LOW",
    "HOLD_BACK": "LOW",
    "HOLD_OVER": "LOW",
    "HOLD_BACK_WITH_CAUTION": "LOW",
    "HOLD_OVER_WITH_CAUTION": "LOW",
    "SIGNAL_MAINTAINED": "LOW",
    "COOLDOWN": "LOW",
    "NO_ACTION": "LOW",
}

# === Severity icons ===
SEVERITY_ICON = {
    "INFO": "\U0001f535",       # 🔵
    "WATCH": "\U0001f440",      # 👀
    "ACTION": "\U0001f7e2",     # 🟢
    "URGENT": "\U0001f534",     # 🔴
    "BLOCKED": "⛔",        # ⛔
    "EXPIRED": "⚫",        # ⚫
}

# === Tradução de tokens internos pra exibição em pt-BR ===
# Tokens são mantidos em inglês internamente (compat com testes/filtros do
# telegram_client), mas exibidos em português na mensagem.
REASON_PT_MAP = {
    "RED_CARD": "Cartão vermelho contra o time apostado",
    "SCORE_KILLED_GAME": "Diferença de placar ≥ 3 — jogo decidido",
    "BILATERALITY_LOST": "Bilateralidade perdida (um lado parou de criar) — avaliar transição para Back",
    "NO_NEW_ENTRY_AFTER_83": "Minuto > 83 — sem novas entradas",
    "NO_NEW_OVER_AFTER_75": "Minuto > 75 — Over normal bloqueado",
    "DATA_DELAY": "Dados atrasados — bloqueio de segurança",
    "DATA_INVALID": "Dados inválidos — bloqueio de segurança",
    "MIN_BC_ZERO_BLOCKS_OVER": "Um lado sem big chance — bloqueia Over",
    "DRAW_BLOCKS_GOL_LIMITE": "Empate invalida Over Gol Limite",
    "LAST_BC_TOO_OLD": "Última big chance muito antiga",
    "SIGNAL_TURNED_AGAINST": "Sinal virou contra — adversário ganhou força",
    "STALE_MATCH": "Dado suspeito (jogo em min ≤ 2 com placar repetido)",
    "NO_DATA_EVOLUTION": "Sem evolução de dados desde o scan anterior",
    "NO_NEW_BC_SINCE_OVER_EXIT": "Sem nova big chance desde o último exit Over — anti-reentrada",
}


def _translate_reason(reason: str) -> str:
    """Traduz tokens internos pra pt-BR. Strings já em pt-BR passam direto."""
    if not reason:
        return ""
    return REASON_PT_MAP.get(reason, reason)


def enrich_telegram_metadata(decision: Decision):
    """Fill in Telegram protocol fields based on recommended_action."""
    action = decision.recommended_action

    decision.message_severity = SEVERITY_MAP.get(action, "INFO")
    decision.operator_instruction = INSTRUCTION_MAP.get(action, "")
    decision.operator_action_required = ACTION_REQUIRED.get(action, False)
    decision.telegram_priority = PRIORITY_MAP.get(action, "LOW")

    # Over Gol Limite gets fire icon
    if action == "ENTER_OVER_GOL_LIMITE":
        decision.message_severity = "ACTION"  # but icon overridden below


def format_telegram_message(decision: Decision, ms=None, d=None) -> str:
    """Format a complete Telegram message string (Section 23)."""
    action = decision.recommended_action
    icon = SEVERITY_ICON.get(decision.message_severity, "")

    # Special icon for Gol Limite
    if action == "ENTER_OVER_GOL_LIMITE":
        icon = "\U0001f525"  # 🔥

    lines = []

    # Header
    sev = decision.message_severity
    if decision.market_target:
        lines.append(f"{icon} {sev} | {action} — {decision.market_target}")
    else:
        lines.append(f"{icon} {sev} | {action}")

    # Game info
    if ms:
        lines.append(f"Jogo: {ms.home} x {ms.away}")
        lines.append(f"Min {ms.minute} | Placar {ms.home_score}-{ms.away_score}")

    # Signal validity
    if decision.signal_valid_until > 0:
        lines.append(f"Válido até: min {decision.signal_valid_until}")

    # Data (if available)
    if d:
        lines.append(f"CC {ms.home_bc}x{ms.away_bc} | xGOT {ms.home_xgot:.2f}x{ms.away_xgot:.2f}")
        if decision.game_profile:
            lines.append(f"Perfil: {decision.game_profile} | Tier: {decision.confidence_tier}")

    # Alternative market (Gol Limite)
    if decision.alternative_market:
        lines.append(f"Alt: {decision.alternative_market}")

    lines.append("")

    # Command
    if decision.operator_instruction:
        lines.append(f"Comando: {decision.operator_instruction}")

    # Blocked reason — traduzido pra pt-BR quando for token interno
    if decision.blocked_reason:
        lines.append(f"Motivo: {_translate_reason(decision.blocked_reason)}")

    return "\n".join(lines)
