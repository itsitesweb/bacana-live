"""
MATCH_READER — Gera leitura tática + texto Telegram + narrative.md.

Cruza métricas funil (quádrupla + SOT%) com métricas contexto
(posse, toques área, defesas goleiro, cartões, escanteios, etc.)
para produzir uma INTERPRETAÇÃO narrativa do jogo.

NÃO toma decisão. Lê e relata.
"""
from datetime import datetime, timezone
from pathlib import Path

__version__ = "1.0.0"

_ROOT = Path(__file__).resolve().parent.parent
NARRATIVES_DIR = _ROOT / "logs" / "timelines"


def _safe_get(stats: dict, label_options: list, side: str):
    """stats no formato {label: {h, a}}. Tenta cada label, devolve valor ou None."""
    if not stats: return None
    stats_lower = {k.lower(): v for k, v in stats.items()}
    for label in label_options:
        v = stats_lower.get(label.lower())
        if v: return v.get(side, "")
    return None


def _parse_num(s):
    if not s: return 0.0
    s = str(s).replace("%","").replace(",",".").strip()
    # "88%(263/300)" pega só o primeiro número
    try: return float(s.split("(")[0].strip())
    except: return 0.0


def extract_context(stats: dict) -> dict:
    """Extrai métricas contexto do bag all_stats."""
    POSSE     = ["Posse de bola", "Ball possession"]
    TOQUES    = ["Toques dentro da área adversária","Touches in opposition box"]
    DENTRO    = ["Finalizações de dentro da área", "Shots inside box"]
    FORA      = ["Finalizações de fora da área", "Shots outside box"]
    BLOQUEADAS= ["Finalizações bloqueadas", "Blocked shots"]
    FORA_GOL  = ["Finalizações para fora", "Shots off target"]
    ESCANTEIOS= ["Escanteios", "Corners"]
    AMARELOS  = ["Cartões amarelos", "Yellow cards"]
    VERMELHOS = ["Cartões vermelhos", "Red cards"]
    PASSES_TF = ["Passes no terço final", "Final third passes"]
    PASSES_P  = ["Passes em profundidade certos", "Completed crosses"]
    DESARMES  = ["Desarmes", "Tackles"]
    INTERCEP  = ["Interceptações", "Interceptions"]
    DUELOS    = ["Duelos ganhos", "Duels won"]
    DEFESAS   = ["Defesas do goleiro", "Goalkeeper saves"]
    XGOT_ENF  = ["xGOT enfrentado", "xGOT against"]

    def both(labels):
        return (_parse_num(_safe_get(stats, labels, "h")),
                _parse_num(_safe_get(stats, labels, "a")))

    return {
        "posse":      both(POSSE),
        "toques_area":both(TOQUES),
        "fin_dentro": both(DENTRO),
        "fin_fora":   both(FORA),
        "fin_bloqueadas": both(BLOQUEADAS),
        "fin_fora_gol": both(FORA_GOL),
        "escanteios": both(ESCANTEIOS),
        "amarelos":   both(AMARELOS),
        "vermelhos":  both(VERMELHOS),
        "passes_tf":  both(PASSES_TF),
        "passes_prof":both(PASSES_P),
        "desarmes":   both(DESARMES),
        "intercep":   both(INTERCEP),
        "duelos":     both(DUELOS),
        "defesas":    both(DEFESAS),
        "xgot_enf":   both(XGOT_ENF),
    }


def detect_scenario(score_result: dict, ctx: dict, ms_dict: dict) -> dict:
    """Detecta o cenário narrativo dominante. Retorna dict com:
      scenario: "pressao_asfixiante" | "posse_improdutiva" | "contra_ataque" |
                "pressao_sem_qualidade" | "bola_parada" | "jogo_aberto" | "indef"
      side: "home" | "away" | "bilateral"
      reasoning: list de pontos auditáveis
    """
    h_g = ms_dict.get("home_score",0); a_g = ms_dict.get("away_score",0)
    posse_h, posse_a = ctx["posse"]
    toq_h, toq_a = ctx["toques_area"]
    dentro_h, dentro_a = ctx["fin_dentro"]

    home_xg = ms_dict.get("home_xg",0); away_xg = ms_dict.get("away_xg",0)
    home_cc = ms_dict.get("home_cc",0) or ms_dict.get("home_bc",0)
    away_cc = ms_dict.get("away_cc",0) or ms_dict.get("away_bc",0)

    reasoning = []
    diff = h_g - a_g  # +N home na frente, -N away na frente
    minute = ms_dict.get("minute", 0)

    # ✨ v4.0 — Cenário 0 (PRIORIDADE MÁXIMA): ADMINISTRAÇÃO DE VANTAGEM
    # Time com vantagem (1+ gols) + posse alta + ritmo baixo de produção
    # = administra resultado. NÃO é "posse improdutiva" — gols já vieram,
    # agora é controle. Tese: NÃO ENTRAR (placar tende a se manter).
    if diff >= 1:
        # Home na frente
        if posse_h >= 55 and home_xg < 1.0 and toq_h < 12 and minute >= 25:
            reasoning.append(
                f"Placar {h_g}-{a_g} | {home_xg:.2f} xG vs {h_g} gols → "
                f"posse {posse_h:.0f}% baixo ritmo (toques {toq_h:.0f}, xG {home_xg:.2f})"
            )
            return {"scenario": "administra_vantagem", "side": "home",
                    "reasoning": reasoning}
    elif diff <= -1:
        # Away na frente
        if posse_a >= 55 and away_xg < 1.0 and toq_a < 12 and minute >= 25:
            reasoning.append(
                f"Placar {h_g}-{a_g} | {away_xg:.2f} xG vs {a_g} gols → "
                f"posse {posse_a:.0f}% baixo ritmo (toques {toq_a:.0f}, xG {away_xg:.2f})"
            )
            return {"scenario": "administra_vantagem", "side": "away",
                    "reasoning": reasoning}

    # Cenário 1 — PRESSÃO ASFIXIANTE
    for side, posse, toq, xg, cc, other_toq in (
        ("home", posse_h, toq_h, home_xg, home_cc, toq_a),
        ("away", posse_a, toq_a, away_xg, away_cc, toq_h),
    ):
        if posse >= 65 and toq >= 12 and xg >= 1.0 and cc >= 2:
            ratio = (toq / other_toq) if other_toq > 0 else 99
            reasoning.append(
                f"Posse {posse:.0f}%, toques área {toq:.0f} (vs {other_toq:.0f}, "
                f"ratio {ratio:.1f}x), xG {xg:.2f}, CC {cc}"
            )
            return {"scenario":"pressao_asfixiante", "side":side,
                    "reasoning":reasoning}

    # Cenário 2 — POSSE IMPRODUTIVA
    for side, posse, toq, xg in (("home", posse_h, toq_h, home_xg),
                                   ("away", posse_a, toq_a, away_xg)):
        if posse >= 60 and toq < 8 and xg < 0.7:
            reasoning.append(f"Posse {posse:.0f}% mas só {toq:.0f} toques área, xG {xg:.2f}")
            return {"scenario":"posse_improdutiva", "side":side,
                    "reasoning":reasoning}

    # Cenário 3 — CONTRA-ATAQUE
    if posse_h < 40 and home_xg > away_xg and home_cc >= 2:
        reasoning.append(f"Posse só {posse_h:.0f}% mas xG {home_xg:.2f} > xG away {away_xg:.2f}")
        return {"scenario":"contra_ataque", "side":"home", "reasoning":reasoning}
    if posse_a < 40 and away_xg > home_xg and away_cc >= 2:
        reasoning.append(f"Posse só {posse_a:.0f}% mas xG {away_xg:.2f} > xG home {home_xg:.2f}")
        return {"scenario":"contra_ataque", "side":"away", "reasoning":reasoning}

    # Cenário 4 — PRESSÃO SEM QUALIDADE
    for side, posse, toq, xg, cc in (("home", posse_h, toq_h, home_xg, home_cc),
                                       ("away", posse_a, toq_a, away_xg, away_cc)):
        if posse >= 60 and toq >= 10 and xg < 0.8 and cc < 2:
            reasoning.append(
                f"Posse {posse:.0f}%, toques área {toq:.0f}, mas xG só {xg:.2f}, CC {cc}"
            )
            return {"scenario":"pressao_sem_qualidade", "side":side,
                    "reasoning":reasoning}

    # Cenário 6 — JOGO ABERTO
    if (abs(posse_h - 50) < 10 and toq_h >= 10 and toq_a >= 10
            and home_xg >= 1.0 and away_xg >= 1.0):
        reasoning.append(
            f"Posse {posse_h:.0f}/{posse_a:.0f}, toques área {toq_h:.0f}/{toq_a:.0f}, "
            f"xG {home_xg:.2f}/{away_xg:.2f}"
        )
        return {"scenario":"jogo_aberto", "side":"bilateral",
                "reasoning":reasoning}

    return {"scenario":"indef", "side":None, "reasoning":["sem cenário claro identificado"]}


