"""
MATCH_PDF v2 — Relatório executivo premium estilo Bloomberg.

Layout:
  ┌─────────────────────────────────────┐
  │ ▌ TRADER REGRA 3.1.2.0  ·  22:36 GMT │ ← faixa preta + dourado
  ├─────────────────────────────────────┤
  │                                     │
  │  MINNESOTA 2 · 3 — 1 · SKC II       │ ← score em destaque
  │  BLOCO 4 · 45-60 MIN · MIN 68       │
  │  [WATCH 74/100]   <-- badge tier    │
  ├─────────────────────────────────────┤
  │  ◆ O QUE ROLOU NO BLOCO             │
  │  [narrativa]                        │
  │                                     │
  │  ◆ LEITURA TÁTICA                   │
  │  [análise]                          │
  │                                     │
  │  ◆ EVOLUÇÃO vs BLOCO ANTERIOR       │
  │  ▲ Score +12  ▲ Finalizações +4    │
  │                                     │
  │  ◆ MÉTRICAS DO JOGO                 │
  │  [tabela executiva]                 │
  ├─────────────────────────────────────┤
  │  RECOMENDAÇÃO                       │
  │  [tese clara, destaque visual]      │
  ├─────────────────────────────────────┤
  │ TRADER REGRA 3.1.2.0  ·  v3.8       │ ← footer
  └─────────────────────────────────────┘
"""
from pathlib import Path
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A5, A4
from reportlab.lib.units import mm

# ✨ v4.6 — Padronização A4 para todos os PDFs (alinha com Relatório Final)
PAGE_SIZE = A4
FOOTER_BRAND = "TRADER REGRA 3.1.2.0 · CONFIDENCIAL"
FOOTER_RIGHT = "OPERADOR: TIAGO LOPES"
from reportlab.lib.colors import HexColor, white, black
from reportlab.pdfgen import canvas as _canvas
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    Table, TableStyle, HRFlowable, KeepTogether,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

__version__ = "2.1.0"


