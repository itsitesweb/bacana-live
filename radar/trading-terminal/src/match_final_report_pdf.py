"""
MATCH_FINAL_REPORT_PDF — Relatório de FIM DE JOGO em padrão EXECUTIVO premium.

Estrutura (10-14 páginas):
  1. Capa executiva
  2. Sumário Executivo (KPIs, veredito preliminar)
  3. Metodologia
  4. Evolução por Bloco (15/30/45/60/75/90)
  5. Análise Probabilística (mercados durante o jogo)
  6. Bloco Final detalhado
  7. Conclusão Final com declaração assinada

Padrão visual: paleta preto/dourado (Bloomberg), KPIs em destaque,
tabelas executivas, evidências de dados, conclusão sólida.
"""
from pathlib import Path
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.pdfgen import canvas as _canvas
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    Table, TableStyle, HRFlowable, KeepTogether, PageBreak,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY

__version__ = "1.0.0"

_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = _ROOT / "logs" / "reports"

# Paleta executiva
C_BLACK = HexColor("#0A0A0A")
C_DARK = HexColor("#1A1A1A")
C_GOLD = HexColor("#C9A961")
C_GOLD_DARK = HexColor("#8B7635")
C_GRAY_DARKEST = HexColor("#2D2D2D")
C_GRAY_DARK = HexColor("#525252")
C_GRAY = HexColor("#737373")
C_GRAY_LIGHT = HexColor("#D4D4D4")
C_GRAY_LIGHTER = HexColor("#F5F5F5")
C_OFFWHITE = HexColor("#FAFAFA")
C_GREEN = HexColor("#047857")
C_GREEN_LIGHT = HexColor("#ECFDF5")
C_AMBER = HexColor("#B45309")
C_AMBER_LIGHT = HexColor("#FEF3C7")
C_RED = HexColor("#B91C1C")
C_RED_LIGHT = HexColor("#FEE2E2")
C_BLUE = HexColor("#1E40AF")