SCENARIO_LABELS = {
    "administra_vantagem":   "🛡 ADMINISTRA VANTAGEM",
    "pressao_asfixiante":    "🔥 PRESSÃO ASFIXIANTE",
    "posse_improdutiva":     "😐 POSSE IMPRODUTIVA",
    "contra_ataque":         "⚡ CONTRA-ATAQUE",
    "pressao_sem_qualidade": "😴 PRESSÃO SEM QUALIDADE",
    "bola_parada":           "🎯 BOLA PARADA",
    "jogo_aberto":           "🌪 JOGO ABERTO",
    "indef":                 "❓ INDEFINIDO",
}


def build_telegram_text(ms_dict: dict, score_result: dict, scenario: dict,
                         ctx: dict, derivatives: dict) -> str:
    """Gera texto do Telegram com leitura tática."""
    tier = score_result["tier"]
    score = score_result["score"]
    home = ms_dict.get("home","?"); away = ms_dict.get("away","?")
    h_g = ms_dict.get("home_score",0); a_g = ms_dict.get("away_score",0)
    minute = ms_dict.get("minute",0)
    scope = score_result["scope"]; side = score_result["scope_side"]

    det = score_result["details"]
    cc_rate = det.get("cc_rate","?"); shot_rate = det.get("shot_rate","?")
    sot_pct = det.get("sot_pct",0); sot_proj = det.get("sot_projected","?")

    posse_h, posse_a = ctx["posse"]
    toq_h, toq_a = ctx["toques_area"]
    am_h, am_a = ctx["amarelos"]
    ve_h, ve_a = ctx["vermelhos"]
    def_h, def_a = ctx["defesas"]

    # Tese da operação por cenário
    sc = scenario["scenario"]; sc_side = scenario["side"]
    sc_label = SCENARIO_LABELS.get(sc, sc)
    if sc == "pressao_asfixiante" and sc_side:
        side_team = home if sc_side == "home" else away
        tese = f"BACK {side_team} próximo gol ou OVER se contraparte produzir"
    elif sc == "jogo_aberto":
        tese = "OVER 2.5 — jogo aberto dos 2 lados"
    elif sc == "contra_ataque" and sc_side:
        side_team = home if sc_side == "home" else away
        tese = f"BACK {side_team} (contra-ataque encaixado)"
    else:
        tese = "OVER 2.5 ou BACK time dominante (avaliar contexto)"

    # Quádrupla
    quad_lines = (
        f"CC: {det.get('cc','?')} (rate {cc_rate}min) "
        f"| xGOT: {det.get('xgot','?')} "
        f"| xG: {det.get('xg','?')} "
        f"| xA: {det.get('xa','?')}"
    )

    # Componentes do score
    comp = det.get("score_components",{})
    comp_line = (f"CC {comp.get('cc_norm','?')}/100 × 35% + "
                 f"xGOT {comp.get('xgot_norm','?')} × 25% + "
                 f"xG {comp.get('xg_norm','?')} × 20% + "
                 f"xA {comp.get('xa_norm','?')} × 20%")

    # Contexto narrativo
    contexto_lines = (
        f"Posse: {posse_h:.0f}%/{posse_a:.0f}% | "
        f"Toques área adv: {toq_h:.0f}/{toq_a:.0f} | "
        f"Defesas goleiro: {def_h:.0f}/{def_a:.0f}"
    )
    cartoes_line = (
        f"Amarelos: {am_h:.0f}/{am_a:.0f}"
        + (f" | 🟥 vermelhos: {ve_h:.0f}/{ve_a:.0f}" if (ve_h+ve_a) > 0 else "")
    )

    # Evolução das métricas funil
    evol_lines = []
    for m_name, label in [("home_cc","CC home"),("away_cc","CC away"),
                            ("home_xg","xG home"),("away_xg","xG away"),
                            ("home_xgot","xGOT home"),("away_xgot","xGOT away")]:
        d = derivatives.get(m_name, {})
        if d.get("delta_15m"):
            sign = "+" if d["delta_15m"] > 0 else ""
            evol_lines.append(f"  {label}: {sign}{d['delta_15m']} nos últimos 15min ({d.get('inflection','?')})")
    evol_text = "\n".join(evol_lines[:6]) if evol_lines else "  (sem histórico ainda)"

    # Reasoning do cenário
    reasoning = " · ".join(scenario.get("reasoning", []))

    tier_emoji = {"PREMIUM":"🟢","FORTE":"🟠","WATCH":"📡"}.get(tier,"")

    text = f"""{tier_emoji} {tier} — Score {score:.1f}/100
─────────────────────────
{home} {h_g}-{a_g} {away} | min {minute}
Escopo: {scope}{f' ({side})' if scope=='unilateral' else ''}

📊 Quádrupla:
{quad_lines}
SOT%: {sot_pct*100:.0f}% | SOT projetado: {sot_proj}

🎬 Cenário: {sc_label}
{reasoning}

📈 Evolução nos últimos 15 min:
{evol_text}

🎭 Contexto:
{contexto_lines}
{cartoes_line}

🧮 Composição:
{comp_line}

🎯 TESE:
{tese}

✅ Stake sugerido: {'2u' if tier=='PREMIUM' else '1u'}
"""
    return text