def build_pressao_vendavel_pdf(ms_dict: dict, pv_result: dict, ctx: dict) -> Path:
    """PDF de ALERTA — Pressão Vendável (BACK na odd alta + LAY na baixa).

    Layout urgente: header verde, tese gigante, números em destaque.
    """
    home = ms_dict.get("home", "?")
    away = ms_dict.get("away", "?")
    h_g = ms_dict.get("home_score", 0); a_g = ms_dict.get("away_score", 0)
    minute = ms_dict.get("minute", 0)
    mid = ms_dict.get("match_id", "match")
    team = pv_result["team"]
    m = pv_result["metrics"]
    prob = pv_result.get("probability", {})
    prob_target = prob.get("prob_target", 0)
    prob_home = prob.get("prob_home_win", 0)
    prob_draw = prob.get("prob_draw", 0)
    prob_away = prob.get("prob_away_win", 0)
    fair_odd = prob.get("fair_odd", 0)
    min_odd = prob.get("min_recommended_odd", 0)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%H%M%S")
    safe_mid = str(mid).replace("/", "_").replace(":", "_")
    pdf_path = REPORTS_DIR / f"{safe_mid}_ALERT_pv_{ts}.pdf"

    doc = BaseDocTemplate(
        str(pdf_path), pagesize=PAGE_SIZE,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=20*mm, bottomMargin=18*mm,
        title=f"ENTRADA RECOMENDADA · BACK {team}",
        author="Trader Regra 3.1.2.0",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                   doc.width, doc.height, id="main", showBoundary=0)

    def _draw_alert_hf(canv, doc_):
        pw, ph = PAGE_SIZE  # consistente com doc.pagesize
        # Top bar verde
        canv.saveState()
        canv.setFillColor(HexColor("#047857"))
        canv.rect(0, ph - 10*mm, pw, 10*mm, fill=1, stroke=0)
        canv.setFillColor(white)
        canv.setFont("Helvetica-Bold", 8)
        canv.drawString(10*mm, ph - 6.5*mm, "▌ TRADER REGRA 3.1.2.0")
        ts2 = datetime.now().strftime("%H:%M · %d %b %Y").upper()
        canv.setFont("Helvetica", 7)
        canv.drawRightString(pw - 10*mm, ph - 6.5*mm, ts2)
        # Footer
        fy = 8*mm
        canv.setFillColor(COLOR_GRAY_LIGHT)
        canv.rect(10*mm, fy + 4*mm, pw - 20*mm, 0.3, fill=1, stroke=0)
        canv.setFillColor(COLOR_GRAY_DARK)
        canv.setFont("Helvetica-Bold", 6.5)
        canv.drawString(10*mm, fy, FOOTER_BRAND)
        canv.setFillColor(COLOR_GRAY)
        canv.setFont("Helvetica", 6.5)
        try:
            page_num = canv.getPageNumber()
            canv.drawCentredString(pw/2, fy, f"Página {page_num}")
        except Exception:
            pass
        canv.drawRightString(pw - 10*mm, fy, FOOTER_RIGHT)
        canv.restoreState()

    template = PageTemplate(id="alert", frames=[frame], onPage=_draw_alert_hf)
    doc.addPageTemplates([template])

    base = getSampleStyleSheet()
    st_alert_label = ParagraphStyle(
        "alertLabel", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=8, leading=10,
        textColor=HexColor("#047857"), alignment=TA_LEFT, spaceAfter=4,
    )
    st_match = ParagraphStyle(
        "match", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=14, leading=17,
        textColor=COLOR_BLACK, alignment=TA_LEFT, spaceAfter=2,
    )
    st_meta = ParagraphStyle(
        "meta", parent=base["Normal"],
        fontName="Helvetica", fontSize=9, leading=11,
        textColor=COLOR_GRAY, alignment=TA_LEFT, spaceAfter=8,
    )
    st_action = ParagraphStyle(
        "action", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=20, leading=24,
        textColor=HexColor("#047857"), alignment=TA_CENTER, spaceAfter=10,
    )
    st_sec = ParagraphStyle(
        "sec", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=7.5, leading=10,
        textColor=COLOR_GOLD_DARK, alignment=TA_LEFT,
        spaceBefore=10, spaceAfter=4,
    )
    st_body = ParagraphStyle(
        "body", parent=base["BodyText"],
        fontName="Helvetica", fontSize=10, leading=14,
        textColor=COLOR_DARK, alignment=TA_LEFT, spaceAfter=4,
    )
    st_odd_label = ParagraphStyle(
        "oddL", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=7, leading=9,
        textColor=COLOR_GRAY, alignment=TA_CENTER,
    )
    st_odd = ParagraphStyle(
        "odd", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=14, leading=17,
        textColor=COLOR_BLACK, alignment=TA_CENTER,
    )

    story = []
    story.append(Paragraph("ENTRADA RECOMENDADA", st_alert_label))
    story.append(Paragraph(f"{home}  <font color='#C9A961'>{h_g} — {a_g}</font>  {away}", st_match))
    story.append(Paragraph(f"MINUTO {minute}", st_meta))

    # AÇÃO em destaque
    story.append(Paragraph(f"BACK  {team.upper()}", st_action))

    # ─── Mesa de probabilidade + odd ───
    odd_table = Table([
        [Paragraph("PROBABILIDADE", st_odd_label),
         Paragraph("ODD JUSTA", st_odd_label),
         Paragraph("ODD MÍNIMA", st_odd_label)],
        [Paragraph(f"{prob_target:.0f}%", st_odd),
         Paragraph(f"{fair_odd:.2f}", st_odd),
         Paragraph(f"{min_odd:.2f}", st_odd)],
    ], colWidths=[42*mm, 42*mm, 42*mm])
    odd_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), COLOR_OFFWHITE),
        ("BACKGROUND", (0,1), (0,1), HexColor("#ECFDF5")),
        ("BACKGROUND", (1,1), (1,1), HexColor("#FFFBEB")),
        ("BACKGROUND", (2,1), (2,1), HexColor("#ECFDF5")),
        ("BOX", (0,0), (0,-1), 0.8, HexColor("#047857")),
        ("BOX", (1,0), (1,-1), 0.8, HexColor("#C9A961")),
        ("BOX", (2,0), (2,-1), 1.2, HexColor("#047857")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(odd_table)
    story.append(Spacer(1, 4))

    # Cenários completos (P home / draw / away)
    rule = (
        f"<font color='#525252' size='8'>"
        f"P({home}) <b>{prob_home:.0f}%</b> · "
        f"P(empate) <b>{prob_draw:.0f}%</b> · "
        f"P({away}) <b>{prob_away:.0f}%</b>"
        f"</font>"
    )
    p_meta = ParagraphStyle("pmeta", parent=base["Normal"],
                              fontName="Helvetica", fontSize=8,
                              alignment=TA_CENTER,
                              textColor=COLOR_GRAY_DARK)
    story.append(Paragraph(rule, p_meta))
    story.append(Spacer(1, 8))

    # Por que entrou
    story.append(Paragraph("◆ POR QUE ENTROU", st_sec))
    motivo = (
        f"{team} tem dominância clara: <b>{m['cc']} chances claras</b>, "
        f"xG <b>{m['xg']:.2f}</b>, xGOT <b>{m['xgot']:.2f}</b>, "
        f"{m['shots']} finalizações ({m['sot_pct']*100:.0f}% no alvo). "
        f"Posse <b>{m['posse']:.0f}%</b>, "
        f"<b>{m['toq']:.0f} toques na área</b> contra {m['toq_opp']:.0f} do adversário."
    )
    story.append(Paragraph(motivo, st_body))

    # Tese
    story.append(Paragraph("◆ TESE OPERACIONAL", st_sec))
    tese_text = (
        f"Modelo estima <b>{prob_target:.0f}% de probabilidade</b> do "
        f"{team} vencer (Poisson sobre xG remaining ajustado por cenário). "
        f"Odd justa é <b>{fair_odd:.2f}</b>. Com margem de segurança de 8% "
        f"sobre erro de modelo, só vale entrar se odd de mercado for "
        f"<b>≥ {min_odd:.2f}</b>. "
        f"Adversário tem pouca produção (xG {m['opp_xg']:.2f}) — risco "
        f"contrário baixo no momento."
    )
    story.append(Paragraph(tese_text, st_body))

    # Stake sugerido
    story.append(Spacer(1, 8))
    stake_box = Table(
        [[Paragraph("STAKE SUGERIDO · 1u–2u (risco moderado)", st_alert_label)]],
        colWidths=[doc.width - 4*mm],
    )
    stake_box.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), HexColor("#FAFAF5")),
        ("LINEABOVE", (0,0), (-1,0), 1.2, HexColor("#C9A961")),
        ("LINEBELOW", (0,-1), (-1,-1), 0.3, HexColor("#C9A961")),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
    ]))
    story.append(stake_box)

    doc.build(story)
    return pdf_path