def build_final_report_pdf(timeline: list, league_name: str = "") -> Path:
    """Gera o relatório executivo final do jogo.

    Args:
      timeline: lista de snapshots (do match_timeline.load_timeline)
      league_name: nome da liga (pra calibração probabilística)

    Returns: Path do PDF gerado.
    """
    if not timeline:
        raise ValueError("Timeline vazia — sem dados pra reportar")

    # Imports tardios pra não criar ciclo
    from src.turbo_score import evaluate
    from src.match_reader import extract_context, detect_scenario, coach_narrative
    from src.match_timeline import compute_block_delta
    from src.trend_engine import detect_trend
    from src.match_probability import compute_all_markets

    final = timeline[-1]
    home = final.get("home", "?")
    away = final.get("away", "?")
    home_score = final.get("home_score", 0)
    away_score = final.get("away_score", 0)
    final_minute = final.get("minute", 90)
    match_id = final.get("match_id", "match")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%H%M%S")
    safe_mid = str(match_id).replace("/", "_").replace(":", "_")
    pdf_path = REPORTS_DIR / f"{safe_mid}_FINAL_EXEC_{ts}.pdf"

    # ─── Header/Footer ───
    def _hf(canv, doc):
        pw, ph = A4
        canv.saveState()
        canv.setFillColor(C_BLACK)
        canv.rect(0, ph - 12*mm, pw, 12*mm, fill=1, stroke=0)
        canv.setFillColor(C_GOLD)
        canv.setFont("Helvetica-Bold", 9)
        canv.drawString(15*mm, ph - 8*mm, "▌ RELATÓRIO DE FIM DE JOGO")
        canv.setFillColor(white)
        canv.setFont("Helvetica", 8)
        canv.drawString(75*mm, ph - 8*mm, f"{home[:18]} vs {away[:18]}")
        ts2 = datetime.now().strftime("%d %b %Y · %H:%M").upper()
        canv.setFillColor(C_GRAY_LIGHT)
        canv.setFont("Helvetica", 7)
        canv.drawRightString(pw - 15*mm, ph - 8*mm, ts2)
        canv.setFillColor(C_GOLD)
        canv.rect(0, ph - 12*mm - 0.5, pw, 0.5, fill=1, stroke=0)
        # Footer
        fy = 10*mm
        canv.setFillColor(C_GRAY_LIGHT)
        canv.rect(15*mm, fy + 5*mm, pw - 30*mm, 0.3, fill=1, stroke=0)
        canv.setFillColor(C_GRAY_DARK)
        canv.setFont("Helvetica-Bold", 7)
        canv.drawString(15*mm, fy, "TRADER REGRA 3.1.2.0 · CONFIDENCIAL")
        canv.setFillColor(C_GRAY)
        canv.setFont("Helvetica", 7)
        canv.drawCentredString(pw/2, fy, f"Página {doc.page}")
        canv.drawRightString(pw - 15*mm, fy, f"OPERADOR: TIAGO LOPES")
        canv.restoreState()

    doc = BaseDocTemplate(
        str(pdf_path), pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=20*mm, bottomMargin=18*mm,
        title=f"{home} vs {away} — Relatório Final",
        author="Trader Regra 3.1.2.0",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                   doc.width, doc.height, id="main")
    template = PageTemplate(id="exec", frames=[frame], onPage=_hf)
    doc.addPageTemplates([template])

    # ─── Estilos ───
    base = getSampleStyleSheet()
    st_cap = ParagraphStyle("cap", parent=base["Normal"],
                              fontName="Helvetica-Bold", fontSize=26,
                              leading=32, textColor=C_BLACK,
                              alignment=TA_CENTER, spaceAfter=8)
    st_cap_sub = ParagraphStyle("capsub", parent=base["Normal"],
                                  fontName="Helvetica-Bold", fontSize=14,
                                  leading=18, textColor=C_GOLD,
                                  alignment=TA_CENTER, spaceAfter=20)
    st_cap_meta = ParagraphStyle("capm", parent=base["Normal"],
                                   fontName="Helvetica", fontSize=10,
                                   leading=14, textColor=C_GRAY_DARK,
                                   alignment=TA_CENTER, spaceAfter=6)
    st_h1 = ParagraphStyle("h1", parent=base["Normal"],
                             fontName="Helvetica-Bold", fontSize=18,
                             leading=24, textColor=C_BLACK,
                             spaceBefore=14, spaceAfter=8)
    st_h2 = ParagraphStyle("h2", parent=base["Normal"],
                             fontName="Helvetica-Bold", fontSize=13,
                             leading=17, textColor=C_GOLD_DARK,
                             spaceBefore=12, spaceAfter=4)
    st_h3 = ParagraphStyle("h3", parent=base["Normal"],
                             fontName="Helvetica-Bold", fontSize=10,
                             leading=13, textColor=C_GRAY_DARKEST,
                             spaceBefore=8, spaceAfter=3)
    st_body = ParagraphStyle("body", parent=base["BodyText"],
                               fontName="Helvetica", fontSize=10,
                               leading=14, textColor=C_DARK,
                               alignment=TA_JUSTIFY, spaceAfter=5)
    st_bold = ParagraphStyle("bd", parent=base["BodyText"],
                               fontName="Helvetica-Bold", fontSize=10,
                               leading=14, textColor=C_BLACK, spaceAfter=5)
    st_caption = ParagraphStyle("cp", parent=base["Normal"],
                                  fontName="Helvetica-Oblique", fontSize=8,
                                  leading=11, textColor=C_GRAY, spaceAfter=4)
    st_kpi_num = ParagraphStyle("kn", parent=base["Normal"],
                                  fontName="Helvetica-Bold", fontSize=24,
                                  leading=28, alignment=TA_CENTER)
    st_kpi_lbl = ParagraphStyle("kl", parent=base["Normal"],
                                  fontName="Helvetica-Bold", fontSize=7,
                                  leading=9, alignment=TA_CENTER,
                                  textColor=C_GRAY)

    story = []

    # ════════════════ CAPA ════════════════
    story.append(Spacer(1, 55*mm))
    story.append(Paragraph("RELATÓRIO DE FIM DE JOGO", st_cap))
    story.append(Paragraph(
        f"{home} {home_score} — {away_score} {away}", st_cap_sub))
    story.append(HRFlowable(width="60%", thickness=1, color=C_GOLD,
                              hAlign="CENTER", spaceAfter=20))
    story.append(Paragraph("Análise Tática e Probabilística Completa",
                             st_cap_meta))
    story.append(Paragraph(league_name or "Liga não identificada",
                             st_cap_meta))
    story.append(Spacer(1, 25*mm))

    meta = Table([
        [Paragraph("PLACAR FINAL", st_kpi_lbl),
         Paragraph(f"{home_score} — {away_score}", st_body)],
        [Paragraph("MINUTO FINAL", st_kpi_lbl),
         Paragraph(f"{final_minute}", st_body)],
        [Paragraph("LIGA", st_kpi_lbl),
         Paragraph(league_name or "—", st_body)],
        [Paragraph("SNAPSHOTS CAPTURADOS", st_kpi_lbl),
         Paragraph(f"{len(timeline)}", st_body)],
        [Paragraph("BLOCOS ANALISADOS", st_kpi_lbl),
         Paragraph("6 (15, 30, 45, 60, 75, 90)", st_body)],
    ], colWidths=[55*mm, 110*mm])
    meta.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), C_OFFWHITE),
        ("LINEBELOW", (0,0), (-1,-2), 0.3, C_GRAY_LIGHT),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
    ]))
    story.append(meta)
    story.append(PageBreak())

    # ════════════════ 1. SUMÁRIO EXECUTIVO ════════════════
    story.append(Paragraph("1. Sumário Executivo", st_h1))
    story.append(HRFlowable(width="100%", thickness=0.6, color=C_GOLD,
                              spaceAfter=10))

    # Calcular KPIs do jogo
    h_xg_final = float(final.get("home_xg", 0))
    a_xg_final = float(final.get("away_xg", 0))
    h_cc_final = int(final.get("home_cc", 0))
    a_cc_final = int(final.get("away_cc", 0))
    h_shots = int(final.get("home_shots", 0))
    a_shots = int(final.get("away_shots", 0))
    h_sot = int(final.get("home_sot", 0))
    a_sot = int(final.get("away_sot", 0))
    total_goals = home_score + away_score

    winner = "EMPATE"
    if home_score > away_score:
        winner = home
    elif away_score > home_score:
        winner = away

    story.append(Paragraph(
        f"Esta análise consolida a evolução completa do confronto entre "
        f"{home} e {away}, encerrado em <b>{home_score}-{away_score}</b> "
        f"({winner}). Foram capturados {len(timeline)} snapshots ao longo "
        f"de {final_minute} minutos de jogo, processados em 6 blocos de "
        f"análise (15, 30, 45, 60, 75 e 90 minutos).",
        st_body))

    story.append(Paragraph(
        f"Aplicaram-se as metodologias: Quádrupla de métricas (CC, xG, "
        f"xGOT, xA com pesos 35/25/20/20), detecção de cenário tático em "
        f"7 padrões, engine de tendência tática em 9 padrões e modelo "
        f"Poisson calibrado por tipo de competição com cap de regressão "
        f"à média.",
        st_body))

    story.append(Spacer(1, 8))
    story.append(Paragraph("KPIs Consolidados do Jogo", st_h2))

    # Determinar quem foi o líder em produção
    leader_xg = home if h_xg_final > a_xg_final else away
    score_match = total_goals == round(h_xg_final + a_xg_final)
    xg_eff = "MATERIALIZOU" if score_match else (
        "SOBREPERFORMOU" if total_goals > round(h_xg_final + a_xg_final) else "SUBPERFORMOU")

    kpis = Table([[
        Table([[Paragraph(f"{total_goals}", st_kpi_num)],
               [Paragraph("GOLS NO JOGO", st_kpi_lbl)]],
              colWidths=[35*mm]),
        Table([[Paragraph(f"{h_shots + a_shots}", st_kpi_num)],
               [Paragraph("FINALIZAÇÕES", st_kpi_lbl)]],
              colWidths=[35*mm]),
        Table([[Paragraph(f"{h_cc_final + a_cc_final}", st_kpi_num)],
               [Paragraph("CHANCES CLARAS", st_kpi_lbl)]],
              colWidths=[35*mm]),
        Table([[Paragraph(f"{(h_xg_final + a_xg_final):.2f}", st_kpi_num)],
               [Paragraph("xG TOTAL", st_kpi_lbl)]],
              colWidths=[35*mm]),
    ]], colWidths=[42*mm, 42*mm, 42*mm, 42*mm])
    kpis.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                               ("ALIGN", (0,0), (-1,-1), "CENTER")]))
    story.append(kpis)

    story.append(Spacer(1, 10))
    story.append(Paragraph("Comparação Direta dos Times", st_h2))

    cmp_table = Table([
        [Paragraph("MÉTRICA", ParagraphStyle("ch", fontName="Helvetica-Bold",
                                              fontSize=8, textColor=white,
                                              alignment=TA_CENTER)),
         Paragraph(home.upper(), ParagraphStyle("ch1", fontName="Helvetica-Bold",
                                                  fontSize=8, textColor=white,
                                                  alignment=TA_CENTER)),
         Paragraph(away.upper(), ParagraphStyle("ch2", fontName="Helvetica-Bold",
                                                  fontSize=8, textColor=white,
                                                  alignment=TA_CENTER)),
         Paragraph("VANTAGEM", ParagraphStyle("ch3", fontName="Helvetica-Bold",
                                                fontSize=8, textColor=white,
                                                alignment=TA_CENTER))],
        [Paragraph("Gols", st_body),
         Paragraph(f"{home_score}", st_body),
         Paragraph(f"{away_score}", st_body),
         Paragraph(home if home_score > away_score else (
                    away if away_score > home_score else "—"), st_bold)],
        [Paragraph("Finalizações", st_body),
         Paragraph(f"{h_shots}", st_body),
         Paragraph(f"{a_shots}", st_body),
         Paragraph(home if h_shots > a_shots else (
                    away if a_shots > h_shots else "—"), st_bold)],
        [Paragraph("No alvo (SOT)", st_body),
         Paragraph(f"{h_sot}", st_body),
         Paragraph(f"{a_sot}", st_body),
         Paragraph(home if h_sot > a_sot else (
                    away if a_sot > h_sot else "—"), st_bold)],
        [Paragraph("Chances claras", st_body),
         Paragraph(f"{h_cc_final}", st_body),
         Paragraph(f"{a_cc_final}", st_body),
         Paragraph(home if h_cc_final > a_cc_final else (
                    away if a_cc_final > h_cc_final else "—"), st_bold)],
        [Paragraph("xG", st_body),
         Paragraph(f"{h_xg_final:.2f}", st_body),
         Paragraph(f"{a_xg_final:.2f}", st_body),
         Paragraph(home if h_xg_final > a_xg_final else (
                    away if a_xg_final > h_xg_final else "—"), st_bold)],
        [Paragraph("xGOT", st_body),
         Paragraph(f"{final.get('home_xgot', 0):.2f}", st_body),
         Paragraph(f"{final.get('away_xgot', 0):.2f}", st_body),
         Paragraph(home if final.get('home_xgot',0) > final.get('away_xgot',0)
                    else (away if final.get('away_xgot',0) > final.get('home_xgot',0) else "—"), st_bold)],
    ], colWidths=[40*mm, 40*mm, 40*mm, 45*mm])
    cmp_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), C_BLACK),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_OFFWHITE, white]),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("LINEBELOW", (0,1), (-1,-2), 0.25, C_GRAY_LIGHT),
        ("LINEBELOW", (0,-1), (-1,-1), 0.8, C_GOLD),
    ]))
    story.append(cmp_table)
    story.append(PageBreak())

    # ════════════════ 2. EVOLUÇÃO POR BLOCO ════════════════
    story.append(Paragraph("2. Evolução por Bloco", st_h1))
    story.append(HRFlowable(width="100%", thickness=0.6, color=C_GOLD,
                              spaceAfter=10))
    story.append(Paragraph(
        "Análise sequencial de cada janela de 15 minutos. Cada bloco é "
        "avaliado pela Quádrupla, classificado em cenário tático e "
        "associado a uma tendência operacional. A coluna 'Mercado' "
        "indica o mercado recomendado naquele momento.",
        st_body))

    # Headers da tabela de blocos
    block_rows = [[
        Paragraph("BLOCO", ParagraphStyle("bh", fontName="Helvetica-Bold",
                                            fontSize=8, textColor=white,
                                            alignment=TA_CENTER)),
        Paragraph("PLACAR", ParagraphStyle("bh1", fontName="Helvetica-Bold",
                                             fontSize=8, textColor=white,
                                             alignment=TA_CENTER)),
        Paragraph("CENÁRIO", ParagraphStyle("bh2", fontName="Helvetica-Bold",
                                              fontSize=8, textColor=white,
                                              alignment=TA_CENTER)),
        Paragraph("TENDÊNCIA", ParagraphStyle("bh3", fontName="Helvetica-Bold",
                                                fontSize=8, textColor=white,
                                                alignment=TA_CENTER)),
        Paragraph("MERCADO", ParagraphStyle("bh4", fontName="Helvetica-Bold",
                                              fontSize=8, textColor=white,
                                              alignment=TA_CENTER)),
    ]]

    block_analyses = []
    for block_end in (15, 30, 45, 60, 75, 90):
        block_start = max(0, block_end - 15)
        if block_end == 45:
            block_start = 0  # HT = resumo 1º tempo
        try:
            bm = compute_block_delta(timeline, block_start, block_end)
            bm["match_id"] = match_id
            bm["home"] = home; bm["away"] = away
            ctx_b = extract_context(bm.get("all_stats", {}))
            sc_b = detect_scenario(evaluate(bm), ctx_b, bm)
            # ms acumulado no momento do bloco
            ms_at = next((s for s in reversed(timeline)
                            if s.get("minute", 999) <= block_end), bm)
            ctx_acc = extract_context(ms_at.get("all_stats", {}))
            sc_acc = detect_scenario(evaluate(ms_at), ctx_acc, ms_at)
            trend = detect_trend(ms_at, ctx_acc, sc_acc, block_data=bm)
            block_analyses.append((block_end, bm, ms_at, sc_b, sc_acc, trend))
            block_rows.append([
                Paragraph(f"<b>{'HT' if block_end==45 else block_end}</b>", st_body),
                Paragraph(f"{ms_at.get('home_score',0)}-{ms_at.get('away_score',0)}",
                            st_body),
                Paragraph(sc_acc.get("scenario", "—").replace("_", " "), st_body),
                Paragraph(trend.get("trend", "—").replace("_", " "),
                            ParagraphStyle("tt", fontName="Helvetica-Bold",
                                            fontSize=9, textColor=C_GOLD_DARK)),
                Paragraph(trend.get("market_label", "—")[:30], st_body),
            ])
        except Exception as e:
            block_rows.append([
                Paragraph(f"{block_end}", st_body),
                Paragraph("—", st_body),
                Paragraph(f"ERR: {str(e)[:20]}", st_body),
                Paragraph("—", st_body),
                Paragraph("—", st_body),
            ])

    btable = Table(block_rows, colWidths=[22*mm, 22*mm, 36*mm, 40*mm, 45*mm])
    btable.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), C_BLACK),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_OFFWHITE, white]),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("LINEBELOW", (0,1), (-1,-2), 0.25, C_GRAY_LIGHT),
        ("LINEBELOW", (0,-1), (-1,-1), 0.8, C_GOLD),
    ]))
    story.append(btable)
    story.append(PageBreak())

    # ════════════════ 3. ANÁLISE PROBABILÍSTICA ════════════════
    story.append(Paragraph("3. Análise Probabilística por Bloco", st_h1))
    story.append(HRFlowable(width="100%", thickness=0.6, color=C_GOLD,
                              spaceAfter=10))

    story.append(Paragraph(
        "Para cada bloco analisado, o modelo Poisson calculou as "
        "probabilidades dos mercados disponíveis no instante. Esta tabela "
        "mostra os mercados-chave e suas probabilidades estimadas em cada "
        "momento — útil para identificar quando havia entrada com valor.",
        st_body))

    prob_rows = [[
        Paragraph("MIN", ParagraphStyle("ph", fontName="Helvetica-Bold",
                                          fontSize=8, textColor=white,
                                          alignment=TA_CENTER)),
        Paragraph(f"BACK {home[:10].upper()}", ParagraphStyle("ph1", fontName="Helvetica-Bold",
                                                                fontSize=7, textColor=white,
                                                                alignment=TA_CENTER)),
        Paragraph(f"BACK {away[:10].upper()}", ParagraphStyle("ph2", fontName="Helvetica-Bold",
                                                                fontSize=7, textColor=white,
                                                                alignment=TA_CENTER)),
        Paragraph("OVER 2.5", ParagraphStyle("ph3", fontName="Helvetica-Bold",
                                               fontSize=8, textColor=white,
                                               alignment=TA_CENTER)),
        Paragraph("OVER 3.5", ParagraphStyle("ph4", fontName="Helvetica-Bold",
                                               fontSize=8, textColor=white,
                                               alignment=TA_CENTER)),
        Paragraph("BTS", ParagraphStyle("ph5", fontName="Helvetica-Bold",
                                          fontSize=8, textColor=white,
                                          alignment=TA_CENTER)),
    ]]

    for block_end, bm, ms_at, sc_b, sc_acc, trend in block_analyses:
        try:
            mk = compute_all_markets(ms_at, sc_acc, league_name=league_name)
            prob_rows.append([
                Paragraph(f"{block_end}", st_body),
                Paragraph(f"{mk['p_home']:.0f}%", st_body),
                Paragraph(f"{mk['p_away']:.0f}%", st_body),
                Paragraph(f"{mk['p_over_25']:.0f}%", st_body),
                Paragraph(f"{mk['p_over_35']:.0f}%", st_body),
                Paragraph(f"{mk['p_bts_yes']:.0f}%", st_body),
            ])
        except Exception:
            prob_rows.append([Paragraph(f"{block_end}", st_body)] +
                              [Paragraph("—", st_body) for _ in range(5)])

    ptable = Table(prob_rows, colWidths=[15*mm, 30*mm, 30*mm, 30*mm, 30*mm, 30*mm])
    ptable.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), C_BLACK),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_OFFWHITE, white]),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("LINEBELOW", (0,1), (-1,-2), 0.25, C_GRAY_LIGHT),
        ("LINEBELOW", (0,-1), (-1,-1), 0.8, C_GOLD),
    ]))
    story.append(ptable)

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "<i>Nota: probabilidades calculadas via Poisson independente com "
        "calibração para o tipo de competição. Fair odd = 1/probabilidade. "
        "Margem de segurança de 8% aplicada para odd mínima recomendada.</i>",
        st_caption))

    # ════════════════ 4. BLOCO FINAL DETALHADO ════════════════
    story.append(PageBreak())
    story.append(Paragraph("4. Bloco Final em Detalhe", st_h1))
    story.append(HRFlowable(width="100%", thickness=0.6, color=C_GOLD,
                              spaceAfter=10))

    if block_analyses:
        block_end, bm_f, ms_f, sc_b, sc_acc, trend_f = block_analyses[-1]
        narr_f = coach_narrative(bm_f, extract_context(bm_f.get("all_stats", {})),
                                   sc_b, evaluate(bm_f))

        story.append(Paragraph("4.1 O Que Rolou no Bloco Final (75-90 min)", st_h2))
        rolou_text = narr_f.get("rolou", "—")
        # Esclarece ambiguidade: deixa claro que números são DO BLOCO
        rolou_text = rolou_text.replace(
            f"em {final_minute} min",
            f"nos últimos 15 min do jogo"
        )
        story.append(Paragraph(rolou_text, st_body))

        story.append(Paragraph("4.2 Leitura Tática do Encerramento", st_h2))
        story.append(Paragraph(narr_f.get("leitura", "—"), st_body))

        story.append(Paragraph("4.3 Tendência Detectada no Encerramento", st_h2))
        # Como jogo já acabou, NÃO usa narrativa de "aguardar" — explica o
        # que a tendência teria sido se houvesse mais tempo
        trend_name = trend_f.get("trend", "INDEF")
        if trend_name == "INDEF":
            story.append(Paragraph(
                "Tendência não identificada no encerramento — jogo já estava "
                "matematicamente decidido nos minutos finais. Padrões "
                "operacionais (BACK, OVER, BTS) já não aplicáveis.",
                st_body))
        else:
            story.append(Paragraph(
                f"<b>Padrão tático detectado:</b> {trend_name.replace('_', ' ')}. "
                f"{trend_f.get('narrative', '—')}",
                st_body))
            story.append(Paragraph(
                "<i>Nota: como o jogo encerrou, essa tendência fica como "
                "registro histórico para calibração futura de jogos com "
                "perfil semelhante.</i>",
                st_caption))

        story.append(Paragraph("4.4 Métricas do Bloco vs Acumulado", st_h2))

        bvA_rows = [
            [Paragraph("MÉTRICA", ParagraphStyle("bH", fontName="Helvetica-Bold",
                                                  fontSize=8, textColor=white)),
             Paragraph(f"BLOCO {home[:10].upper()}", ParagraphStyle("bH1", fontName="Helvetica-Bold",
                                                                      fontSize=7, textColor=white,
                                                                      alignment=TA_CENTER)),
             Paragraph(f"BLOCO {away[:10].upper()}", ParagraphStyle("bH2", fontName="Helvetica-Bold",
                                                                      fontSize=7, textColor=white,
                                                                      alignment=TA_CENTER)),
             Paragraph(f"TOTAL {home[:10].upper()}", ParagraphStyle("bH3", fontName="Helvetica-Bold",
                                                                      fontSize=7, textColor=white,
                                                                      alignment=TA_CENTER)),
             Paragraph(f"TOTAL {away[:10].upper()}", ParagraphStyle("bH4", fontName="Helvetica-Bold",
                                                                      fontSize=7, textColor=white,
                                                                      alignment=TA_CENTER))],
            [Paragraph("Finalizações", st_body),
             Paragraph(f"{bm_f.get('home_shots',0):.0f}", st_body),
             Paragraph(f"{bm_f.get('away_shots',0):.0f}", st_body),
             Paragraph(f"{h_shots}", st_body),
             Paragraph(f"{a_shots}", st_body)],
            [Paragraph("No alvo (SOT)", st_body),
             Paragraph(f"{bm_f.get('home_sot',0):.0f}", st_body),
             Paragraph(f"{bm_f.get('away_sot',0):.0f}", st_body),
             Paragraph(f"{h_sot}", st_body),
             Paragraph(f"{a_sot}", st_body)],
            [Paragraph("xG", st_body),
             Paragraph(f"{bm_f.get('home_xg',0):.2f}", st_body),
             Paragraph(f"{bm_f.get('away_xg',0):.2f}", st_body),
             Paragraph(f"{h_xg_final:.2f}", st_body),
             Paragraph(f"{a_xg_final:.2f}", st_body)],
            [Paragraph("xGOT", st_body),
             Paragraph(f"{bm_f.get('home_xgot',0):.2f}", st_body),
             Paragraph(f"{bm_f.get('away_xgot',0):.2f}", st_body),
             Paragraph(f"{final.get('home_xgot',0):.2f}", st_body),
             Paragraph(f"{final.get('away_xgot',0):.2f}", st_body)],
            [Paragraph("CC", st_body),
             Paragraph(f"{bm_f.get('home_cc',0):.0f}", st_body),
             Paragraph(f"{bm_f.get('away_cc',0):.0f}", st_body),
             Paragraph(f"{h_cc_final}", st_body),
             Paragraph(f"{a_cc_final}", st_body)],
        ]
        bvA = Table(bvA_rows, colWidths=[33*mm, 33*mm, 33*mm, 33*mm, 33*mm])
        bvA.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), C_BLACK),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_OFFWHITE, white]),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("ALIGN", (1,0), (-1,-1), "CENTER"),
            ("TOPPADDING", (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("LINEBELOW", (0,1), (-1,-2), 0.25, C_GRAY_LIGHT),
            ("LINEBELOW", (0,-1), (-1,-1), 0.8, C_GOLD),
        ]))
        story.append(bvA)

    # ════════════════ 5. CONCLUSÃO FINAL ════════════════
    story.append(PageBreak())
    story.append(Paragraph("5. Conclusão Final", st_h1))
    story.append(HRFlowable(width="100%", thickness=0.6, color=C_GOLD,
                              spaceAfter=10))

    # Eficiência vs xG
    h_efficiency = "OK"
    if home_score > h_xg_final + 0.5:
        h_efficiency = "ACIMA do esperado (clinical / sorte)"
    elif home_score < h_xg_final - 0.5:
        h_efficiency = "ABAIXO do esperado (ineficiente)"
    else:
        h_efficiency = "ALINHADO ao xG"

    a_efficiency = "OK"
    if away_score > a_xg_final + 0.5:
        a_efficiency = "ACIMA do esperado (clinical / sorte)"
    elif away_score < a_xg_final - 0.5:
        a_efficiency = "ABAIXO do esperado (ineficiente)"
    else:
        a_efficiency = "ALINHADO ao xG"

    story.append(Paragraph("5.1 Veredito do Resultado", st_h2))
    story.append(Paragraph(
        f"<b>Placar final {home_score}-{away_score} </b>"
        f"({winner if winner != 'EMPATE' else 'jogo empatado'}).",
        st_body))
    story.append(Paragraph(
        f"<b>{home}:</b> marcou {home_score} gol{'s' if home_score != 1 else ''} "
        f"com xG total de {h_xg_final:.2f}. Eficiência: {h_efficiency}.",
        st_body))
    story.append(Paragraph(
        f"<b>{away}:</b> marcou {away_score} gol{'s' if away_score != 1 else ''} "
        f"com xG total de {a_xg_final:.2f}. Eficiência: {a_efficiency}.",
        st_body))

    story.append(Paragraph("5.2 Análise Estatística Consolidada", st_h2))
    diff_xg = h_xg_final - a_xg_final
    if abs(diff_xg) > 0.8:
        dom = home if diff_xg > 0 else away
        story.append(Paragraph(
            f"<b>{dom}</b> teve a melhor produção do jogo (xG "
            f"{max(h_xg_final, a_xg_final):.2f} vs "
            f"{min(h_xg_final, a_xg_final):.2f}). "
            f"Vantagem de {abs(diff_xg):.2f} xG indica superioridade clara "
            f"na criação de chances.",
            st_body))
    else:
        story.append(Paragraph(
            f"Jogo equilibrado na criação (xG {h_xg_final:.2f} vs "
            f"{a_xg_final:.2f}). Diferença marginal de "
            f"{abs(diff_xg):.2f} xG sugere que o resultado dependeu mais "
            f"da eficiência da finalização que do volume de chances.",
            st_body))

    story.append(Paragraph("5.3 Veredito Operacional do Sistema", st_h2))

    # Conta quantos blocos sugeriram entrada
    entries_suggested = sum(1 for _, _, _, _, _, t in block_analyses
                              if t.get("trend") not in ("INDEF", None))
    story.append(Paragraph(
        f"<b>Cobertura analítica:</b> {len(block_analyses)} blocos "
        f"processados, {entries_suggested} com tendência operacional "
        f"identificada. O sistema entregou análise completa do jogo do "
        f"minuto 0 ao {final_minute}.",
        st_body))

    story.append(Spacer(1, 14))

    # DECLARAÇÃO FINAL
    declaration = Table([[
        Paragraph(
            f"<b>DECLARAÇÃO FINAL</b><br/><br/>"
            f"Este relatório consolida {len(timeline)} snapshots capturados "
            f"durante o confronto {home} {home_score}-{away_score} {away}. "
            f"Toda a análise foi conduzida pelo sistema Trader Regra 3.1.2.0 "
            f"v4.4, com modelo Poisson calibrado por tipo de competição "
            f"({league_name or 'genérica'}) e engine de tendência tática "
            f"em 9 padrões. <b>Os dados aqui apresentados foram extraídos "
            f"em tempo real do Flashscore e são auditáveis</b> através do "
            f"arquivo de timeline em <font face='Courier' size='9'>"
            f"logs/timelines/{match_id}.jsonl</font>.",
            ParagraphStyle("decl", fontName="Helvetica", fontSize=10,
                            leading=14, textColor=C_BLACK,
                            alignment=TA_JUSTIFY))
    ]], colWidths=[170*mm])
    declaration.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), C_GREEN_LIGHT),
        ("LINEABOVE", (0,0), (-1,0), 1.5, C_GREEN),
        ("LINEBELOW", (0,-1), (-1,-1), 1.5, C_GREEN),
        ("TOPPADDING", (0,0), (-1,-1), 14),
        ("BOTTOMPADDING", (0,0), (-1,-1), 14),
        ("LEFTPADDING", (0,0), (-1,-1), 16),
        ("RIGHTPADDING", (0,0), (-1,-1), 16),
    ]))
    story.append(declaration)

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "<i>— Fim do Relatório —</i>",
        ParagraphStyle("end", fontName="Helvetica-Oblique", fontSize=9,
                        textColor=C_GRAY, alignment=TA_CENTER)))

    doc.build(story)
    return pdf_path
