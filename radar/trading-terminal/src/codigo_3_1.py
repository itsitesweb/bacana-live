"""
Código 3:1 — REGRA 3.1.2.0 (Placar Atrasado, Rate Qualificado, Níveis Operacionais)

Evolução da Regra 3:1 original. Mantém a tese central (1 gol esperado a cada 3 CC),
mas introduz NÍVEIS operacionais validados pelos 1603 jogos da base histórica:

  ┌─────────────┬──────────────────────────────────────────────────────────┐
  │ NÍVEL       │ CONDIÇÃO                                                  │
  ├─────────────┼──────────────────────────────────────────────────────────┤
  │ OVER:       │                                                           │
  │  WATCH      │ CC≥3   + rate≤15 + goals<expected                         │
  │  FORTE      │ CC≥4   + rate≤12 + goals<expected                         │
  │  PREMIUM    │ CC≥6   + rate≤12 + goals<expected                         │
  │  PREMIUM+xG │ CC≥6   + rate≤12 + goals<expected + xG≥2.5                │
  │  BILATERAL  │ home_cc≥3 + away_cc≥3 + total≥6 + goals<expected          │
  │                                                                           │
  │ BACK:       │                                                           │
  │  WATCH      │ dom_cc≥3 + opp≤1 + diff≥3 + dom_goals<expected            │
  │  FORTE      │ dom_cc≥4 + opp≤1 + diff≥4 + dom_goals<expected            │
  │  PREMIUM    │ dom_cc≥6 + opp=0 + diff≥6 + dom_goals<expected            │
  │ (todos BACK bloqueados se dominante já vencendo por 2+)                  │
  └─────────────┴──────────────────────────────────────────────────────────┘

PRIORIDADE (do mais forte ao mais fraco) — só 1 alerta por jogo por ciclo:
  1. PREMIUM OVER BILATERAL PESADO
  2. PREMIUM OVER CC+xG CONFIRMADOS
  3. PREMIUM OVER
  4. PREMIUM BACK
  5. FORTE OVER
  6. FORTE BACK
  7. WATCH OVER
  8. WATCH BACK

ANTI-SPAM POR BUCKET (mantém Cód 3:1 original + estende):
  bucket_over     = floor(total_cc / 3)        — pra OVER (main, bilateral, premium+xG)
  bucket_back     = floor(dominant_cc / 3)     — pra BACK
  Só dispara se bucket atual > último bucket do mesmo tipo já alertado.

NÃO MEXE: Supervisor, Radar13, Motor V1.2, Telegram estrutural, Discovery, Watchlist.
Dossiê: docs/current/Codigo_3_1_Matriz_das_Chances_Claras.md (será atualizado pra v2)
"""
from typing import Optional


# ──────────────────────────────────────────────────────────────────────
# Tipos de alerta (em ordem de prioridade — maior=mais forte)
# ──────────────────────────────────────────────────────────────────────

ALERT_OVER_BILATERAL_PREMIUM = "over_bilateral_premium"   # prio 1
ALERT_OVER_PREMIUM_XG        = "over_premium_xg"          # prio 2
ALERT_OVER_PREMIUM           = "over_premium"             # prio 3
ALERT_BACK_PREMIUM           = "back_premium"             # prio 4
ALERT_OVER_FORTE             = "over_forte"               # prio 5
ALERT_BACK_FORTE             = "back_forte"               # prio 6
ALERT_OVER_WATCH             = "over_watch"               # prio 7
ALERT_BACK_WATCH             = "back_watch"               # prio 8

# Aliases pra compatibilidade com código antigo (testes que usavam "main"/"unilateral")
ALERT_TYPE_MAIN = ALERT_OVER_WATCH        # mapeamento legado
ALERT_TYPE_UNILATERAL = ALERT_BACK_WATCH  # mapeamento legado

PRIORITY = [
    ALERT_OVER_BILATERAL_PREMIUM,
    ALERT_OVER_PREMIUM_XG,
    ALERT_OVER_PREMIUM,
    ALERT_BACK_PREMIUM,
    ALERT_OVER_FORTE,
    ALERT_BACK_FORTE,
    ALERT_OVER_WATCH,
    ALERT_BACK_WATCH,
]