def append_narrative_block(match_id: str, block_text: str) -> Path:
    """Anexa texto no narrative.md do match_id."""
    p = NARRATIVES_DIR / f"{match_id}.narrative.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(block_text + "\n\n")
    return p


def build_tactical_report_md(ms_dict: dict, score_result: dict,
                              scenario: dict, ctx: dict,
                              derivatives: dict) -> str:
    """Gera leitura tática completa em Markdown legível.
    Funciona pra QUALQUER jogo monitorado, mesmo sem cruzar threshold.
    Aberto em qualquer editor (VS Code, Marked, Quick Look) fica bonito."""
    from datetime import datetime, timezone

    home = ms_dict.get("home","?"); away = ms_dict.get("away","?")
    h_g = ms_dict.get("home_score",0); a_g = ms_dict.get("away_score",0)
    minute = ms_dict.get("minute",0)
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    # Quádrupla
    h_cc = ms_dict.get("home_cc",0); a_cc = ms_dict.get("away_cc",0)
    h_xg = ms_dict.get("home_xg",0.0); a_xg = ms_dict.get("away_xg",0.0)
    h_xgot = ms_dict.get("home_xgot",0.0); a_xgot = ms_dict.get("away_xgot",0.0)
    h_xa = ms_dict.get("home_xa",0.0); a_xa = ms_dict.get("away_xa",0.0)
    h_shots = ms_dict.get("home_shots",0); a_shots = ms_dict.get("away_shots",0)
    h_sot = ms_dict.get("home_sot",0); a_sot = ms_dict.get("away_sot",0)

    # Contexto
    posse_h, posse_a = ctx.get("posse",(0,0))
    toq_h, toq_a = ctx.get("toques_area",(0,0))
    den_h, den_a = ctx.get("fin_dentro",(0,0))
    for_h, for_a = ctx.get("fin_fora",(0,0))
    fora_gol_h, fora_gol_a = ctx.get("fin_fora_gol",(0,0))
    blo_h, blo_a = ctx.get("fin_bloqueadas",(0,0))
    esc_h, esc_a = ctx.get("escanteios",(0,0))
    am_h, am_a = ctx.get("amarelos",(0,0))
    ve_h, ve_a = ctx.get("vermelhos",(0,0))
    def_h, def_a = ctx.get("defesas",(0,0))
    int_h, int_a = ctx.get("intercep",(0,0))
    duel_h, duel_a = ctx.get("duelos",(0,0))

    # Status do score
    tier = score_result.get("tier")
    score = score_result.get("score", 0.0)
    failed = score_result.get("failed_filter")
    tier_emoji = {"PREMIUM":"🟢","FORTE":"🟠","WATCH":"📡"}.get(tier,"⚪️")

    if tier:
        status_line = f"## {tier_emoji} {tier} — Score {score:.1f}/100"
        operacao = "**SIM** — entrada qualificada"
    elif failed:
        status_line = f"## ⚪️ Não-elegível"
        operacao = f"**Não.** Filtro bloqueou: `{failed}`"
    else:
        status_line = "## ⚪️ Aguardando dados"
        operacao = "Aguardar mais minutos / mais produção"

    # Cenário
    sc_label = SCENARIO_LABELS.get(scenario.get("scenario","indef"), "Indefinido")
    sc_reasoning = " · ".join(scenario.get("reasoning", []))

    # Tese da operação
    sc = scenario.get("scenario")
    sc_side = scenario.get("side")
    if sc == "pressao_asfixiante" and sc_side:
        side_team = home if sc_side == "home" else away
        tese = f"BACK **{side_team}** próximo gol — ou OVER se outro lado produzir"
    elif sc == "jogo_aberto":
        tese = "**OVER 2.5** — jogo aberto dos 2 lados"
    elif sc == "contra_ataque" and sc_side:
        side_team = home if sc_side == "home" else away
        tese = f"BACK **{side_team}** — contra-ataque encaixado"
    elif sc == "pressao_sem_qualidade":
        tese = "Esperar pontaria melhorar — pressão existe mas chuta mal"
    elif sc == "posse_improdutiva":
        tese = "**Não entrar** — posse sem perigo"
    else:
        tese = "Avaliar contexto (sem cenário claro identificado)"

    # Evolução
    evol_lines = []
    for m_name, label in [("home_cc","CC home"),("away_cc","CC away"),
                           ("home_xg","xG home"),("away_xg","xG away"),
                           ("home_xgot","xGOT home"),("away_xgot","xGOT away"),
                           ("home_shots","Finalizações home")]:
        d = derivatives.get(m_name, {})
        if d.get("delta_15m"):
            sign = "+" if d["delta_15m"] > 0 else ""
            evol_lines.append(f"- **{label}**: {sign}{d['delta_15m']} nos últimos 15min ({d.get('inflection','?')})")
    evol_text = "\n".join(evol_lines) if evol_lines else "_Sem histórico significativo ainda — primeiros snapshots_"

    md = f"""---

# {home} {h_g}-{a_g} {away}

**Minuto {minute}** · Atualizado às {now}

{status_line}

🎬 **Cenário detectado:** {sc_label}

{sc_reasoning if sc_reasoning else "_Aguardando dados suficientes para cenário_"}

---

## 📊 Quádrupla (métricas-mãe)

| Métrica | {home} | {away} |
|---|---:|---:|
| Chances Claras (CC) | **{h_cc}** | {a_cc} |
| xG | **{h_xg}** | {a_xg} |
| xGOT (qualidade fin.) | **{h_xgot}** | {a_xgot} |
| xA (qualidade passe) | **{h_xa}** | {a_xa} |

## 🎯 Finalizações

| | {home} | {away} |
|---|---:|---:|
| Total | **{h_shots}** | {a_shots} |
| No alvo (SOT) | **{h_sot}** | {a_sot} |
| Dentro da área | {den_h:.0f} | {den_a:.0f} |
| Fora da área | {for_h:.0f} | {for_a:.0f} |
| Para fora | {fora_gol_h:.0f} | {fora_gol_a:.0f} |
| Bloqueadas | {blo_h:.0f} | {blo_a:.0f} |

## 🗺 Contexto territorial

| | {home} | {away} |
|---|---:|---:|
| Posse de bola | **{posse_h:.0f}%** | {posse_a:.0f}% |
| Toques na área adversária | **{toq_h:.0f}** | {toq_a:.0f} |
| Escanteios | {esc_h:.0f} | {esc_a:.0f} |

## 🛡 Defesa & disciplina

| | {home} | {away} |
|---|---:|---:|
| Defesas do goleiro | {def_h:.0f} | {def_a:.0f} |
| Interceptações | {int_h:.0f} | {int_a:.0f} |
| Duelos ganhos | {duel_h:.0f} | {duel_a:.0f} |
| 🟨 Amarelos | {am_h:.0f} | {am_a:.0f} |
| 🟥 Vermelhos | {ve_h:.0f} | {ve_a:.0f} |

## 📈 Evolução nos últimos 15 min

{evol_text}

## 🎯 Tese operacional

**Vai virar Telegram?** {operacao}

**Sugestão tática:** {tese}

---

"""
    return md