_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = _ROOT / "logs" / "reports"

# ─── PALETA EXECUTIVA ───────────────────────────────────
COLOR_BLACK = HexColor("#0A0A0A")        # preto absoluto
COLOR_DARK = HexColor("#1A1A1A")
COLOR_GOLD = HexColor("#C9A961")         # dourado fosco (executivo)
COLOR_GOLD_DARK = HexColor("#8B7635")
COLOR_GRAY_DARKEST = HexColor("#2D2D2D")
COLOR_GRAY_DARK = HexColor("#525252")
COLOR_GRAY = HexColor("#737373")
COLOR_GRAY_LIGHT = HexColor("#D4D4D4")
COLOR_GRAY_LIGHTER = HexColor("#F5F5F5")
COLOR_OFFWHITE = HexColor("#FAFAFA")

# Tiers
COLOR_WATCH = HexColor("#1E40AF")        # azul royal
COLOR_FORTE = HexColor("#B45309")        # âmbar profundo
COLOR_PREMIUM = HexColor("#047857")      # esmeralda

# Status / setas
COLOR_GREEN = HexColor("#047857")        # subindo
COLOR_RED = HexColor("#B91C1C")          # caindo
COLOR_NEUTRAL = HexColor("#525252")

# Recomendação
COLOR_REC_BG = HexColor("#FAFAF5")
COLOR_REC_BORDER = COLOR_GOLD


# ─── HELPERS ────────────────────────────────────────────
def _bloc_full(b: int) -> str:
    return {15: "Bloco 1 · 0–15 min",
             30: "Bloco 2 · 15–30 min",
             45: "Intervalo · 1º Tempo",
             60: "Bloco 4 · 45–60 min",
             75: "Bloco 5 · 60–75 min",
             90: "Final · Jogo encerrado"}.get(b, f"Min {b}")


def _next_label(minute: int) -> str:
    if minute < 30: return "PRÓXIMA LEITURA · MIN 30"
    if minute < 45: return "PRÓXIMA LEITURA · INTERVALO (MIN 45)"
    if minute < 60: return "PRÓXIMA LEITURA · MIN 60"
    if minute < 75: return "PRÓXIMA LEITURA · MIN 75"
    if minute < 90: return "PRÓXIMA LEITURA · FINAL (MIN 90)"
    return "JOGO ENCERRADO"


def _tier_color(tier):
    return {"PREMIUM": COLOR_PREMIUM, "FORTE": COLOR_FORTE,
            "WATCH": COLOR_WATCH}.get(tier, COLOR_GRAY)