# ──────────────────────────────────────────────────────────────────────
# Política de Telegram (ajuste pós-Regra 3.1.2.0):
#   WATCH = apenas RADAR → terminal + log JSONL, SEM Telegram.
#   FORTE/PREMIUM = ALERTA OPERACIONAL → Telegram + anti-spam por bucket.
# WATCH NÃO consome bucket — se um jogo passou por WATCH no bucket 1 e
# depois evoluiu para FORTE/PREMIUM no mesmo bucket, o FORTE/PREMIUM
# ainda dispara Telegram normalmente.
# ──────────────────────────────────────────────────────────────────────
WATCH_ONLY_ALERTS = frozenset({
    ALERT_OVER_WATCH,
    ALERT_BACK_WATCH,
})


def is_watch_only(alert_type) -> bool:
    """True se o alert_type é WATCH (radar apenas, sem Telegram)."""
    return alert_type in WATCH_ONLY_ALERTS


def is_telegram_eligible(alert_type) -> bool:
    """True se o alert_type deve disparar Telegram (FORTE/PREMIUM/BILATERAL)."""
    if not alert_type:
        return False
    return alert_type not in WATCH_ONLY_ALERTS

# Razões de filtro
FILTER_INVALID_MINUTE = "invalid_minute"
FILTER_CC_LT_3 = "CC<3"
FILTER_RATE_GT_15 = "rate>15"
FILTER_GOALS_GE_EXPECTED = "goals>=expected"
FILTER_BUCKET_ALREADY_SENT = "bucket_already_sent"
FILTER_DATA_INVALID = "data_invalid"
FILTER_BACK_DOMINANT_LEADING = "back_dominant_leading"
FILTER_NO_PATTERN_MATCHED = "no_pattern_matched"


# ──────────────────────────────────────────────────────────────────────
# Núcleo da regra
# ──────────────────────────────────────────────────────────────────────


