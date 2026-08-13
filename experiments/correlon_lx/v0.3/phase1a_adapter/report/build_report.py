from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[5]
OUTPUT = (
    ROOT
    / "experiments/correlon_lx/v0.3/phase1a_adapter/artifacts/phase1a-run1/report"
    / "correlon_lx_v0.3_phase1a_adapter_qualification_report.pdf"
)

NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#2B6CB0")
LIGHT_BLUE = colors.HexColor("#EAF2FA")
RED = colors.HexColor("#B42318")
LIGHT_RED = colors.HexColor("#FDECEC")
GREEN = colors.HexColor("#18794E")
LIGHT_GREEN = colors.HexColor("#EAF7F0")
GRAY = colors.HexColor("#586474")
LIGHT_GRAY = colors.HexColor("#F3F5F7")
BORDER = colors.HexColor("#CBD3DC")


def register_fonts() -> None:
    pdfmetrics.registerFont(TTFont("YuGothic", r"C:\Windows\Fonts\YuGothR.ttc", subfontIndex=0))
    pdfmetrics.registerFont(TTFont("YuGothic-M", r"C:\Windows\Fonts\YuGothM.ttc", subfontIndex=0))


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def styled_table(data, widths, header=True, font_size=8.2, row_colors=None):
    cell_style = ParagraphStyle(
        "TableCell", fontName="YuGothic", fontSize=font_size,
        leading=font_size + 3, textColor=colors.HexColor("#263442"),
    )
    head_style = ParagraphStyle(
        "TableHead", parent=cell_style, fontName="YuGothic-M", textColor=colors.white,
    )
    wrapped = []
    for row_index, row in enumerate(data):
        wrapped.append([
            value if isinstance(value, Paragraph) else Paragraph(
                escape(str(value)), head_style if header and row_index == 0 else cell_style
            )
            for value in row
        ])
    table = Table(wrapped, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("FONTNAME", (0, 0), (-1, -1), "YuGothic"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("LEADING", (0, 0), (-1, -1), font_size + 3),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "YuGothic-M"),
        ]
        for row in range(1, len(data)):
            commands.append(("BACKGROUND", (0, row), (-1, row), colors.white if row % 2 else LIGHT_GRAY))
    if row_colors:
        for row, color in row_colors.items():
            commands.append(("BACKGROUND", (0, row), (-1, row), color))
    table.setStyle(TableStyle(commands))
    return table


