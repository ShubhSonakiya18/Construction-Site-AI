"""
app/services/pdf_export.py — Markdown-to-PDF export for generated documents.

Sprint 10, Deliverable 4. Scoped narrowly to safety_talk per
docs/NEXT_SPRINT.md ("scope narrowly ... generalizing to all 4 output
types is a natural follow-up, not required now") — but render_markdown_pdf()
itself has no safety_talk-specific logic; it works on the Markdown shape
every one of the 4 document services already produces (##/###  headers,
**bold**, "- " bullets — see generation/prompts/*.md's REQUIRED SECTIONS
convention, all four prompt files use the identical structural style).

Why reportlab, not weasyprint (the HTML->PDF alternative considered):
    weasyprint depends on GTK3/Pango/Cairo native libraries that are not
    reliably pip-installable on Windows (a common, well-documented source
    of install failures — missing DLLs, PATH issues — outside WSL/Docker).
    reportlab is pure Python, installs with a plain `pip install
    reportlab`, and needs no system dependency on the developer's actual
    machine. The tradeoff is manual layout instead of CSS, which is a
    reasonable cost for one document type's worth of styling.

Why a hand-rolled mini-parser, not a general Markdown library:
    A real Markdown parser (python-markdown, mistune, ...) would handle
    Markdown this codebase never produces — tables, images, nested lists,
    code fences — none of which appear in generation/prompts/*.md's
    REQUIRED SECTIONS templates. All 4 prompt files use exactly: `##`
    headers, `**bold**` inline spans, and `- ` bullet lines. Parsing only
    that shape is ~40 lines and has no third-party dependency surface to
    audit; a general parser would be solving a problem this codebase does
    not have.
"""
from __future__ import annotations

import re
from io import BytesIO

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

_BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")

# Live verification (a real Groq safety_talk generation, not synthetic
# test data) surfaced this: reportlab's default font (Helvetica, a PDF
# core font using WinAnsi/CP1252 encoding) renders any character outside
# that ~256-glyph set as a black box (■) — not an error, a silent visual
# corruption. LLM output routinely uses "smart" Unicode punctuation
# (curly quotes, en/em dashes, the multiplication sign, "approximately")
# that a human writer would type in ASCII. Embedding a full Unicode TTF
# font is the complete fix but adds a bundled font-file dependency this
# project doesn't otherwise have; normalizing the specific characters
# LLM prose actually produces to their ASCII equivalents is proportionate
# to the real failure mode and keeps this module dependency-free.
_UNICODE_TO_ASCII = str.maketrans({
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "--",  # hyphens/dashes
    "‘": "'", "’": "'", "‚": "'",                                 # single quotes
    "“": '"', "”": '"', "„": '"',                                # double quotes
    "…": "...",                                                            # ellipsis
    "×": "x", "÷": "/",                                               # multiply, divide
    "≈": "~", "≤": "<=", "≥": ">=",                              # approx, <=, >=
    "°": " deg", "½": " 1/2", "¼": " 1/4", "¾": " 3/4",     # degree, fractions
})


def _sanitize_for_pdf_font(text: str) -> str:
    """Replace Unicode punctuation the bundled Helvetica font can't
    render with its closest ASCII equivalent. See the module-level
    _UNICODE_TO_ASCII comment for why this exists and what it does not
    attempt to solve (full Unicode support, e.g. non-Latin scripts)."""
    return text.translate(_UNICODE_TO_ASCII)


def _inline_to_reportlab_markup(text: str) -> str:
    """Convert the one inline construct these prompts use (**bold**) to
    reportlab's Paragraph markup (<b>...</b>) — reportlab's Paragraph
    accepts a small XML-like markup subset, not literal Markdown."""
    sanitized = _sanitize_for_pdf_font(text)
    # Escape reportlab/XML special characters BEFORE inserting our own
    # <b> tags, so a literal "<" or "&" in generated content (e.g. "8 AM
    # < 9 AM" or "trades & subs") can't be misread as markup and silently
    # corrupt or crash the render.
    escaped = sanitized.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return _BOLD_PATTERN.sub(r"<b>\1</b>", escaped)


def render_markdown_pdf(title: str, markdown_content: str) -> bytes:
    """Render Markdown text (##  headers, **bold**, "- " bullets) to a
    styled PDF and return the raw bytes.

    Not tied to any one service_type — see module docstring for why this
    is safe across all 4 document-generating services' output shape, even
    though only safety_talk has an endpoint calling it in Sprint 10.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        title=title,
    )

    styles = getSampleStyleSheet()
    heading_style = ParagraphStyle(
        "PdfExportHeading",
        parent=styles["Heading2"],
        textColor=HexColor("#1e3a5f"),
        spaceBefore=14,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "PdfExportBody",
        parent=styles["BodyText"],
        spaceAfter=6,
        leading=15,
    )
    bullet_style = ParagraphStyle(
        "PdfExportBullet",
        parent=body_style,
        spaceAfter=2,
    )
    title_style = ParagraphStyle(
        "PdfExportTitle",
        parent=styles["Title"],
        textColor=HexColor("#1e3a5f"),
    )

    story = [Paragraph(_inline_to_reportlab_markup(title), title_style), Spacer(1, 0.15 * inch)]

    bullet_buffer: list[str] = []

    def _flush_bullets() -> None:
        if not bullet_buffer:
            return
        items = [
            ListItem(Paragraph(_inline_to_reportlab_markup(b), bullet_style))
            for b in bullet_buffer
        ]
        story.append(ListFlowable(items, bulletType="bullet", leftIndent=18))
        bullet_buffer.clear()

    for raw_line in markdown_content.splitlines():
        line = raw_line.rstrip()
        if not line:
            _flush_bullets()
            continue

        if line.startswith("## "):
            _flush_bullets()
            story.append(Paragraph(_inline_to_reportlab_markup(line[3:].strip()), heading_style))
        elif line.startswith("- "):
            bullet_buffer.append(line[2:].strip())
        else:
            _flush_bullets()
            story.append(Paragraph(_inline_to_reportlab_markup(line), body_style))

    _flush_bullets()

    doc.build(story)
    return buffer.getvalue()