def evaluate_codigo_3_1(match_state, previous_alert_state: dict) -> dict:
    """Avalia estado do jogo contra a Regra 3.1.2.0.

    Args:
        match_state: instância de MatchState (do src.models)
        previous_alert_state: dict com chaves opcionais 'main_bucket' (OVER) e
            'unilateral_bucket' (BACK) — buckets mais recentes já alertados.

    Returns:
        dict com:
            alert_type     : um dos ALERT_* (priorizado) ou None
            should_alert   : bool
            reason         : motivo string (ex: "OVER_PREMIUM_BILATERAL")
            bucket         : int (anti-spam)
            level          : "watch" | "forte" | "premium" | None
            market         : "over" | "back" | None
            telegram_message_fields : dict pronto pra formatação
    """
    ms = match_state
    home_bc = max(0, int(getattr(ms, "home_bc", 0) or 0))
    away_bc = max(0, int(getattr(ms, "away_bc", 0) or 0))
    home_score = max(0, int(getattr(ms, "home_score", 0) or 0))
    away_score = max(0, int(getattr(ms, "away_score", 0) or 0))
    minute = max(0, int(getattr(ms, "minute", 0) or 0))
    data_is_valid = bool(getattr(ms, "data_is_valid", True))
    scan_delay = int(getattr(ms, "scan_delay_seconds", 0) or 0)

    # xG total (opcional — se ausente, regras PREMIUM+xG não disparam mas outras sim)
    home_xg = float(getattr(ms, "home_xg", 0) or 0)
    away_xg = float(getattr(ms, "away_xg", 0) or 0)
    total_xg = home_xg + away_xg

    # Bloqueios universais
    if not data_is_valid or scan_delay > 180:
        return _no_alert(FILTER_DATA_INVALID)
    if minute <= 0:
        return _no_alert(FILTER_INVALID_MINUTE)

    total_cc = home_bc + away_bc
    total_goals = home_score + away_score
    cc_rate = (minute / total_cc) if total_cc > 0 else 999.0
    expected_over = total_cc // 3
    placar_abaixo_producao = total_goals < expected_over

    # Time dominante (pra BACK e xG do dominante)
    if home_bc > away_bc:
        dominant_team = "home"
        dominant_name = getattr(ms, "home", "?") or "?"
        dominant_score = home_score
        opp_score = away_score
        dom_cc = home_bc
        opp_cc = away_bc
    elif away_bc > home_bc:
        dominant_team = "away"
        dominant_name = getattr(ms, "away", "?") or "?"
        dominant_score = away_score
        opp_score = home_score
        dom_cc = away_bc
        opp_cc = home_bc
    else:
        dominant_team = None
        dominant_name = ""
        dominant_score = 0
        opp_score = 0
        dom_cc = max_team_cc_fallback = 0
        opp_cc = 0

    cc_diff = dom_cc - opp_cc
    expected_back = dom_cc // 3 if dom_cc >= 3 else 0
    back_placar_abaixo = (dominant_score < expected_back) if expected_back else False
    dom_lead = dominant_score - opp_score  # >=2 bloqueia BACK

    last_over = int((previous_alert_state or {}).get("main_bucket", 0) or 0)
    last_back = int((previous_alert_state or {}).get("unilateral_bucket", 0) or 0)

    # ─── Avalia TODOS os padrões e armazena candidatos ──────────────
    candidates = []  # lista de dicts decision
    bucket_blocked = False  # True se algum padrão bateu mas bucket já alertado

    # Campos comuns pra Telegram
    common = {
        "home": getattr(ms, "home", "?") or "?",
        "away": getattr(ms, "away", "?") or "?",
        "home_bc": home_bc,
        "away_bc": away_bc,
        "home_score": home_score,
        "away_score": away_score,
        "minute": minute,
        "total_cc": total_cc,
        "total_goals": total_goals,
        "cc_rate": cc_rate,
        "expected_goals_by_cc": expected_over,
        "total_xg": round(total_xg, 2) if total_xg > 0 else None,
    }
    common_back = {
        **common,
        "dominant_team": dominant_team,
        "dominant_name": dominant_name,
        "dominant_score": dominant_score,
        "dom_cc": dom_cc,
        "opp_cc": opp_cc,
        "cc_diff": cc_diff,
        "expected_dominant_goals_by_cc": expected_back,
    }

    # ─── OVER BILATERAL PESADO (prio 1) ──────────────────────────────
    if (home_bc >= 3 and away_bc >= 3 and total_cc >= 6
            and placar_abaixo_producao):
        bucket = expected_over
        if bucket > last_over:
            candidates.append({
                "alert_type": ALERT_OVER_BILATERAL_PREMIUM,
                "reason": "OVER_PREMIUM_BILATERAL",
                "level": "premium",
                "market": "over",
                "bucket": bucket,
                "telegram_message_fields": common,
            })
        else:
            bucket_blocked = True

    # ─── OVER PREMIUM + xG (prio 2) ──────────────────────────────────
    if (total_cc >= 6 and cc_rate <= 12 and placar_abaixo_producao
            and total_xg >= 2.5):
        bucket = expected_over
        if bucket > last_over:
            candidates.append({
                "alert_type": ALERT_OVER_PREMIUM_XG,
                "reason": "OVER_PREMIUM_CC_XG",
                "level": "premium",
                "market": "over",
                "bucket": bucket,
                "telegram_message_fields": common,
            })
        else:
            bucket_blocked = True

    # ─── OVER PREMIUM (prio 3) ────────────────────────────────────────
    if (total_cc >= 6 and cc_rate <= 12 and placar_abaixo_producao):
        bucket = expected_over
        if bucket > last_over:
            candidates.append({
                "alert_type": ALERT_OVER_PREMIUM,
                "reason": "OVER_PREMIUM",
                "level": "premium",
                "market": "over",
                "bucket": bucket,
                "telegram_message_fields": common,
            })
        else:
            bucket_blocked = True

    # ─── BACK PREMIUM (prio 4) ────────────────────────────────────────
    # bloqueio se dominante já vencendo por 2+
    if dominant_team and dom_lead < 2:
        if (dom_cc >= 6 and opp_cc == 0 and cc_diff >= 6
                and dominant_score < expected_back):
            bucket = expected_back
            if bucket > last_back:
                candidates.append({
                    "alert_type": ALERT_BACK_PREMIUM,
                    "reason": "BACK_PREMIUM_EXTREMO",
                    "level": "premium",
                    "market": "back",
                    "bucket": bucket,
                    "telegram_message_fields": common_back,
                })
            else:
                bucket_blocked = True

    # ─── OVER FORTE (prio 5) ──────────────────────────────────────────
    if (total_cc >= 4 and cc_rate <= 12 and placar_abaixo_producao):
        bucket = expected_over
        if bucket > last_over:
            candidates.append({
                "alert_type": ALERT_OVER_FORTE,
                "reason": "OVER_FORTE",
                "level": "forte",
                "market": "over",
                "bucket": bucket,
                "telegram_message_fields": common,
            })
        else:
            bucket_blocked = True

    # ─── BACK FORTE (prio 6) ──────────────────────────────────────────
    if dominant_team and dom_lead < 2:
        if (dom_cc >= 4 and opp_cc <= 1 and cc_diff >= 4
                and dominant_score < expected_back):
            bucket = expected_back
            if bucket > last_back:
                candidates.append({
                    "alert_type": ALERT_BACK_FORTE,
                    "reason": "BACK_FORTE",
                    "level": "forte",
                    "market": "back",
                    "bucket": bucket,
                    "telegram_message_fields": common_back,
                })
            else:
                bucket_blocked = True

    # ─── OVER WATCH (prio 7) — regra original ─────────────────────────
    if (total_cc >= 3 and cc_rate <= 15 and placar_abaixo_producao):
        bucket = expected_over
        if bucket > last_over:
            candidates.append({
                "alert_type": ALERT_OVER_WATCH,
                "reason": "OVER_WATCH",
                "level": "watch",
                "market": "over",
                "bucket": bucket,
                "telegram_message_fields": common,
            })
        else:
            bucket_blocked = True

    # ─── BACK WATCH (prio 8) ──────────────────────────────────────────
    if dominant_team and dom_lead < 2:
        if (dom_cc >= 3 and opp_cc <= 1 and cc_diff >= 3
                and dominant_score < expected_back):
            bucket = expected_back
            if bucket > last_back:
                candidates.append({
                    "alert_type": ALERT_BACK_WATCH,
                    "reason": "BACK_WATCH",
                    "level": "watch",
                    "market": "back",
                    "bucket": bucket,
                    "telegram_message_fields": common_back,
                })
            else:
                bucket_blocked = True

    # ─── PRIORIZAÇÃO ─────────────────────────────────────────────────
    if not candidates:
        # Determina razão mais informativa
        # 'bucket_already_sent' tem PRIORIDADE sobre os demais quando aplicável,
        # pois indica que houve match mas o anti-spam por bucket bloqueou.
        if bucket_blocked:
            return _no_alert(FILTER_BUCKET_ALREADY_SENT)
        if total_cc < 3:
            return _no_alert(FILTER_CC_LT_3)
        if cc_rate > 15:
            return _no_alert(FILTER_RATE_GT_15)
        if not placar_abaixo_producao:
            return _no_alert(FILTER_GOALS_GE_EXPECTED)
        if dominant_team and dom_lead >= 2:
            return _no_alert(FILTER_BACK_DOMINANT_LEADING)
        return _no_alert(FILTER_NO_PATTERN_MATCHED)

    # Ordena por prioridade (índice menor = maior prioridade)
    candidates.sort(key=lambda d: PRIORITY.index(d["alert_type"]))
    chosen = candidates[0]
    chosen["should_alert"] = True
    return chosen