def append_tactical_report(match_id: str, md_block: str) -> Path:
    """Reescreve (não anexa) o report tático completo. Mantém só o mais
    recente — versão atual do jogo. Anterior fica em snapshots .jsonl."""
    p = NARRATIVES_DIR / f"{match_id}.narrative.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        f.write(md_block)
    return p


# v3.4 — Relatório narrativo interpretativo (não tabela) pra Telegram
# Acionado a cada FIM DE BLOCO: 15, 30, 45 (HT), 60, 75, 90 min.

def _what_block(minute: int) -> int:
    """Retorna o bloco completado (15, 30, 45, 60, 75, 90) — ou 0 se ainda
    não fechou nenhum bloco."""
    for b in (90, 75, 60, 45, 30, 15):
        if minute >= b:
            return b
    return 0


def _bloc_label(b: int) -> str:
    return {
        15: "BLOCO 1 (0-15min)",
        30: "BLOCO 2 (15-30min)",
        45: "INTERVALO — Resumo do 1º Tempo",
        60: "BLOCO 4 (45-60min)",
        75: "BLOCO 5 (60-75min)",
        90: "FINAL — Resumo do Jogo",
    }.get(b, f"Min {b}")


def _next_block_label(minute: int) -> str:
    """Aponta o próximo ponto de revisão."""
    if minute < 30: return "Próxima leitura: min 30"
    if minute < 45: return "Próxima leitura: HT (min 45)"
    if minute < 60: return "Próxima leitura: min 60"
    if minute < 75: return "Próxima leitura: min 75"
    if minute < 90: return "Próxima leitura: Final (min 90)"
    return "Jogo encerrado"


def _fmt_sec(title: str, body: str) -> str:
    return f"**{title}**\n{body}\n\n"


def _build_data_line(ms_dict: dict, score_result: dict) -> str:
    h = ms_dict.get("home","?")[:6]
    a = ms_dict.get("away","?")[:6]
    h_xg = ms_dict.get("home_xg",0); a_xg = ms_dict.get("away_xg",0)
    h_cc = ms_dict.get("home_cc",0); a_cc = ms_dict.get("away_cc",0)
    h_sh = ms_dict.get("home_shots",0); a_sh = ms_dict.get("away_shots",0)
    h_sot = ms_dict.get("home_sot",0); a_sot = ms_dict.get("away_sot",0)
    score = score_result.get("score", 0.0) or 0.0
    return (
        f"xG {h_xg:.2f} × {a_xg:.2f}  ·  CC {h_cc} × {a_cc}\n"
        f"Finalizações {h_sh} × {a_sh}  ·  SOT {h_sot} × {a_sot}\n"
        f"Score: **{score:.0f}/100**"
    )


def _interp_pressao(home, away, dom_side, ms_dict, ctx, score_result):
    """Cenário PRESSÃO ASFIXIANTE."""
    dom_team = home if dom_side == "home" else away
    opp_team = away if dom_side == "home" else home
    posse_h, posse_a = ctx["posse"]
    toq_h, toq_a = ctx["toques_area"]
    posse_dom = posse_h if dom_side == "home" else posse_a
    toq_dom = toq_h if dom_side == "home" else toq_a
    toq_opp = toq_a if dom_side == "home" else toq_h

    xg_dom = ms_dict.get(f"{dom_side}_xg", 0.0)
    xgot_dom = ms_dict.get(f"{dom_side}_xgot", 0.0)
    xa_dom = ms_dict.get(f"{dom_side}_xa", 0.0)
    shots_dom = ms_dict.get(f"{dom_side}_shots", 0)
    sot_dom = ms_dict.get(f"{dom_side}_sot", 0)
    sot_pct = (sot_dom/shots_dom*100) if shots_dom else 0

    leitura = (
        f"{dom_team} domina o jogo. Posse {posse_dom:.0f}%, "
        f"{toq_dom:.0f} toques na área adversária contra apenas "
        f"{toq_opp:.0f}. Joga DENTRO da área do {opp_team}."
    )
    if sot_pct < 30 and shots_dom >= 8:
        leitura += (
            f"\n\nMas a finalização é ruim: {shots_dom} chutes, "
            f"só {sot_dom} no alvo ({sot_pct:.0f}%). xGOT {xgot_dom:.2f} "
            f"confirma — chutes que não machucam o goleiro."
        )
        tese = (
            f"**Aguardar pontaria melhorar.** Se SOT% subir pra 30%+, "
            f"entra BACK {dom_team}. Por enquanto, sem entrada."
        )
    elif xa_dom >= 0.6 and xgot_dom >= 0.7:
        leitura += (
            f"\n\nE finalização QUALIFICADA: xA {xa_dom:.2f} mostra "
            f"passes chegando ao último terço. xGOT {xgot_dom:.2f} "
            f"confirma qualidade no chute."
        )
        tese = f"**BACK {dom_team}** — pressão + qualidade = gol questão de tempo."
    else:
        leitura += (
            f"\n\nProdução média: xG {xg_dom:.2f}, xGOT {xgot_dom:.2f}. "
            f"Volume tá, qualidade ainda não."
        )
        tese = f"**Aguardar** — pressão presente, qualidade precisa subir."
    return leitura, tese


