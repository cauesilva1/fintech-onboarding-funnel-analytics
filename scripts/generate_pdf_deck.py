"""
Generate an executive 3-slide PDF deck summarizing funnel findings.

Output:
  docs/executive_summary.pdf

Usage:
  python3 scripts/generate_pdf_deck.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "docs" / "executive_summary.pdf"

# Landscape 16:9-ish slide size (widescreen)
PAGE_W, PAGE_H = 13.333 * inch, 7.5 * inch

BG = HexColor("#0d1117")
PANEL = HexColor("#161b22")
ACCENT = HexColor("#58a6ff")
RED = HexColor("#e63946")
AMBER = HexColor("#f4a261")
GREEN = HexColor("#3fb950")
TEXT = HexColor("#e6edf3")
MUTED = HexColor("#8b949e")
CARD = HexColor("#21262d")


def _draw_background(c: canvas.Canvas) -> None:
    c.setFillColor(BG)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)


def _draw_header(c: canvas.Canvas, title: str, subtitle: str, slide_num: int) -> float:
    """Draw title block; return y position below header."""
    c.setFillColor(ACCENT)
    c.rect(0.55 * inch, PAGE_H - 0.45 * inch, 0.18 * inch, 0.18 * inch, fill=1, stroke=0)

    c.setFillColor(TEXT)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(0.9 * inch, PAGE_H - 0.48 * inch, title)

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 12)
    c.drawString(0.9 * inch, PAGE_H - 0.78 * inch, subtitle)

    c.setStrokeColor(HexColor("#30363d"))
    c.setLineWidth(1)
    c.line(0.55 * inch, PAGE_H - 1.0 * inch, PAGE_W - 0.55 * inch, PAGE_H - 1.0 * inch)

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 9)
    c.drawRightString(PAGE_W - 0.55 * inch, 0.35 * inch, f"Slide {slide_num} / 3  ·  Neobank Onboarding Analytics")

    return PAGE_H - 1.35 * inch


def _wrap_text(text: str, font: str, size: float, max_width: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if pdfmetrics.stringWidth(trial, font, size) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_bullet_block(
    c: canvas.Canvas,
    x: float,
    y: float,
    label: str,
    body: str,
    accent: HexColor,
    max_width: float,
) -> float:
    """Draw a labeled finding card; return new y below the card."""
    label_font, label_size = "Helvetica-Bold", 11
    body_font, body_size = "Helvetica", 11
    line_h = 15

    body_lines = _wrap_text(body, body_font, body_size, max_width - 0.35 * inch)
    card_h = 0.42 * inch + len(body_lines) * line_h

    c.setFillColor(PANEL)
    c.roundRect(x, y - card_h, max_width, card_h, 8, fill=1, stroke=0)

    c.setFillColor(accent)
    c.rect(x, y - card_h, 0.08 * inch, card_h, fill=1, stroke=0)

    text_x = x + 0.28 * inch
    c.setFillColor(accent)
    c.setFont(label_font, label_size)
    c.drawString(text_x, y - 0.28 * inch, label)

    c.setFillColor(TEXT)
    c.setFont(body_font, body_size)
    ty = y - 0.48 * inch
    for line in body_lines:
        c.drawString(text_x, ty, line)
        ty -= line_h

    return y - card_h - 0.18 * inch


def slide_1(c: canvas.Canvas) -> None:
    _draw_background(c)
    y = _draw_header(
        c,
        "Neobank Onboarding Analytics: Funnel Drop-off & Financial Impact",
        "Diagnostic Analysis of User Acquisition Bottlenecks (Q1-Q3)",
        1,
    )

    # KPI strip
    kpis = [
        ("1,200", "Accounts Created", ACCENT),
        ("57%", "Doc → KYC Conversion", RED),
        ("25%", "End-to-End Conversion", AMBER),
        ("360", "Users Lost at KYC", RED),
    ]
    card_w = 2.8 * inch
    gap = 0.22 * inch
    start_x = 0.55 * inch
    for i, (value, caption, color) in enumerate(kpis):
        x = start_x + i * (card_w + gap)
        c.setFillColor(CARD)
        c.roundRect(x, y - 1.05 * inch, card_w, 1.05 * inch, 8, fill=1, stroke=0)
        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 26)
        c.drawString(x + 0.2 * inch, y - 0.5 * inch, value)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 10)
        c.drawString(x + 0.2 * inch, y - 0.8 * inch, caption)

    y = y - 1.35 * inch
    findings = [
        (
            "Top of Funnel Volume",
            "1,200 contas criadas no período analisado.",
            ACCENT,
        ),
        (
            "Primary Bottleneck",
            "Apenas 57% dos usuários que sobem documentos chegam à aprovação de KYC (perda bruta de 360 usuários).",
            RED,
        ),
        (
            "Net Conversion Rate",
            "Taxa final de conversão (Account Created -> First Deposit) travada em 25% (300 usuários depositantes).",
            AMBER,
        ),
        (
            "Financial Impact",
            "Perda de receita recorrente por desistência operacional na verificação de identidade antes da primeira monetização.",
            AMBER,
        ),
    ]
    for label, body, accent in findings:
        y = _draw_bullet_block(c, 0.55 * inch, y, label, body, accent, PAGE_W - 1.1 * inch)


def slide_2(c: canvas.Canvas) -> None:
    _draw_background(c)
    y = _draw_header(
        c,
        "Monthly Cohort Analysis: KYC Approval Rate Degradation",
        "Evaluating Onboarding Health Across Acquisition Months",
        2,
    )

    # Timeline cards
    milestones = [
        ("March Peak", "61.67%", "Melhor desempenho da série", GREEN),
        ("June Trough", "52.20%", "Vale de -9.47 pp vs baseline", RED),
        ("September", "58.46%", "Estabilização parcial no Q3", AMBER),
    ]
    card_w = 3.85 * inch
    gap = 0.25 * inch
    for i, (title, value, note, color) in enumerate(milestones):
        x = 0.55 * inch + i * (card_w + gap)
        c.setFillColor(PANEL)
        c.roundRect(x, y - 1.35 * inch, card_w, 1.35 * inch, 8, fill=1, stroke=0)
        c.setFillColor(color)
        c.rect(x, y - 1.35 * inch, 0.1 * inch, 1.35 * inch, fill=1, stroke=0)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 11)
        c.drawString(x + 0.28 * inch, y - 0.35 * inch, title)
        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 28)
        c.drawString(x + 0.28 * inch, y - 0.8 * inch, value)
        c.setFillColor(TEXT)
        c.setFont("Helvetica", 10)
        c.drawString(x + 0.28 * inch, y - 1.1 * inch, note)

    y = y - 1.7 * inch
    items = [
        (
            "Peak Performance (March)",
            "Taxa de aprovação no KYC de 61.67%.",
            GREEN,
        ),
        (
            "Trough Performance (June)",
            "Queda contínua até o vale de 52.20% em junho (-9.47 pp).",
            RED,
        ),
        (
            "Stabilization (Q3)",
            "Recuperação parcial no terceiro trimestre, estabilizando em 58.46% em setembro.",
            AMBER,
        ),
        (
            "Root Cause Hypothesis",
            "Falhas na integração da API de validação de documentos nos meses de maior pico e fricção no fluxo mobile (documentos ilegíveis/timeout de OCR).",
            RED,
        ),
    ]
    for label, body, accent in items:
        y = _draw_bullet_block(c, 0.55 * inch, y, label, body, accent, PAGE_W - 1.1 * inch)


def slide_3(c: canvas.Canvas) -> None:
    _draw_background(c)
    y = _draw_header(
        c,
        "Product & Operational Roadmap: Recovering Onboarding Conversion",
        "High-Impact Initiatives for Product, Fraud, and Operations",
        3,
    )

    actions = [
        (
            "01  Instant Feedback UX",
            "Validação em tempo real durante a foto do documento (foco e iluminação automatizados).",
            ACCENT,
        ),
        (
            "02  Fallback Verification Provider",
            "Failover automático para segunda API quando a latência ultrapassar 5s.",
            ACCENT,
        ),
        (
            "03  Automated Re-engagement",
            "Régua de comunicação via Push/SMS/E-mail nas primeiras 24h e 48h.",
            ACCENT,
        ),
    ]
    for label, body, accent in actions:
        y = _draw_bullet_block(c, 0.55 * inch, y, label, body, accent, PAGE_W - 1.1 * inch)

    # Target metric banner
    banner_h = 1.35 * inch
    c.setFillColor(CARD)
    c.roundRect(0.55 * inch, 0.7 * inch, PAGE_W - 1.1 * inch, banner_h, 10, fill=1, stroke=0)
    c.setFillColor(GREEN)
    c.rect(0.55 * inch, 0.7 * inch, 0.12 * inch, banner_h, fill=1, stroke=0)

    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(0.9 * inch, 0.7 * inch + banner_h - 0.35 * inch, "TARGET METRIC")

    c.setFillColor(TEXT)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(
        0.9 * inch,
        0.7 * inch + banner_h - 0.7 * inch,
        "Elevar conversão do KYC de 57% para 68%",
    )
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 12)
    c.drawString(
        0.9 * inch,
        0.7 * inch + banner_h - 1.05 * inch,
        "Ganho incremental estimado: +130 usuários depositantes",
    )


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUTPUT_PATH), pagesize=(PAGE_W, PAGE_H))
    c.setTitle("Neobank Onboarding Analytics — Executive Summary")
    c.setAuthor("FinTech Growth & Revenue Funnel Portfolio")

    slide_1(c)
    c.showPage()
    slide_2(c)
    c.showPage()
    slide_3(c)
    c.save()

    print(f"Generated: {OUTPUT_PATH}")
    print(f"Size: {OUTPUT_PATH.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