def _no_alert(reason: str) -> dict:
    return {
        "alert_type": None,
        "should_alert": False,
        "reason": reason,
        "bucket": 0,
        "level": None,
        "market": None,
        "telegram_message_fields": {},
    }


# ──────────────────────────────────────────────────────────────────────
# Helpers de state (anti-spam por bucket)
# ──────────────────────────────────────────────────────────────────────


def get_previous_alert_state(state_entry: dict) -> dict:
    """Lê últimos buckets alertados a partir da entry do state.json.
    Mantém chaves antigas main_bucket/unilateral_bucket pra compat."""
    if not isinstance(state_entry, dict):
        return {"main_bucket": 0, "unilateral_bucket": 0}
    cc = state_entry.get("codigo_3_1") or {}
    return {
        "main_bucket": int(cc.get("main_bucket_last", 0) or 0),
        "unilateral_bucket": int(cc.get("unilateral_bucket_last", 0) or 0),
    }


def update_state_after_alert(state_entry: dict, decision: dict) -> None:
    """Atualiza state com o bucket que acabou de ser alertado.

    REGRA WATCH = log-only (não consome bucket):
    Se o alert_type for WATCH (over_watch ou back_watch), NÃO atualiza
    main_bucket_last/unilateral_bucket_last. Isso garante que um FORTE
    ou PREMIUM disparando depois no MESMO bucket ainda envie Telegram.
    """
    if not isinstance(state_entry, dict) or not decision:
        return
    if not decision.get("should_alert"):
        return
    # WATCH não consome bucket — apenas FORTE/PREMIUM
    if is_watch_only(decision.get("alert_type")):
        return
    cc = state_entry.setdefault("codigo_3_1", {
        "main_bucket_last": 0,
        "unilateral_bucket_last": 0,
    })
    bucket = int(decision.get("bucket", 0) or 0)
    market = decision.get("market")
    if market == "over":
        cc["main_bucket_last"] = bucket
    elif market == "back":
        cc["unilateral_bucket_last"] = bucket