# ─── PAGE FRAME / CABEÇALHO / RODAPÉ ────────────────────
def _draw_header_footer(canv, doc):
    """Faixa preta no topo + linha dourada + footer corporativo."""
    pw, ph = PAGE_SIZE

    # Top bar preta
    canv.saveState()
    canv.setFillColor(COLOR_BLACK)
    canv.rect(0, ph - 10*mm, pw, 10*mm, fill=1, stroke=0)

    # Brand
    canv.setFillColor(COLOR_GOLD)
    canv.setFont("Helvetica-Bold", 8)
    canv.drawString(10*mm, ph - 6.5*mm, "▌ TRADER REGRA 3.1.2.0")

    # Timestamp à direita
    ts = datetime.now().strftime("%H:%M · %d %b %Y").upper()
    canv.setFillColor(COLOR_GRAY_LIGHT)
    canv.setFont("Helvetica", 7)
    canv.drawRightString(pw - 10*mm, ph - 6.5*mm, ts)

    # Linha dourada fina
    canv.setFillColor(COLOR_GOLD)
    canv.rect(0, ph - 10*mm - 0.5, pw, 0.5, fill=1, stroke=0)

    # ─── Footer ───
    fy = 8*mm
    canv.setFillColor(COLOR_GRAY_LIGHT)
    canv.rect(10*mm, fy + 4*mm, pw - 20*mm, 0.3, fill=1, stroke=0)

    canv.setFillColor(COLOR_GRAY_DARK)
    canv.setFont("Helvetica-Bold", 6.5)
    canv.drawString(10*mm, fy, FOOTER_BRAND)
    canv.setFillColor(COLOR_GRAY)
    canv.setFont("Helvetica", 6.5)
    # Página centralizada
    try:
        page_num = canv.getPageNumber()
        canv.drawCentredString(pw/2, fy, f"Página {page_num}")
    except Exception:
        pass
    canv.drawRightString(pw - 10*mm, fy, FOOTER_RIGHT)
    canv.restoreState()