def _interp_jogo_aberto(home, away, ms_dict, ctx, score_result):
    posse_h, posse_a = ctx["posse"]
    toq_h, toq_a = ctx["toques_area"]
    h_xg = ms_dict.get("home_xg",0); a_xg = ms_dict.get("away_xg",0)
    leitura = (
        f"Festa de gol — os dois times atacam. "
        f"Posse {posse_h:.0f}/{posse_a:.0f}, toques área "
        f"{toq_h:.0f}/{toq_a:.0f}. xG bilateral ({h_xg:.2f} vs {a_xg:.2f}) "
        f"mostra que os dois criam."
    )
    tese = "**OVER 2.5** — jogo aberto não fecha em 0-0."
    return leitura, tese


def _interp_posse_improdutiva(home, away, dom_side, ms_dict, ctx):
    dom_team = home if dom_side == "home" else away
    posse_h, posse_a = ctx["posse"]
    toq_h, toq_a = ctx["toques_area"]
    posse_dom = posse_h if dom_side == "home" else posse_a
    toq_dom = toq_h if dom_side == "home" else toq_a
    xg_dom = ms_dict.get(f"{dom_side}_xg", 0.0)
    leitura = (
        f"{dom_team} tem a bola ({posse_dom:.0f}%) mas não chega no "
        f"perigo. Só {toq_dom:.0f} toques na área, xG {xg_dom:.2f}. "
        f"Posse de dança — não machuca."
    )
    tese = "**Não entrar.** Esse jogo pode terminar 0-0 fácil."
    return leitura, tese


def _interp_contra_ataque(home, away, dom_side, ms_dict, ctx):
    dom_team = home if dom_side == "home" else away
    opp_team = away if dom_side == "home" else home
    posse_dom = ctx["posse"][0] if dom_side == "home" else ctx["posse"][1]
    xg_dom = ms_dict.get(f"{dom_side}_xg", 0.0)
    leitura = (
        f"{dom_team} encaixado no contra-ataque. Posse só {posse_dom:.0f}% "
        f"mas xG {xg_dom:.2f} — quando sai, sai com perigo. {opp_team} "
        f"tem a bola sem converter em chance."
    )
    tese = f"**BACK {dom_team}** — contra-ataque encaixado é gol que acontece."
    return leitura, tese


def _interp_indef(home, away, ms_dict, ctx, score_result):
    minute = ms_dict.get("minute",0)
    h_g = ms_dict.get("home_score",0); a_g = ms_dict.get("away_score",0)
    h_xg = ms_dict.get("home_xg",0); a_xg = ms_dict.get("away_xg",0)
    h_shots = ms_dict.get("home_shots",0); a_shots = ms_dict.get("away_shots",0)
    total_shots = h_shots + a_shots
    shot_rate = (minute / total_shots) if total_shots else 999

    if total_shots < 5:
        leitura = (
            f"Jogo lento até agora. Apenas {total_shots} finalizações "
            f"em {minute} min — ritmo de 1 chute a cada {shot_rate:.1f}min, "
            f"abaixo do ritmo qualificado (3.5min/chute)."
        )
    elif shot_rate > 4:
        leitura = (
            f"Ritmo de finalizações lento ({shot_rate:.1f}min/chute). "
            f"xG {h_xg:.2f} × {a_xg:.2f} — produção mediana. "
            f"Jogo ainda não engatou."
        )
    else:
        leitura = (
            f"Jogo equilibrado, sem dominância clara. "
            f"xG {h_xg:.2f} × {a_xg:.2f}, finalizações "
            f"{h_shots} × {a_shots}. Aguarda definição."
        )
    tese = "**Aguardar** mais produção pra ter cenário tático claro."
    return leitura, tese


# v3.5 — Detecção de jogo qualificado (modo intensivo)
INTENSIVE_SCENARIOS = ("pressao_asfixiante", "jogo_aberto", "contra_ataque")
SCORE_INTENSIVE_THRESHOLD = 60.0
SCORE_RISING_THRESHOLD = 10.0


def is_intensive_mode(score_result: dict, scenario: dict,
                        score_history: list = None) -> tuple:
    """Decide se o jogo entra em modo intensivo.

    Returns (intensivo: bool, motivo: str).
    Critérios (qualquer um basta):
      1. score >= 60
      2. cenário em (PRESSÃO ASFIXIANTE, JOGO ABERTO, CONTRA-ATAQUE)
      3. score crescendo >= 10 entre 2 últimos blocos
      4. passou em pelo menos 4 dos 6 filtros eliminatórios
    """
    score = score_result.get("score", 0.0) or 0.0
    sc_name = scenario.get("scenario", "indef")

    # 1. Score já está no zona WATCH ou acima
    if score >= SCORE_INTENSIVE_THRESHOLD:
        return (True, f"score={score:.1f}>={SCORE_INTENSIVE_THRESHOLD}")

    # 2. Cenário tático aproveitável detectado
    if sc_name in INTENSIVE_SCENARIOS:
        return (True, f"scenario={sc_name}")

    # 3. Score crescendo entre blocos
    if score_history and len(score_history) >= 2:
        if score_history[-1] - score_history[-2] >= SCORE_RISING_THRESHOLD:
            return (True, f"score rising +{score_history[-1] - score_history[-2]:.1f}")

    # 4. Quase passou — chegou perto da entrada
    # Conta quantos filtros explicitamente passou (sem failed_filter, ou
    # falhou em apenas 1 dos 6)
    failed = score_result.get("failed_filter")
    if failed is None:
        return (True, "all_filters_passed")
    # Se chegou a calcular details com cc_rate + shot_rate + sot_pct =
    # significa que passou no mínimo dos 3 primeiros filtros
    details = score_result.get("details") or {}
    filters_passed = sum(1 for k in ("cc_rate","shot_rate","sot_pct","sot_projected") if k in details)
    if filters_passed >= 3:
        return (True, f"passed {filters_passed}/4 critical filters (failed: {failed})")

    return (False, f"padrao (score={score:.1f}, scenario={sc_name})")