# ──────────────────────────────────────────────────────────────────────
# Formatação Telegram + Display Terminal
# ──────────────────────────────────────────────────────────────────────


# Mapa alert_type → (emoji, label) — TÍTULOS OFICIAIS da Regra 3.1.2.0
# WATCH usa 📡 (radar), FORTE 🟠, PREMIUM 🟢
ALERT_DISPLAY = {
    ALERT_OVER_BILATERAL_PREMIUM: ("🟢", "PREMIUM 3.1.2 — OVER BILATERAL PESADO"),
    ALERT_OVER_PREMIUM_XG:        ("🟢", "PREMIUM 3.1.2 — CC + xG CONFIRMADOS"),
    ALERT_OVER_PREMIUM:           ("🟢", "PREMIUM 3.1.2 — GOL MUITO DEVENDO"),
    ALERT_BACK_PREMIUM:           ("🟢", "PREMIUM 3.1.2 — BACK DOMINANTE EXTREMO"),
    ALERT_OVER_FORTE:             ("🟠", "FORTE 3.1.2 — GOL DEVENDO"),
    ALERT_BACK_FORTE:             ("🟠", "FORTE 3.1.2 — BACK DOMINANTE"),
    ALERT_OVER_WATCH:             ("📡", "WATCH 3.1.2 — RADAR DE GOL"),
    ALERT_BACK_WATCH:             ("📡", "WATCH 3.1.2 — RADAR DE BACK DOMINANTE"),
}

# Motivo + Leitura por alert_type — textos oficiais.
# WATCH usa linguagem de RADAR (não-entrada automática).
# FORTE/PREMIUM/BILATERAL usam linguagem operacional.
MESSAGE_TEMPLATES = {
    ALERT_OVER_WATCH: {
        "motivo": "Produção suficiente para gol, mas o placar ainda não pagou.",
        "leitura": ("Radar ativo. Não é entrada automática. "
                    "Aguardar nova CC ou evolução para FORTE/PREMIUM."),
    },
    ALERT_OVER_FORTE: {
        "motivo": "Produção ofensiva forte, rate qualificado e placar abaixo da produção.",
        "leitura": "Sinal operacional. Avaliar entrada em gol/Over conforme odd e contexto.",
    },
    ALERT_OVER_PREMIUM: {
        "motivo": "Volume alto de chances claras e placar claramente atrasado.",
        "leitura": "Sinal premium de gol atrasado. Prioridade alta para análise de entrada.",
    },
    ALERT_OVER_PREMIUM_XG: {
        "motivo": "Chances claras e xG confirmam alta produção ofensiva com placar abaixo.",
        "leitura": "Sinal premium confirmado por duas métricas. Prioridade máxima.",
    },
    ALERT_OVER_BILATERAL_PREMIUM: {
        "motivo": ("Os dois times já criaram 3+ chances claras. "
                   "Jogo aberto dos dois lados."),
        "leitura": ("Padrão forte para Over/BTTS. "
                    "Não é sinal de Back; é sinal de jogo aberto."),
    },
    ALERT_BACK_WATCH: {
        "motivo": ("Um time começou a abrir vantagem em chances claras, "
                   "mas o placar ainda não refletiu."),
        "leitura": ("Radar ativo. Não é entrada automática. "
                    "Aguardar confirmação de domínio para FORTE/PREMIUM."),
    },
    ALERT_BACK_FORTE: {
        "motivo": ("Dominante tem vantagem clara em chances, "
                   "mas o placar ainda não pagou essa produção."),
        "leitura": ("Sinal operacional para Back do dominante. "
                    "Confirmar pressão atual antes da entrada."),
    },
    ALERT_BACK_PREMIUM: {
        "motivo": ("Domínio extremo em chances claras, "
                   "adversário sem produção relevante e placar contra a lógica do jogo."),
        "leitura": "Sinal premium para reação do dominante. Prioridade alta.",
    },
}


def format_telegram_message(decision: dict) -> str:
    """Roteia pro formatter por mercado (over | back)."""
    if not decision or not decision.get("should_alert"):
        return ""
    market = decision.get("market")
    if market == "back":
        return _format_back(decision)
    return _format_over(decision)