def build_block_report_pdf(ms_dict: dict, score_result: dict,
                            scenario: dict, ctx: dict,
                            block: int, narrative: dict,
                            score_history: list = None,
                            derivatives: dict = None,
                            trend: dict = None,
                            markets: dict = None,
                            validation: dict = None) -> Path:
    """Gera PDF executivo do bloco. Retorna caminho."""
    home = ms_dict.get("home", "?")
    away = ms_dict.get("away", "?")
    h_g = ms_dict.get("home_score", 0); a_g = ms_dict.get("away_score", 0)
    minute = ms_dict.get("minute", 0)
    mid = ms_dict.get("match_id", "match")
    tier = score_result.get("tier")
    score = score_result.get("score", 0.0) or 0.0

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%H%M%S")
    safe_mid = str(mid).replace("/", "_").replace(":", "_")
    pdf_path = REPORTS_DIR / f"{safe_mid}_b{block}_{ts}.pdf"

    doc = BaseDocTemplate(
        str(pdf_path),
        pagesize=PAGE_SIZE,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=20*mm, bottomMargin=18*mm,
        title=f"{home} vs {away} — {_bloc_full(block)}",
        author="Trader Regra 3.1.2.0",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                   doc.width, doc.height, id="main", showBoundary=0)
    template = PageTemplate(id="exec", frames=[frame],
                              onPage=_draw_header_footer)
    doc.addPageTemplates([template])

    # ─── ESTILOS ───
    base = getSampleStyleSheet()

    st_score_label = ParagraphStyle(
        "scoreLabel", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=7, leading=9,
        textColor=COLOR_GRAY, alignment=TA_LEFT, spaceAfter=3,
    )
    st_teams = ParagraphStyle(
        "teams", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=14, leading=17,
        textColor=COLOR_BLACK, alignment=TA_LEFT, spaceAfter=2,
    )
    st_meta = ParagraphStyle(
        "meta", parent=base["Normal"],
        fontName="Helvetica", fontSize=8, leading=10,
        textColor=COLOR_GRAY, alignment=TA_LEFT, spaceAfter=6,
    )
    st_section = ParagraphStyle(
        "section", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=7.5, leading=10,
        textColor=COLOR_GOLD_DARK, alignment=TA_LEFT,
        spaceBefore=10, spaceAfter=4,
        # tracking simulado com espaço entre letras seria ideal
    )
    st_body = ParagraphStyle(
        "body", parent=base["BodyText"],
        fontName="Helvetica", fontSize=9.5, leading=13,
        textColor=COLOR_DARK, alignment=TA_LEFT, spaceAfter=3,
    )
    st_rec_label = ParagraphStyle(
        "recLabel", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=7, leading=9,
        textColor=COLOR_GOLD_DARK, alignment=TA_LEFT, spaceAfter=2,
    )
    st_rec = ParagraphStyle(
        "rec", parent=base["BodyText"],
        fontName="Helvetica-Bold", fontSize=10.5, leading=14,
        textColor=COLOR_BLACK, alignment=TA_LEFT, spaceAfter=2,
    )
    st_next = ParagraphStyle(
        "next", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=7, leading=9,
        textColor=COLOR_GRAY, alignment=TA_CENTER, spaceBefore=6,
    )
    st_tier_badge = ParagraphStyle(
        "tierBadge", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=9, leading=11,
        textColor=white, alignment=TA_CENTER,
    )

    story = []

    # ═══════════════════════════════════════════════════
    # CABEÇALHO DO MATCH
    # ═══════════════════════════════════════════════════
    story.append(Paragraph("ANÁLISE TÁTICA · BLOCO FECHADO", st_score_label))
    # Placar acumulado (estado atual do jogo)
    h_g_acc = ms_dict.get("home_score_acc", h_g)
    a_g_acc = ms_dict.get("away_score_acc", a_g)
    h_g_block = ms_dict.get("home_score_block", None)
    a_g_block = ms_dict.get("away_score_block", None)
    score_text = f"{home}  <font color='#C9A961'>{h_g_acc} — {a_g_acc}</font>  {away}"
    story.append(Paragraph(score_text, st_teams))
    # Indicador de gols feitos NO BLOCO
    if h_g_block is not None and a_g_block is not None:
        if h_g_block + a_g_block > 0:
            gols_block = (
                f"NESTE BLOCO: <b>{h_g_block}</b> gol(s) {home[:14]} · "
                f"<b>{a_g_block}</b> gol(s) {away[:14]}"
            )
        else:
            gols_block = "NESTE BLOCO: nenhum gol"
        story.append(Paragraph(gols_block, st_meta))
    story.append(Paragraph(
        f"{_bloc_full(block).upper()} · MINUTO {minute}", st_meta))

    # ─── Tier badge (se houver) ───
    if tier:
        badge_text = f"{tier} · {score:.0f}/100"
        badge_table = Table(
            [[Paragraph(badge_text, st_tier_badge)]],
            colWidths=[42*mm], rowHeights=[6*mm],
        )
        badge_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), _tier_color(tier)),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("BOX", (0,0), (-1,-1), 0, white),
            ("LEFTPADDING", (0,0), (-1,-1), 0),
            ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ]))
        story.append(badge_table)

    # Divisor dourado fino
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.5,
                              color=COLOR_GOLD, spaceBefore=0, spaceAfter=4))

    # ═══════════════════════════════════════════════════
    # O QUE ROLOU NO BLOCO
    # ═══════════════════════════════════════════════════
    story.append(Paragraph("◆ O QUE ROLOU NO BLOCO", st_section))
    story.append(Paragraph(narrative.get("rolou", "—"), st_body))

    # ═══════════════════════════════════════════════════
    # LEITURA TÁTICA
    # ═══════════════════════════════════════════════════
    story.append(Paragraph("◆ LEITURA TÁTICA", st_section))
    story.append(Paragraph(narrative.get("leitura", "—"), st_body))

    # ═══════════════════════════════════════════════════
    # EVOLUÇÃO
    # ═══════════════════════════════════════════════════
    evol_html = _format_evolution_html(
        derivatives or {}, score, score_history or [])
    if evol_html:
        story.append(Paragraph("◆ EVOLUÇÃO vs BLOCO ANTERIOR", st_section))
        story.append(Paragraph(evol_html, st_body))

    # ═══════════════════════════════════════════════════
    # TENDÊNCIA TÁTICA + MERCADO (NOVO)
    # ═══════════════════════════════════════════════════
    if trend and trend.get("trend") and trend.get("trend") != "INDEF":
        story.append(Paragraph("◆ TENDÊNCIA TÁTICA", st_section))
        story.append(Paragraph(trend.get("narrative", ""), st_body))

        # Mercado recomendado em destaque
        if trend.get("market_label"):
            conf = trend.get("confidence", "?").upper()
            mkt_label = trend["market_label"]
            # Buscar probabilidade do mercado
            prob_str = ""
            fair_str = ""
            if markets:
                mk_key = trend.get("market")
                _map = {
                    "OVER_2_5": ("p_over_25", "fair_over_25"),
                    "OVER_3_5": ("p_over_35", "fair_over_35"),
                    "UNDER_2_5": ("p_under_25", "fair_under_25"),
                    "BTS_SIM": ("p_bts_yes", "fair_bts_yes"),
                    "BACK_HOME": ("p_home", "fair_home"),
                    "BACK_AWAY": ("p_away", "fair_away"),
                    "NEXT_GOAL_HOME": ("p_next_home", "fair_next_home"),
                    "NEXT_GOAL_AWAY": ("p_next_away", "fair_next_away"),
                    # Handicaps
                    "HCP_HOME_-1.5": ("p_hcp_home_15", "fair_hcp_home_15"),
                    "HCP_HOME_-2.5": ("p_hcp_home_25", "fair_hcp_home_25"),
                    "HCP_HOME_-3.5": ("p_hcp_home_35", "fair_hcp_home_35"),
                    "HCP_HOME_-4.5": ("p_hcp_home_45", "fair_hcp_home_45"),
                    "HCP_AWAY_-1.5": ("p_hcp_away_15", "fair_hcp_away_15"),
                    "HCP_AWAY_-2.5": ("p_hcp_away_25", "fair_hcp_away_25"),
                    "HCP_AWAY_-3.5": ("p_hcp_away_35", "fair_hcp_away_35"),
                    "HCP_AWAY_-4.5": ("p_hcp_away_45", "fair_hcp_away_45"),
                }
                pk, fk = _map.get(mk_key, (None, None))
                if pk and pk in markets:
                    prob_str = f"{markets[pk]:.0f}%"
                    fair_str = f"{markets[fk]:.2f}"

            market_text = (
                f"<font color='#047857'><b>MERCADO: {mkt_label}</b></font>"
            )
            if prob_str:
                market_text += f" · Prob: <b>{prob_str}</b> · Odd justa: <b>{fair_str}</b>"
            market_text += f" · Confiança: <b>{conf}</b>"
            story.append(Paragraph(market_text, st_body))

        # Validação por blocos
        if validation and validation.get("evidence"):
            status = validation.get("status", "em_andamento")
            status_label = {
                "confirmou": "<font color='#047857'>✓ TESE CONFIRMOU</font>",
                "refutou": "<font color='#B91C1C'>✗ TESE REFUTOU</font>",
                "em_andamento": "<font color='#525252'>⏳ TESE EM CURSO</font>",
            }.get(status, status)
            story.append(Paragraph(
                f"<b>Validação vs bloco anterior:</b> {status_label}", st_body))
            for ev in validation["evidence"]:
                story.append(Paragraph(f"• {ev}", st_body))

    # ═══════════════════════════════════════════════════
    # MÉTRICAS — produção DO BLOCO + estado ATUAL
    # ═══════════════════════════════════════════════════
    tbl_block, tbl_state = _build_data_tables(home, away, ms_dict, ctx)
    # ✨ v4.6 — KeepTogether: protege tabelas contra quebra entre páginas
    story.append(KeepTogether([
        Paragraph("◆ PRODUÇÃO NESTE BLOCO (15 min)", st_section),
        tbl_block,
    ]))
    story.append(Spacer(1, 6))
    story.append(KeepTogether([
        Paragraph("◆ ESTADO ATUAL DO JOGO", st_section),
        tbl_state,
    ]))

    # ═══════════════════════════════════════════════════
    # RECOMENDAÇÃO (caixa premium)
    # ═══════════════════════════════════════════════════
    story.append(Spacer(1, 10))
    rec_box = Table(
        [[Paragraph("RECOMENDAÇÃO OPERACIONAL", st_rec_label)],
         [Paragraph(narrative.get("recomendacao", "—"), st_rec)]],
        colWidths=[doc.width - 4*mm],
    )
    rec_box.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), COLOR_REC_BG),
        ("LINEABOVE", (0,0), (-1,0), 1.2, COLOR_GOLD),
        ("LINEBELOW", (0,-1), (-1,-1), 0.3, COLOR_GOLD),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("TOPPADDING", (0,0), (-1,0), 8),
        ("BOTTOMPADDING", (0,0), (-1,0), 0),
        ("TOPPADDING", (0,1), (-1,1), 0),
        ("BOTTOMPADDING", (0,-1), (-1,-1), 10),
    ]))
    story.append(KeepTogether(rec_box))

    # ═══════════════════════════════════════════════════
    # PRÓXIMA LEITURA
    # ═══════════════════════════════════════════════════
    story.append(Paragraph(_next_label(minute), st_next))

    doc.build(story)
    return pdf_path