def should_send_block_report(block: int, intensive: bool) -> bool:
    """Decide se o relatório deste bloco deve ser enviado.

    Modo PADRÃO: só envia min 30 e min 60.
    Modo INTENSIVO: envia em todos os blocos (15, 30, 45, 60, 75, 90).
    """
    if intensive:
        return block in (15, 30, 45, 60, 75, 90)
    return block in (30, 60)


# v3.6 — Relatório estilo "auxiliar técnico" (Pep/Ancelotti)
# Estrutura fixa:
#   1. Header curto (placar + bloco)
#   2. "Boss, o que rolou:" — narrativa do bloco
#   3. "Leitura tática:" — interpretação do cenário
#   4. "Evolução desde o último bloco:" (se houver histórico)
#   5. "Recomendação:" — clara, direta
#   6. "Próxima leitura: ..." — checkpoint seguinte

def _bloc_simple_label(b: int) -> str:
    return {15: "Bloco 1", 30: "Bloco 2", 45: "Intervalo (HT)",
            60: "Bloco 4", 75: "Bloco 5", 90: "Final"}.get(b, f"Min {b}")


def coach_narrative(ms_dict, ctx, scenario, score_result) -> dict:
    """API pública: retorna {'rolou', 'leitura', 'recomendacao'} pro PDF."""
    home = ms_dict.get("home", "?"); away = ms_dict.get("away", "?")
    rolou, leitura, rec = _coach_narrative_block(
        home, away, ms_dict, ctx, scenario, score_result)
    return {"rolou": rolou, "leitura": leitura, "recomendacao": rec}


