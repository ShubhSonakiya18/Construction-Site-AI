"""
app/services/osha_log_export.py — Sprint 15: OSHA Form 300 Log PDF export.

A separate PDF-generation code path from app/services/pdf_export.py's
render_markdown_pdf(), not an extension of it — that function is
deliberately scoped to the specific Markdown shape (## headers, **bold**,
"- " bullets) the 4 document-generation services produce, with no
table-rendering path. An OSHA 300 Log is fundamentally tabular (one row
per recordable case, fixed columns); reportlab.platypus.Table/TableStyle
(already available — reportlab is an existing dependency) is the right
tool, but it's a genuinely different rendering path than the bullet-list
one, per docs/NEXT_SPRINT.md's own investigation before this sprint began.

Reuses render_markdown_pdf()'s hard-won Unicode-to-ASCII sanitization
(_sanitize_for_pdf_font) rather than duplicating it — that fix was found
via live verification against real Groq output and applies identically
here: any incident description or corrective-action text could contain
the same "smart" Unicode punctuation an LLM or a voice-to-text pipeline
routinely produces.

Which incidents are table-ready vs. need-review (ADR-061): an incident
needs osha_recordable=True AND an osha_classification AND a resolved
worker identity (worker_id set, or worker_match_status not needing
review) before it can appear as a complete OSHA 300 row. Missing any of
these is surfaced explicitly (see build_osha_300_log()'s
excluded_needs_review return value) rather than silently either omitting
the incident or guessing at the missing field — a real safety officer
needs to know which incidents still need their attention before this
document is filed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from io import BytesIO
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.pdf_export import _sanitize_for_pdf_font

# OSHA Form 300 classification -> the form's own column label, in the
# fixed left-to-right column order OSHA's real form uses.
_CLASSIFICATION_LABELS = {
    "death": "Death",
    "days_away_from_work": "Days away from work",
    "job_transfer_or_restriction": "Job transfer or restriction",
    "other_recordable_case": "Other recordable case",
}

_INJURY_TYPE_LABELS = {
    "injury": "Injury",
    "skin_disorder": "Skin disorder",
    "respiratory_condition": "Respiratory condition",
    "poisoning": "Poisoning",
    "hearing_loss": "Hearing loss",
    "all_other_illnesses": "All other illnesses",
}


@dataclass
class OshaLogIncident:
    """One LogSafetyIncident row, already resolved to what a caller
    needs to render it -- built from the ORM row, not the row itself, so
    this module has no direct DB dependency and stays testable with
    small hand-built fixtures, matching schedule_service.py/
    cost_service.py's session-free pattern for the pure-computation half
    of their features."""

    case_number: Optional[str]
    log_date: date
    worker_name: Optional[str]
    job_title: Optional[str]
    description: str
    osha_classification: Optional[str]
    injury_illness_type: Optional[str]
    days_away_from_work_count: Optional[int]
    days_of_job_transfer_or_restriction_count: Optional[int]
    is_review_ready: bool
    review_reason: Optional[str]  # set when is_review_ready is False


@dataclass
class OshaLogBuildResult:
    pdf_bytes: bytes
    included_count: int
    excluded_needs_review: list[OshaLogIncident]


def classify_incident_readiness(
    *,
    osha_recordable: Optional[bool],
    osha_classification: Optional[str],
    worker_id: Optional[object],
    worker_match_status: Optional[str],
) -> tuple[bool, Optional[str]]:
    """Decide whether one incident has enough data to appear as a
    complete OSHA 300 row. Returns (is_ready, reason_if_not).

    An incident explicitly marked osha_recordable=False is a real,
    already-made determination that it does NOT belong on the log --
    excluded silently (is_ready=False, reason=None), not counted toward
    "needs review". Only osha_recordable=None (not yet assessed at all)
    is itself a review-needed blocker; a safety officer who already
    decided "not recordable" doesn't need a second prompt to decide
    again. reason is set (non-None) only when the incident is a real
    candidate that's missing something -- a caller can treat
    (is_ready=False, reason=None) as "not applicable" and
    (is_ready=False, reason=<str>) as "needs a human" without any
    further branching.

    Checked in a fixed order so the reason given is always the first
    real blocker, not an arbitrary one when multiple fields are missing.
    """
    if osha_recordable is False:
        return False, None
    if osha_recordable is None:
        return False, "OSHA recordability not yet assessed"
    if not osha_classification:
        return False, "missing OSHA classification (human review required)"
    if worker_match_status == "needs_review":
        return False, "worker identity needs review (ambiguous or partial name match)"
    if worker_id is None:
        return False, "no worker matched to this incident"
    return True, None


def build_osha_300_log(
    incidents: list[OshaLogIncident], *, project_name: str, calendar_year: int
) -> OshaLogBuildResult:
    """Render the OSHA 300 Log PDF for one project's recordable
    incidents in one calendar year.

    Incidents where is_review_ready=False are excluded from the table
    and returned in excluded_needs_review instead -- the PDF states the
    exclusion count plainly rather than silently omitting real
    recordable incidents from an official compliance document.
    """
    included = [i for i in incidents if i.is_review_ready]
    # review_reason is None for an incident that's simply not a
    # candidate at all (explicitly osha_recordable=False) -- that's a
    # real, already-made determination, not a gap needing a human's
    # attention, so it's excluded from the table without inflating the
    # "needs review" count (classify_incident_readiness()'s own
    # docstring explains why).
    excluded = [i for i in incidents if not i.is_review_ready and i.review_reason]

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(LETTER),
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        title=_sanitize_for_pdf_font(f"OSHA Form 300 Log - {project_name} - {calendar_year}"),
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "OshaLogTitle", parent=styles["Title"], textColor=HexColor("#1e3a5f"),
        fontSize=16,
    )
    subtitle_style = ParagraphStyle(
        "OshaLogSubtitle", parent=styles["BodyText"], spaceAfter=4,
    )
    cell_style = ParagraphStyle(
        "OshaLogCell", parent=styles["BodyText"], fontSize=8, leading=10,
    )
    header_style = ParagraphStyle(
        "OshaLogHeader", parent=styles["BodyText"], fontSize=8, leading=10,
        textColor=colors.white,
    )

    def _cell(text: object) -> Paragraph:
        return Paragraph(_sanitize_for_pdf_font(str(text) if text is not None else "—"), cell_style)

    story = [
        Paragraph(_sanitize_for_pdf_font("OSHA Form 300 — Log of Work-Related Injuries and Illnesses"), title_style),
        Spacer(1, 0.1 * inch),
        Paragraph(_sanitize_for_pdf_font(f"{project_name} — Calendar Year {calendar_year}"), subtitle_style),
        Spacer(1, 0.15 * inch),
    ]

    header_row = [
        Paragraph(h, header_style)
        for h in [
            "Case No.", "Date", "Employee Name", "Job Title", "Description",
            "Classification", "Injury/Illness Type", "Days Away",
            "Days Restricted",
        ]
    ]
    table_data: list[list] = [header_row]
    for inc in included:
        table_data.append([
            _cell(inc.case_number),
            _cell(inc.log_date.isoformat()),
            _cell(inc.worker_name),
            _cell(inc.job_title),
            _cell(inc.description),
            _cell(_CLASSIFICATION_LABELS.get(inc.osha_classification, inc.osha_classification)),
            _cell(_INJURY_TYPE_LABELS.get(inc.injury_illness_type, inc.injury_illness_type)),
            _cell(inc.days_away_from_work_count if inc.days_away_from_work_count is not None else "—"),
            _cell(
                inc.days_of_job_transfer_or_restriction_count
                if inc.days_of_job_transfer_or_restriction_count is not None else "—"
            ),
        ])

    if len(table_data) == 1:
        story.append(Paragraph(
            _sanitize_for_pdf_font(
                "No recordable incidents with complete data for this project and year."
            ),
            cell_style,
        ))
    else:
        col_widths = [0.85, 0.85, 1.1, 1.0, 2.25, 1.1, 1.1, 0.6, 0.7]
        total_width = 10.0 * inch
        col_widths = [w / sum(col_widths) * total_width for w in col_widths]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#1e3a5f")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, HexColor("#f0f4f8")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)

    if excluded:
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph(
            _sanitize_for_pdf_font(
                f"{len(excluded)} recordable incident(s) need human review before they can "
                "appear on this log — missing OSHA classification or an unresolved worker match."
            ),
            subtitle_style,
        ))

    doc.build(story)
    return OshaLogBuildResult(
        pdf_bytes=buffer.getvalue(),
        included_count=len(included),
        excluded_needs_review=excluded,
    )