# ─── EVOLUÇÃO ───────────────────────────────────────────
def _format_evolution_html(derivatives: dict, current_score: float,
                            history: list) -> str:
    """HTML inline (Paragraph) com setas coloridas."""
    parts = []

    if history and len(history) >= 2:
        delta = current_score - history[-2]
        if abs(delta) >= 5:
            if delta > 0:
                parts.append(
                    f"<font color='#047857'>▲</font> "
                    f"<b>Score do jogo</b> +{delta:.0f} pontos")
            else:
                parts.append(
                    f"<font color='#B91C1C'>▼</font> "
                    f"<b>Score do jogo</b> {delta:.0f} pontos")

    LABEL = {
        "home_cc": "CC casa", "away_cc": "CC fora",
        "home_xg": "xG casa", "away_xg": "xG fora",
        "home_xgot": "xGOT casa", "away_xgot": "xGOT fora",
        "home_shots": "Finalizações casa",
        "away_shots": "Finalizações fora",
        "home_sot": "SOT casa", "away_sot": "SOT fora",
    }
    deltas = []
    for m, label in LABEL.items():
        d = derivatives.get(m, {})
        delta = d.get("delta_15m", 0)
        if abs(delta) >= 0.5:
            deltas.append((abs(delta), label, delta))
    deltas.sort(reverse=True)

    for _, label, val in deltas[:3]:
        if val > 0:
            parts.append(
                f"<font color='#047857'>▲</font> "
                f"<b>{label}</b> +{val:.1f}")
        else:
            parts.append(
                f"<font color='#B91C1C'>▼</font> "
                f"<b>{label}</b> {val:.1f}")

    return "&nbsp;&nbsp;·&nbsp;&nbsp;".join(parts) if parts else ""