def page_decor(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
    canvas.setFont("YuGothic", 7.5)
    canvas.setFillColor(GRAY)
    canvas.drawString(18 * mm, 9.5 * mm, "Correlon-LX v0.3 | Phase 1A Adapter Qualification")
    canvas.drawRightString(A4[0] - 18 * mm, 9.5 * mm, f"{doc.page}")
    canvas.restoreState()


def build() -> None:
    register_fonts()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "TitleJP", parent=styles["Title"], fontName="YuGothic-M", fontSize=22,
        leading=29, textColor=NAVY, alignment=TA_LEFT, spaceAfter=10,
    )
    subtitle = ParagraphStyle(
        "Subtitle", parent=styles["Normal"], fontName="YuGothic", fontSize=10,
        leading=16, textColor=GRAY, spaceAfter=10,
    )
    h1 = ParagraphStyle(
        "H1JP", parent=styles["Heading1"], fontName="YuGothic-M", fontSize=15,
        leading=21, textColor=NAVY, spaceBefore=8, spaceAfter=8,
    )
    h2 = ParagraphStyle(
        "H2JP", parent=styles["Heading2"], fontName="YuGothic-M", fontSize=11.5,
        leading=17, textColor=BLUE, spaceBefore=7, spaceAfter=5,
    )
    body = ParagraphStyle(
        "BodyJP", parent=styles["BodyText"], fontName="YuGothic", fontSize=9.2,
        leading=15, textColor=colors.HexColor("#263442"), spaceAfter=6,
    )
    small = ParagraphStyle(
        "SmallJP", parent=body, fontSize=7.7, leading=12, textColor=GRAY,
    )
    badge = ParagraphStyle(
        "Badge", parent=body, fontName="YuGothic-M", fontSize=12, leading=17,
        alignment=TA_CENTER, textColor=RED,
    )
    bullet = ParagraphStyle(
        "BulletJP", parent=body, leftIndent=12, firstLineIndent=-8, bulletIndent=2,
    )

    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=20 * mm,
        title="Correlon-LX v0.3 Phase 1A Adapter Qualification Report",
        author="CORENO-Q experimental audit",
        subject="Formal falsification result",
    )
    story = []

    story += [
        paragraph("Correlon-LX v0.3", title),
        paragraph("Phase 1A Adapter Qualification - サイクル反証実験報告", subtitle),
        Spacer(1, 4 * mm),
        Table(
            [[paragraph("正式判定", small), paragraph("STOP_COMBINED_SEMANTICS_MISMATCH", badge)]],
            colWidths=[32 * mm, 128 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_RED),
                ("BOX", (0, 0), (-1, -1), 1, RED),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]),
        ),
        Spacer(1, 6 * mm),
        paragraph("技術要約", h1),
        paragraph(
            "v0.2.3で固定したrff24 detectorとR1-R4 adapterを対象に、同一raw dataをadapter前後でpaired評価した。"
            "4表現 x 6条件 x 100反復 = 2,400 paired evaluationsは数値異常ゼロで完走した。A0-A4およびA6はPASSしたが、"
            "A5の最小判定一致率は0.94（基準0.95）、A7のcombined OR意味論不一致は401件（基準0）だった。",
            body,
        ),
        paragraph(
            "したがってPhase 1Aは不合格であり、Phase 1B Cross-Representation Rendezvousは未実施である。"
            "達成claim levelはL0のままで、共有構造探索L1以降および直接因果L4の主張は許可されない。",
            body,
        ),
        paragraph("主要数値", h2),
        styled_table(
            [
                ["指標", "観測値", "基準", "判定"],
                ["paired evaluations", "2,400", "予定2,400", "PASS"],
                ["nonfinite / range failures", "0 / 0", "0 / 0", "PASS"],
                ["null combined FWER", "0.01-0.02", "<=0.05", "PASS"],
                ["square nonlinear sensitivity", "1.00 (R1-R4)", ">=0.95", "PASS"],
                ["minimum paired agreement", "0.94", ">=0.95", "FAIL"],
                ["combined OR mismatches", "401 / 2,400", "0", "FAIL"],
            ],
            [62 * mm, 36 * mm, 31 * mm, 25 * mm],
            row_colors={5: LIGHT_RED, 6: LIGHT_RED},
        ),
        Spacer(1, 4 * mm),
        paragraph(
            "結論: Adapter単体の数値安定性・null保全・線形/非線形感度は良好だが、combined判定が仕様上のORとして機能しない。"
            "これは結果後に修正せず、fresh revisionでのみ再設計可能である。",
            body,
        ),
    ]

    story += [PageBreak(), paragraph("A0-A7の反証結果", h1)]
    gate_rows = [
        ["Gate", "結果", "観測", "事前基準"],
        ["A0", "PASS", "nonfinite 0, range 0", "各0"],
        ["A1", "PASS", "null combined 0.01-0.02", "各表現 <=0.05"],
        ["A2", "PASS", "direct linear 1.00", "各表現 >=0.95"],
        ["A3", "PASS", "square/tanh nonlinear 1.00", "各表現 >=0.95"],
        ["A4", "PASS", "square linear FP 0.02-0.09", "各表現 <=0.10"],
        ["A5", "FAIL", "minimum agreement 0.94", "全セル >=0.95"],
        ["A6", "PASS", "最大表現差 0.07", "全対象 <=0.10"],
        ["A7", "FAIL", "OR mismatch 401", "0"],
    ]
    story += [
        paragraph(
            "停止を決めたのはA7である。A5も独立に基準を0.01下回った。A7失敗時の事前登録decisionは"
            "STOP_COMBINED_SEMANTICS_MISMATCHであり、判定の後付け変更はない。",
            body,
        ),
        styled_table(gate_rows, [16 * mm, 20 * mm, 67 * mm, 52 * mm], row_colors={6: LIGHT_RED, 8: LIGHT_RED}),
        Spacer(1, 6 * mm),
        paragraph("表現別の主要性能", h2),
        paragraph(
            "adapter後の主要rateを示す。exact auditを優先し、連続トレンドではないためチャートではなく表を使用した。",
            body,
        ),
        styled_table(
            [
                ["Rep", "Null comb.", "Direct lin.", "Square nonlin.", "Tanh nonlin.", "Square lin. FP"],
                ["R1", "0.02", "1.00", "1.00", "1.00", "0.09"],
                ["R2", "0.02", "1.00", "1.00", "1.00", "0.08"],
                ["R3", "0.01", "1.00", "1.00", "1.00", "0.02"],
                ["R4", "0.02", "1.00", "1.00", "1.00", "0.06"],
            ],
            [18 * mm, 27 * mm, 27 * mm, 29 * mm, 27 * mm, 28 * mm],
        ),
        Spacer(1, 6 * mm),
        paragraph("combined失敗はsquareとnullに集中", h2),
        paragraph(
            "401件の不一致のうち375件がnonlinear_square、26件がnullだった。squareではnonlinear channelが全件検出する一方、"
            "combined検出は0.02-0.09に留まる。raw scoreのmaxと、異なるscaleのchannel別calibrationを混在させたことが"
            "logical ORの判定意味論を満たしていない。",
            body,
        ),
        styled_table(
            [
                ["Rep", "Null mismatch", "Square mismatch", "合計"],
                ["R1", "9", "91", "100"],
                ["R2", "6", "92", "98"],
                ["R3", "6", "98", "104"],
                ["R4", "5", "94", "99"],
                ["Total", "26", "375", "401"],
            ],
            [30 * mm, 40 * mm, 45 * mm, 35 * mm],
            row_colors={5: LIGHT_RED},
        ),
    ]

    story += [PageBreak(), paragraph("実験範囲・定義・方法", h1)]
    methods = [
        ("親記録", "Correlon-LX v0.2.3 PHASE_0R_PASS、stress100 STRESS_PASS。rff24、R1-R4、calibrationを固定。"),
        ("paired design", "各condition/replicateの同一raw Xを、同一representation固有detector realizationでXとA_r(X)に適用。"),
        ("母数", "6 conditions x 100 replicates。各raw datasetを4 representationsで評価し、2,400 paired evaluations。"),
        ("判定単位", "nullは15 pairsのfamily-wise any decision。non-nullは事前登録H-V target pair decision。alpha=0.05。"),
        ("A7定義", "combined_decision == (linear_decision OR nonlinear_decision)。1件でも不一致ならFAIL。"),
        ("停止順序", "A0-A7全PASSのみADAPTER_QUALIFIED。A7 FAILは専用STOP。Phase 1Bへの自動連結は禁止。"),
    ]
    story.append(styled_table([["項目", "固定内容"]] + [[k, v] for k, v in methods], [35 * mm, 120 * mm]))
    story += [
        Spacer(1, 7 * mm),
        paragraph("Repository freezeとrun0停止", h2),
        paragraph(
            "最初のfreeze検証では、GitHub connector経由で保存されたv0.2.3 stress decisionの先頭に実行ログが混入し、"
            "JSONとして解析不能だった。Phase 1A seedを開く前にrun0をSTOP_PARENT_ARTIFACT_NOT_MACHINE_READABLEとして保存した。"
            "元の決定論的stress成果物を復元し、2,400行のruns.csvとsummary.csvが再実行でSHA-256一致、decisionもelapsed_seconds以外一致した後、"
            "fresh run1 freezeを作成した。",
            body,
        ),
        paragraph("独立検証と頑健性", h2),
        paragraph(
            "paired_runs.csvから別計算経路で行数、一意キー、各セル件数、全rate、A0-A7、最終decisionを再計算した。"
            "保存decisionと全項目が一致した。生データ2,400行は全て一意で、各representation-condition cellは100行だった。",
            body,
        ),
        styled_table(
            [
                ["検証項目", "結果"],
                ["row / unique key", "2,400 / 2,400"],
                ["cell size", "全24セルで100"],
                ["gate recomputation", "A0-A7全て保存値と一致"],
                ["decision recomputation", "STOP_COMBINED_SEMANTICS_MISMATCH"],
                ["post-result parameter changes", "0"],
            ],
            [60 * mm, 95 * mm],
        ),
    ]

    story += [PageBreak(), paragraph("限界・解釈・次工程", h1)]
    story += [
        paragraph("このSTOPが意味すること", h2),
        paragraph(
            "Correlon-LX全体の失敗や、adapterが全面的に不安定という結論ではない。A0-A4とA6は通過している。"
            "停止対象は、Phase 1Aで事前登録したcombined OR意味論とpaired consistencyを満たさない現在のv0.3構成である。",
            body,
        ),
        paragraph("許可されない解釈", h2),
        paragraph("- Phase 1B/1Cを実行済み、またはPASSしたと表現しない。", bullet),
        paragraph("- common driver陽性をdirect causal connectionと呼ばない。", bullet),
        paragraph("- nonlinear channel単独の高感度をcombined detectorの認証へ読み替えない。", bullet),
        paragraph("- この結果からL1、L2、L3、L4へclaimを昇格しない。", bullet),
        paragraph("推奨する次工程", h2),
        paragraph(
            "v0.3はこのSTOPで終了する。combined意味論を変更する場合はv0.3.1 fresh revisionとし、結果を見ないdevelopment splitで"
            "次のいずれかを事前固定する必要がある: (1) calibrated channel p-valuesのlogical OR、(2) channel scaleを事前標準化したmax-statistic、"
            "(3) conservative detectorとしてclaim自体を明示的に変更。いずれも新しいnull calibrationとfresh seed namespaceが必要で、"
            "本runの継続扱いは禁止する。",
            body,
        ),
        paragraph("Further questions", h2),
        paragraph("- combinedはOR detectorであるべきか、conservative統合量として再定義すべきか。", bullet),
        paragraph("- A5をchannel別に維持するか、adapter qualificationのprimary decisionを分離するか。", bullet),
        paragraph("- v0.3.1でcombinedを修正した場合、旧A7 failureをholdoutで再現・解消できるか。", bullet),
        Spacer(1, 5 * mm),
        paragraph("Provenance", h2),
        styled_table(
            [
                ["項目", "値"],
                ["v0.3 source commit", "24ecef1aa5f122e7f6c094c0ef6e047e8221841d"],
                ["run1 freeze commit", "89a35639c5131755c1fad3382242575e8917223a"],
                ["preregistration bundle SHA-256", "8D5E9F1E0FC2CF514C99ACEEB2547820A6FC69C066946C0F90AC2421D7C86112"],
                ["result decision SHA-256", "7AFC732B99005E9F68E106BDF389549655018854E88C5989709DCC1EF2D3EB35"],
                ["paired runs SHA-256", "4F55CBAE236215B1A7C1638A31B03B4D17A71EDD9F6AE67BE309F37A63F34CC2"],
            ],
            [48 * mm, 107 * mm],
            font_size=7.2,
        ),
        Spacer(1, 4 * mm),
        paragraph("作成日: 2026-08-13 (Asia/Tokyo) | Repository: osskosc-lab/CORENO-Q", small),
    ]

    doc.build(story, onFirstPage=page_decor, onLaterPages=page_decor)
    print(OUTPUT)


if __name__ == "__main__":
    build()