def _format_over(decision: dict) -> str:
    """Formata mensagem OVER (WATCH/FORTE/PREMIUM/PREMIUM_XG/BILATERAL).

    Layout oficial Regra 3.1.2.0:
        {emoji} {LABEL}
        {home} {placar} {away}
        Min {min} | CC: {h}x{a} = {tot} | Rate: {rate}
        [xG total: {xg}]    ← apenas em PREMIUM xG
        Esperado por CC: {exp} | Gols reais: {gols}
        Motivo:
        {motivo}
        Leitura:
        {leitura}
    """
    f = decision["telegram_message_fields"]
    at = decision["alert_type"]
    emoji, label = ALERT_DISPLAY.get(at, ("🟢", "ALERTA 3.1.2"))
    tpl = MESSAGE_TEMPLATES.get(at, {"motivo": "", "leitura": ""})

    # Linha de xG só em PREMIUM xG
    xg_line = ""
    if at == ALERT_OVER_PREMIUM_XG and f.get("total_xg") is not None:
        xg_line = f"xG total: {f['total_xg']}\n"

    return (
        f"{emoji} {label}\n"
        f"{f['home']} {f['home_score']}-{f['away_score']} {f['away']}\n"
        f"Min {f['minute']} | CC: {f['home_bc']}x{f['away_bc']} = {f['total_cc']} | "
        f"Rate: {f['cc_rate']:.1f}\n"
        f"{xg_line}"
        f"Esperado por CC: {f['expected_goals_by_cc']} | Gols reais: {f['total_goals']}\n"
        f"\n"
        f"Motivo:\n"
        f"{tpl['motivo']}\n"
        f"\n"
        f"Leitura:\n"
        f"{tpl['leitura']}"
    )


def _format_back(decision: dict) -> str:
    """Formata mensagem BACK (WATCH/FORTE/PREMIUM).

    Layout oficial Regra 3.1.2.0:
        {emoji} {LABEL}
        {home} {placar} {away}
        Min {min} | Dominante: {nome}
        CC: {h}x{a} | Diff CC: {diff}
        Esperado dominante: {exp} | Gols dominante: {gols_dom}
        Motivo:
        {motivo}
        Leitura:
        {leitura}
    """
    f = decision["telegram_message_fields"]
    at = decision["alert_type"]
    emoji, label = ALERT_DISPLAY.get(at, ("🟠", "BACK 3.1.2"))
    tpl = MESSAGE_TEMPLATES.get(at, {"motivo": "", "leitura": ""})

    return (
        f"{emoji} {label}\n"
        f"{f['home']} {f['home_score']}-{f['away_score']} {f['away']}\n"
        f"Min {f['minute']} | Dominante: {f['dominant_name']}\n"
        f"CC: {f['home_bc']}x{f['away_bc']} | Diff CC: {f['cc_diff']}\n"
        f"Esperado dominante: {f['expected_dominant_goals_by_cc']} | "
        f"Gols dominante: {f['dominant_score']}\n"
        f"\n"
        f"Motivo:\n"
        f"{tpl['motivo']}\n"
        f"\n"
        f"Leitura:\n"
        f"{tpl['leitura']}"
    )


def format_terminal_status(decision: dict) -> str:
    """Status visual curto pra exibir no painel do daemon."""
    if not decision or not decision.get("should_alert"):
        return ""
    emoji, label = ALERT_DISPLAY.get(decision["alert_type"], ("⚪", "—"))
    return f"{emoji} {label}"


# ──────────────────────────────────────────────────────────────────────
# Envio simplificado (mantém assinatura legada)
# ──────────────────────────────────────────────────────────────────────


def send_alert(tg, decision: dict) -> bool:
    """Envia mensagem do alerta para TODOS os tipos (WATCH/FORTE/PREMIUM/BILATERAL).

    Política v2.8 (pedido do Tiago):
      WATCH OVER/BACK volta ao Telegram, MAS com dedup por
      (match_id, alert_type, bucket) feita pelo CALLER no live_daemon, antes
      de chamar essa função. Aqui o módulo da regra só envia — quem decide
      "novo vs repetido" é o caller, consultando o banco signals_persistence.

      Isso preserva a separação:
        - codigo_3_1 = lógica pura da regra (sem I/O em arquivo)
        - signals_persistence = estado/banco (responsável pela dedup)
        - live_daemon = orquestrador

    WATCH continua sem consumir bucket (update_state_after_alert preserva
    isso), então FORTE/PREMIUM no mesmo bucket após WATCH ainda disparam TG.
    """
    if tg is None or not decision or not decision.get("should_alert"):
        return False
    try:
        if not tg.is_ready():
            return False
    except Exception:
        return False
    msg = format_telegram_message(decision)
    if not msg:
        return False
    try:
        result = tg._send_raw(msg)
        return bool(result)
    except Exception:
        return False