# ─── TABELA EXECUTIVA ───────────────────────────────────
def _build_data_tables(home: str, away: str, ms_dict: dict, ctx: dict):
    """Retorna 2 tabelas: produção DO BLOCO e ESTADO ATUAL do jogo."""
    h_short = home[:18]
    a_short = away[:18]
    posse_h, posse_a = ctx.get("posse", (0, 0))
    toq_h, toq_a = ctx.get("toques_area", (0, 0))
    h_xg = ms_dict.get("home_xg", 0); a_xg = ms_dict.get("away_xg", 0)
    h_xgot = ms_dict.get("home_xgot", 0); a_xgot = ms_dict.get("away_xgot", 0)
    h_xa = ms_dict.get("home_xa", 0); a_xa = ms_dict.get("away_xa", 0)
    h_cc = ms_dict.get("home_cc", 0); a_cc = ms_dict.get("away_cc", 0)
    h_sh = ms_dict.get("home_shots", 0); a_sh = ms_dict.get("away_shots", 0)
    h_sot = ms_dict.get("home_sot", 0); a_sot = ms_dict.get("away_sot", 0)
    h_g_block = ms_dict.get("home_score_block", 0)
    a_g_block = ms_dict.get("away_score_block", 0)
    # Acumulados do jogo
    h_xg_acc = ms_dict.get("home_xg_acc", h_xg)
    a_xg_acc = ms_dict.get("away_xg_acc", a_xg)
    h_xgot_acc = ms_dict.get("home_xgot_acc", h_xgot)
    a_xgot_acc = ms_dict.get("away_xgot_acc", a_xgot)
    h_cc_acc = ms_dict.get("home_cc_acc", h_cc)
    a_cc_acc = ms_dict.get("away_cc_acc", a_cc)
    h_sh_acc = ms_dict.get("home_shots_acc", h_sh)
    a_sh_acc = ms_dict.get("away_shots_acc", a_sh)
    h_sot_acc = ms_dict.get("home_sot_acc", h_sot)
    a_sot_acc = ms_dict.get("away_sot_acc", a_sot)
    h_g_acc = ms_dict.get("home_score_acc", ms_dict.get("home_score", 0))
    a_g_acc = ms_dict.get("away_score_acc", ms_dict.get("away_score", 0))

    def _bold_winner(val_h, val_a, fmt="{:.0f}"):
        if isinstance(val_h, (int, float)) and isinstance(val_a, (int, float)):
            if val_h > val_a:
                return (f"<b>{fmt.format(val_h)}</b>", fmt.format(val_a))
            elif val_a > val_h:
                return (fmt.format(val_h), f"<b>{fmt.format(val_a)}</b>")
        return (fmt.format(val_h), fmt.format(val_a))

    cell_style = ParagraphStyle(
        "cell", parent=getSampleStyleSheet()["Normal"],
        fontName="Helvetica", fontSize=8.5, leading=11,
        textColor=COLOR_DARK, alignment=TA_CENTER,
    )
    metric_style = ParagraphStyle(
        "metric", parent=getSampleStyleSheet()["Normal"],
        fontName="Helvetica", fontSize=8.5, leading=11,
        textColor=COLOR_GRAY_DARK, alignment=TA_LEFT,
    )
    header_style = ParagraphStyle(
        "metricH", parent=getSampleStyleSheet()["Normal"],
        fontName="Helvetica-Bold", fontSize=7.5, leading=10,
        textColor=white, alignment=TA_CENTER,
    )
    def P(v): return Paragraph(str(v), cell_style)
    def M(v): return Paragraph(v, metric_style)
    def H(v): return Paragraph(v, header_style)

    def _style_for(rows_count):
        return TableStyle([
            ("BACKGROUND", (0,0), (-1,0), COLOR_BLACK),
            ("TEXTCOLOR", (0,0), (-1,0), white),
            ("TOPPADDING", (0,0), (-1,0), 6),
            ("BOTTOMPADDING", (0,0), (-1,0), 6),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING", (0,1), (-1,-1), 5),
            ("BOTTOMPADDING", (0,1), (-1,-1), 5),
            ("LEFTPADDING", (0,0), (0,-1), 10),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [COLOR_OFFWHITE, white]),
            ("LINEBELOW", (0,1), (-1,-2), 0.25, COLOR_GRAY_LIGHT),
            ("LINEBELOW", (0,-1), (-1,-1), 0.8, COLOR_GOLD),
        ])

    # ─── TABELA 1: PRODUÇÃO NO BLOCO (delta) ───
    block_rows = [
        [H("PRODUÇÃO NO BLOCO"), H(h_short.upper()), H(a_short.upper())],
        [M("Gols neste bloco"), P(f"{h_g_block}"), P(f"{a_g_block}")],
        [M("Finalizações"), *[P(x) for x in _bold_winner(h_sh, a_sh)]],
        [M("No alvo (SOT)"), *[P(x) for x in _bold_winner(h_sot, a_sot)]],
        [M("Chances claras"), *[P(x) for x in _bold_winner(h_cc, a_cc)]],
        [M("xG"), *[P(x) for x in _bold_winner(h_xg, a_xg, "{:.2f}")]],
        [M("xGOT"), *[P(x) for x in _bold_winner(h_xgot, a_xgot, "{:.2f}")]],
        [M("xA"), *[P(x) for x in _bold_winner(h_xa, a_xa, "{:.2f}")]],
    ]
    tbl_block = Table(block_rows, colWidths=[55*mm, 32*mm, 32*mm])
    tbl_block.setStyle(_style_for(len(block_rows)))

    # ─── TABELA 2: ESTADO ATUAL DO JOGO (acumulado) ───
    state_rows = [
        [H("ACUMULADO DO JOGO"), H(h_short.upper()), H(a_short.upper())],
        [M("Placar"), P(f"<b>{h_g_acc}</b>"), P(f"<b>{a_g_acc}</b>")],
        [M("Posse de bola"), P(f"{posse_h:.0f}%"), P(f"{posse_a:.0f}%")],
        [M("Toques na área adv."), *[P(x) for x in _bold_winner(toq_h, toq_a)]],
        [M("Finalizações total"), *[P(x) for x in _bold_winner(h_sh_acc, a_sh_acc)]],
        [M("SOT total"), *[P(x) for x in _bold_winner(h_sot_acc, a_sot_acc)]],
        [M("CC total"), *[P(x) for x in _bold_winner(h_cc_acc, a_cc_acc)]],
        [M("xG total"), *[P(x) for x in _bold_winner(h_xg_acc, a_xg_acc, "{:.2f}")]],
        [M("xGOT total"), *[P(x) for x in _bold_winner(h_xgot_acc, a_xgot_acc, "{:.2f}")]],
    ]
    tbl_state = Table(state_rows, colWidths=[55*mm, 32*mm, 32*mm])
    tbl_state.setStyle(_style_for(len(state_rows)))

    return tbl_block, tbl_state


def _metrics_table(home: str, away: str, ms_dict: dict, ctx: dict) -> Table:
    """LEGADO — agora só a tabela do bloco. Use _build_data_tables pra ter ambas."""
    tbl_block, _ = _build_data_tables(home, away, ms_dict, ctx)
    return tbl_block
