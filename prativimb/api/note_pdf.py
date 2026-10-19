"""SOAP note as a one page PDF for the patient record."""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from prativimb import config

INK, INK3, RULE = HexColor("#1B1B19"), HexColor("#75726B"), HexColor("#D8D3C8")
_fonts = False


def _register() -> tuple[str, str]:
    global _fonts
    d = config.ROOT / "assets" / "fonts"
    if not _fonts:
        try:
            pdfmetrics.registerFont(TTFont("PlexSerif", str(d / "IBMPlexSerif-Medium.ttf")))
            pdfmetrics.registerFont(TTFont("PlexSans", str(d / "IBMPlexSans-Regular.ttf")))
            pdfmetrics.registerFont(TTFont("PlexSansMed", str(d / "IBMPlexSans-Medium.ttf")))
            _fonts = True
        except Exception:
            return "Times-Bold", "Helvetica"
    return "PlexSerif", "PlexSans"


def render(note: dict) -> bytes:
    serif, sans = _register()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                            bottomMargin=16 * mm, title=f"Clinical note {note['patient']['id']}", author="Prativimb")
    h1 = ParagraphStyle("h1", fontName=serif, fontSize=16, leading=20, textColor=INK)
    meta = ParagraphStyle("meta", fontName=sans, fontSize=8.5, leading=12, textColor=INK3)
    h2 = ParagraphStyle("h2", fontName=serif, fontSize=11, leading=15, textColor=INK, spaceBefore=8, spaceAfter=2)
    body = ParagraphStyle("body", fontName=sans, fontSize=9.5, leading=13.5, textColor=INK, leftIndent=8,
                          bulletIndent=0, spaceAfter=1.5)
    p = note["patient"]
    when = datetime.fromisoformat(note["generated"]).strftime("%d %b %Y, %H:%M")
    flow = [
        Paragraph(f"{p['name']}, {p['age']} {('M' if p['gender'] == 'male' else 'F')}", h1),
        Paragraph(f"{p['id']} &middot; {', '.join(note['problems'])} &middot; Twin summary generated {when} IST", meta),
        Paragraph("Medications: " + "; ".join(note["medications"]), meta),
        Spacer(1, 4), HRFlowable(width="100%", thickness=0.6, color=RULE), Spacer(1, 2),
    ]
    for key, title in (("S", "Subjective"), ("O", "Objective"), ("A", "Assessment (twin findings)"), ("P", "Plan considerations")):
        flow.append(Paragraph(title, h2))
        for line in note[key]:
            flow.append(Paragraph(line, body, bulletText="•"))
    flow += [Spacer(1, 8), HRFlowable(width="100%", thickness=0.6, color=RULE), Spacer(1, 3),
             Paragraph(note["disclaimer"], meta)]
    doc.build(flow)
    return buf.getvalue()