def _coach_narrative_block(home, away, ms_dict, ctx, scenario, score_result):
    """Narrativa do que rolou no bloco — estilo auxiliar técnico.

    Returns: (o_que_rolou, leitura_tatica, recomendacao)
    """
    h_g = ms_dict.get("home_score", 0); a_g = ms_dict.get("away_score", 0)
    minute = ms_dict.get("minute", 0)
    sc = scenario.get("scenario", "indef")
    sc_side = scenario.get("side")

    h_xg = ms_dict.get("home_xg", 0); a_xg = ms_dict.get("away_xg", 0)
    h_cc = ms_dict.get("home_cc", 0); a_cc = ms_dict.get("away_cc", 0)
    h_sh = ms_dict.get("home_shots", 0); a_sh = ms_dict.get("away_shots", 0)
    h_sot = ms_dict.get("home_sot", 0); a_sot = ms_dict.get("away_sot", 0)
    h_xgot = ms_dict.get("home_xgot", 0); a_xgot = ms_dict.get("away_xgot", 0)
    h_xa = ms_dict.get("home_xa", 0); a_xa = ms_dict.get("away_xa", 0)

    posse_h, posse_a = ctx.get("posse", (50, 50))
    toq_h, toq_a = ctx.get("toques_area", (0, 0))

    # ─────────── ADMINISTRA VANTAGEM ───────────
    if sc == "administra_vantagem" and sc_side:
        ven = home if sc_side == "home" else away
        per = away if sc_side == "home" else home
        ven_g = h_g if sc_side == "home" else a_g
        per_g = a_g if sc_side == "home" else h_g
        posse_v = posse_h if sc_side == "home" else posse_a
        toq_v = toq_h if sc_side == "home" else toq_a
        xg_v = h_xg if sc_side == "home" else a_xg

        rolou = (
            f"{ven} vence {ven_g}-{per_g} e baixou o ritmo. Posse "
            f"{posse_v:.0f}% mas só {toq_v:.0f} toques na área, "
            f"xG do bloco {xg_v:.2f}. Cadência de jogo controlado."
        )
        leitura = (
            f"{ven} já materializou a vantagem e agora administra. "
            f"Troca passes no campo de defesa/meio, não se expõe. "
            f"{per} também não pressiona o suficiente pra reagir. "
            f"Cenário típico de jogo que termina como está."
        )
        rec = (
            f"**Sem entrada agora.** Odd {ven} já caiu — sem prêmio. "
            f"Odd {per} (virar/empatar) tem prêmio mas SEM SINAL de "
            f"reação. Não vale a pena especular."
        )
        return rolou, leitura, rec

    # ─────────── PRESSÃO ASFIXIANTE ───────────
    if sc == "pressao_asfixiante" and sc_side:
        dom = home if sc_side == "home" else away
        opp = away if sc_side == "home" else home
        posse_d = posse_h if sc_side == "home" else posse_a
        toq_d = toq_h if sc_side == "home" else toq_a
        toq_o = toq_a if sc_side == "home" else toq_h
        xg_d = h_xg if sc_side == "home" else a_xg
        xgot_d = h_xgot if sc_side == "home" else a_xgot
        xa_d = h_xa if sc_side == "home" else a_xa
        cc_d = h_cc if sc_side == "home" else a_cc
        sh_d = h_sh if sc_side == "home" else a_sh
        sot_d = h_sot if sc_side == "home" else a_sot
        sot_pct = (sot_d/sh_d*100) if sh_d else 0

        # Placar — quem pressiona já está ganhando muito?
        dom_diff = (h_g - a_g) if sc_side == "home" else (a_g - h_g)

        rolou = (
            f"{dom} mandou no bloco. Ficou {posse_d:.0f}% com a bola, "
            f"colocou {toq_d:.0f} pés dentro da área (contra {toq_o:.0f} "
            f"do {opp}). Acumulou {sh_d} finalizações e construiu "
            f"{cc_d} chance{'s' if cc_d != 1 else ''} clara{'s' if cc_d != 1 else ''}."
        )

        # ✨ Quem pressiona JÁ ESTÁ GANHANDO POR 2+: odd despencou, sem trade
        if dom_diff >= 2:
            leitura = (
                f"{dom} mantém o domínio mesmo ganhando {h_g}-{a_g}. "
                f"Pressão pela vitória mais larga, mas o mercado já "
                f"precificou: odd de {dom} já tá baixa demais pra ter "
                f"valor. Pode buscar OVER pelo gol extra se o ritmo "
                f"continuar."
            )
            rec = (
                f"**Sem entrada em BACK {dom}** — odd já caiu, sem prêmio. "
                f"Avaliar **OVER** se total de gols ainda baixo "
                f"(quanto menor o total atual, melhor)."
            )
            return rolou, leitura, rec

        # 3 sub-cenários: chuta mal / chuta bem / produção mediana
        if sot_pct < 30 and sh_d >= 8:
            leitura = (
                f"{dom} está pressionando mas não acerta o alvo — só "
                f"{sot_d} de {sh_d} chutes no gol ({sot_pct:.0f}%). xGOT "
                f"{xgot_d:.2f} confirma: chutes ruins, goleiro não trabalha. "
                f"É domínio territorial sem tradução em perigo real."
            )
            rec = (
                f"Aguardar — pontaria precisa subir. Se SOT% passar dos 30%, "
                f"é hora de BACK {dom}. Por enquanto, sem entrada."
            )
        elif xa_d >= 0.6 and xgot_d >= 0.7:
            leitura = (
                f"{dom} pressiona COM qualidade: xA {xa_d:.2f} mostra que "
                f"os passes chegam ao último terço bem construídos. xGOT "
                f"{xgot_d:.2f} confirma que os chutes machucam o goleiro. "
                f"É questão de tempo até furar."
            )
            rec = (
                f"**BACK {dom}** — pressão + qualidade = gol vindo. "
                f"Stake recomendado: 1u-2u."
            )
        else:
            leitura = (
                f"{dom} tem volume mas a qualidade ainda não engrenou. "
                f"xG {xg_d:.2f}, xGOT {xgot_d:.2f} — produção mediana pro "
                f"tanto que pressiona. Falta o último passe ou o chute decisivo."
            )
            rec = (
                f"Aguardar — pressão tá, qualidade precisa subir. "
                f"Acompanhar próximo bloco."
            )
        return rolou, leitura, rec

    # ─────────── JOGO ABERTO ───────────
    if sc == "jogo_aberto":
        rolou = (
            f"Bloco eletrizante — os dois times atacaram. {home} criou "
            f"({h_sh} fin., xG {h_xg:.2f}) e {away} respondeu "
            f"({a_sh} fin., xG {a_xg:.2f}). Toques na área "
            f"{toq_h:.0f}/{toq_a:.0f}, posse equilibrada "
            f"({posse_h:.0f}/{posse_a:.0f})."
        )
        leitura = (
            f"Jogo de transição — nenhum dos dois consegue controlar. "
            f"Ambos chegam ao último terço e finalizam. Defesas expostas "
            f"em ambos os lados. Sai gol nesse cenário."
        )
        rec = (
            f"**OVER 2.5** — jogo aberto não fecha em 0-0. "
            f"Stake: 1u-2u."
        )
        return rolou, leitura, rec

    # ─────────── CONTRA-ATAQUE ───────────
    if sc == "contra_ataque" and sc_side:
        dom = home if sc_side == "home" else away
        opp = away if sc_side == "home" else home
        posse_d = posse_h if sc_side == "home" else posse_a
        xg_d = h_xg if sc_side == "home" else a_xg
        xg_o = a_xg if sc_side == "home" else h_xg

        rolou = (
            f"{opp} controlou a bola ({100-posse_d:.0f}%) mas {dom} foi mais "
            f"eficiente. Mesmo com posse de {posse_d:.0f}%, o {dom} "
            f"construiu xG {xg_d:.2f} contra {xg_o:.2f} do adversário."
        )
        leitura = (
            f"{dom} está encaixado no contra-ataque. Cede a bola, espera "
            f"o erro e ataca com velocidade. {opp} se expõe na busca por "
            f"jogo ofensivo e abre espaço pras transições."
        )
        rec = (
            f"**BACK {dom}** — contra-ataque encaixado é gol que vem. "
            f"Stake: 1u-2u."
        )
        return rolou, leitura, rec

    # ─────────── POSSE IMPRODUTIVA ───────────
    if sc == "posse_improdutiva" and sc_side:
        dom = home if sc_side == "home" else away
        posse_d = posse_h if sc_side == "home" else posse_a
        toq_d = toq_h if sc_side == "home" else toq_a
        xg_d = h_xg if sc_side == "home" else a_xg

        rolou = (
            f"{dom} ficou com a bola ({posse_d:.0f}%) mas não machucou. "
            f"Apenas {toq_d:.0f} toques na área adversária, xG {xg_d:.2f}. "
            f"Posse esterilizada."
        )
        leitura = (
            f"{dom} domina a posse mas joga longe da área. Trocas no meio "
            f"sem profundidade. O adversário se defende confortável, sem "
            f"sustos. Esse cenário tende a empate sem gol."
        )
        rec = (
            f"**Não entrar.** Posse de dança não vira gol. "
            f"Jogo pode terminar 0-0."
        )
        return rolou, leitura, rec

    # ─────────── INDEFINIDO / EQUILIBRADO ───────────
    total_shots = h_sh + a_sh
    shot_rate = (minute / total_shots) if total_shots else 999

    if h_g + a_g > 0 and abs(h_g - a_g) >= 2:
        ganha = home if h_g > a_g else away
        perde = away if h_g > a_g else home
        loser_side = "away" if h_g > a_g else "home"
        leader_side = "home" if h_g > a_g else "away"

        # ✨ Detectar REAÇÃO do perdedor no bloco
        l_g_block = ms_dict.get(f"{loser_side}_score_block", 0)
        l_xg_b = ms_dict.get(f"{loser_side}_xg", 0)
        l_xgot_b = ms_dict.get(f"{loser_side}_xgot", 0)
        ld_xg_b = ms_dict.get(f"{leader_side}_xg", 0)
        ld_xgot_b = ms_dict.get(f"{leader_side}_xgot", 0)
        is_reacting = (
            l_g_block >= 1 or
            (l_xgot_b >= 0.4 and l_xgot_b > ld_xgot_b) or
            (l_xg_b >= 0.5 and l_xg_b > ld_xg_b)
        )

        if is_reacting:
            # Perdedor REAGIU — narrativa diferente
            reaction_detail = []
            if l_g_block >= 1:
                reaction_detail.append(f"marcou {int(l_g_block)} gol no bloco")
            if l_xgot_b > ld_xgot_b and l_xgot_b >= 0.4:
                reaction_detail.append(
                    f"xGOT bloco {l_xgot_b:.2f} (vs {ld_xgot_b:.2f} do líder)")
            if l_xg_b > ld_xg_b and l_xg_b >= 0.5:
                reaction_detail.append(
                    f"xG bloco {l_xg_b:.2f} (vs {ld_xg_b:.2f} do líder)")
            detail = " · ".join(reaction_detail)

            rolou = (
                f"Placar acumulado {h_g}-{a_g} mas {perde} REAGIU no bloco: "
                f"{detail}. {ganha} relaxou (xG bloco {ld_xg_b:.2f})."
            )
            leitura = (
                f"Apesar do placar amplo, o bloco mostra inversão clara: "
                f"{perde} produziu mais e {ganha} desacelerou (substituições, "
                f"jogo controlado). Próximo gol mais provável do {perde}. "
                f"Jogo se reabriu nos minutos finais."
            )
            rec = (
                f"**Considerar NEXT GOAL {perde}** ou **OVER** "
                f"(jogo abriu). BACK {perde} pra vitória tem stake "
                f"baixíssimo — só vale se odd ≥ fair calculada."
            )
            return rolou, leitura, rec

        # Jogo realmente morto — sem reação
        rolou = (
            f"Placar {h_g}-{a_g} e ritmo do bloco foi baixo. "
            f"{ganha} administra a vantagem, total de {total_shots} "
            f"finalizações em {minute} min — ritmo morno (1 chute a cada "
            f"{shot_rate:.1f} min)."
        )
        leitura = (
            f"Vantagem ampla de {ganha} esfriou o jogo. Sem urgência do "
            f"lado vencedor, sem reação do {perde}. Cenário típico "
            f"de jogo controlado pra dormir."
        )
        rec = (
            f"Sem entrada. Cenário não tem produção pra justificar trade — "
            f"placar tende a se manter."
        )
        return rolou, leitura, rec

    if total_shots < 4:
        rolou = (
            f"Bloco morno. Apenas {total_shots} finalizações totais em "
            f"{minute} min de jogo. Ritmo de 1 chute a cada {shot_rate:.1f} "
            f"min — bem abaixo do esperado pra um jogo produtivo."
        )
        leitura = (
            f"Times entraram cautelosos. Posse {posse_h:.0f}/{posse_a:.0f} "
            f"sem dominância clara. Nenhum dos dois encontrou o caminho "
            f"da área. Jogo precisa engatar."
        )
        rec = "Aguardar — sem volume pra ler cenário ainda."
        return rolou, leitura, rec

    if shot_rate > 4:
        rolou = (
            f"Bloco de ritmo médio. {total_shots} finalizações totais "
            f"({h_sh} × {a_sh}), xG {h_xg:.2f} vs {a_xg:.2f}. Sem "
            f"dominância territorial clara — posse "
            f"{posse_h:.0f}/{posse_a:.0f}."
        )
        leitura = (
            f"Equilíbrio sem definição. Os dois tentam mas ninguém impõe "
            f"superioridade. Cenário tático aberto — pode pender pra "
            f"qualquer lado no próximo bloco."
        )
        rec = "Aguardar próximo bloco — sem entrada com esse equilíbrio."
        return rolou, leitura, rec

    # Fallback genérico
    rolou = (
        f"Bloco com {total_shots} finalizações ({h_sh} × {a_sh}). "
        f"xG {h_xg:.2f} vs {a_xg:.2f}, posse "
        f"{posse_h:.0f}/{posse_a:.0f}."
    )
    leitura = (
        f"Jogo sem cenário tático definido. Produção bilateral sem "
        f"superioridade clara de nenhum lado."
    )
    rec = "Aguardar definição — sem entrada por enquanto."
    return rolou, leitura, rec


def _evolution_summary(derivatives: dict, current_score: float,
                        score_history: list) -> str:
    """Mostra evolução das métricas-chave nos últimos 15 min."""
    if not derivatives:
        return ""

    movements = []
    # Score evolution
    if score_history and len(score_history) >= 2:
        delta = current_score - score_history[-2]
        if abs(delta) >= 5:
            sign = "+" if delta > 0 else ""
            arrow = "↗" if delta > 0 else "↘"
            movements.append(f"Score do jogo {arrow} {sign}{delta:.0f} pontos")

    # Top 3 métricas com maior delta_15m
    deltas = []
    for m, label in [("home_cc", "CC casa"), ("away_cc", "CC fora"),
                       ("home_xg", "xG casa"), ("away_xg", "xG fora"),
                       ("home_shots", "Finalizações casa"),
                       ("away_shots", "Finalizações fora"),
                       ("home_sot", "SOT casa"), ("away_sot", "SOT fora")]:
        d = derivatives.get(m, {})
        delta = d.get("delta_15m", 0)
        if abs(delta) >= 0.5:
            deltas.append((abs(delta), label, delta, d.get("inflection", "")))
    deltas.sort(reverse=True)

    for _, label, val, infl in deltas[:3]:
        sign = "+" if val > 0 else ""
        arrow = "↗" if val > 0 else "↘"
        movements.append(f"{label} {arrow} {sign}{val:.1f}")

    if not movements:
        return ""
    return "\n".join(f"• {m}" for m in movements)


def build_narrative_telegram(ms_dict: dict, score_result: dict,
                                scenario: dict, ctx: dict,
                                derivatives: dict, block: int,
                                intensive: bool = False,
                                intensive_reason: str = "",
                                score_history: list = None) -> str:
    """Relatório estilo auxiliar técnico — clean, conclusivo, narrativo."""
    home = ms_dict.get("home", "?"); away = ms_dict.get("away", "?")
    h_g = ms_dict.get("home_score", 0); a_g = ms_dict.get("away_score", 0)
    minute = ms_dict.get("minute", 0)
    current_score = score_result.get("score", 0.0) or 0.0

    # ─── Header limpo ───
    bloc_lbl = _bloc_simple_label(block)
    header = f"⚽ {home} {h_g}-{a_g} {away}\n"
    header += f"{bloc_lbl} fechado · min {minute}\n\n"

    # ─── Narrativa do auxiliar técnico ───
    rolou, leitura, rec = _coach_narrative_block(
        home, away, ms_dict, ctx, scenario, score_result)

    body = f"**Boss, o que rolou:**\n{rolou}\n\n"
    body += f"**Leitura tática:**\n{leitura}\n\n"

    # ─── Evolução vs bloco anterior (se houver dados) ───
    evol = _evolution_summary(derivatives, current_score, score_history or [])
    if evol:
        body += f"**Evolução vs bloco anterior:**\n{evol}\n\n"

    # ─── Recomendação ───
    body += f"**Recomendação:**\n{rec}\n\n"

    # ─── Sinal de entrada (se tier qualificou) ───
    tier = score_result.get("tier")
    if tier == "PREMIUM":
        body += f"🟢 **ENTRADA PREMIUM** · Score {current_score:.0f}/100\n"
    elif tier == "FORTE":
        body += f"🟠 **ENTRADA FORTE** · Score {current_score:.0f}/100\n"
    elif tier == "WATCH":
        body += f"📡 No radar (WATCH) · Score {current_score:.0f}/100\n"

    # ─── Próxima leitura ───
    next_lbl = _next_block_label(minute)
    body += f"\n_{next_lbl}_"

    return header + body
