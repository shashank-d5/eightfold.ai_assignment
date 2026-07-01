#!/usr/bin/env python3
"""
Generate the Step 1 design document PDF:
  ShashankSripathi_<email>_Eightfold.pdf
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

PAGE_W, PAGE_H = A4

doc = SimpleDocTemplate(
    "ShashankSripathi_shashank@example.com_Eightfold.pdf",
    pagesize=A4,
    topMargin=1.2*cm, bottomMargin=1.2*cm,
    leftMargin=1.5*cm, rightMargin=1.5*cm,
)

# ── Styles ──────────────────────────────────────────────────────────────────
BLUE = colors.HexColor("#1a3a6b")
LIGHT_BLUE = colors.HexColor("#e8eff8")
ACCENT = colors.HexColor("#2c7bb6")
DARK = colors.HexColor("#1a1a1a")
GRAY = colors.HexColor("#555555")
LIGHT_GRAY = colors.HexColor("#f5f5f5")
MID_GRAY = colors.HexColor("#dddddd")

title_style = ParagraphStyle("title", fontSize=14, fontName="Helvetica-Bold",
                              textColor=BLUE, spaceAfter=1, alignment=TA_LEFT)
sub_style = ParagraphStyle("sub", fontSize=8.5, fontName="Helvetica",
                            textColor=GRAY, spaceAfter=6)
section_style = ParagraphStyle("section", fontSize=8.5, fontName="Helvetica-Bold",
                                textColor=BLUE, spaceBefore=5, spaceAfter=2)
body_style = ParagraphStyle("body", fontSize=7.5, fontName="Helvetica",
                             textColor=DARK, spaceAfter=2, leading=11, alignment=TA_JUSTIFY)
bullet_style = ParagraphStyle("bullet", fontSize=7.5, fontName="Helvetica",
                               textColor=DARK, spaceAfter=1.5, leading=11,
                               leftIndent=8, bulletIndent=0)
code_style = ParagraphStyle("code", fontSize=7, fontName="Courier",
                             textColor=DARK, spaceAfter=2, leading=10,
                             backColor=LIGHT_GRAY, leftIndent=6, rightIndent=6)
label_style = ParagraphStyle("label", fontSize=7, fontName="Helvetica-Bold",
                              textColor=BLUE, spaceAfter=1)
small_style = ParagraphStyle("small", fontSize=7, fontName="Helvetica",
                              textColor=GRAY, spaceAfter=2, leading=10)


def section(title):
    return [
        Paragraph(title.upper(), section_style),
        HRFlowable(width="100%", thickness=0.5, color=ACCENT, spaceAfter=3),
    ]


def b(text):
    return f"<b>{text}</b>"


def bullet(text):
    return Paragraph(f"• {text}", bullet_style)


story = []

# ── Header ──────────────────────────────────────────────────────────────────
story.append(Paragraph("Multi-Source Candidate Data Transformer — Technical Design", title_style))
story.append(Paragraph("Shashank Sripathi &nbsp;|&nbsp; shashank@example.com &nbsp;|&nbsp; Eightfold Engineering Intern Assignment", sub_style))
story.append(HRFlowable(width="100%", thickness=1.5, color=BLUE, spaceAfter=5))

# ── Two-column layout via Table ──────────────────────────────────────────────
# LEFT column  (~55%)  RIGHT column (~45%)
COL_L = 9.5*cm
COL_R = 8.0*cm
GAP = 0.4*cm

left_items = []
right_items = []

# ── LEFT: Pipeline breakdown (CREATIVE VERSION) ─────────────────────────────
left_items += section("1. Pipeline Architecture (Parallel Ingestion Fabric)")

pipeline_data = [
    [Paragraph(b("Stage"), label_style),
     Paragraph(b("What happens"), label_style),
     Paragraph(b("Resilience"), label_style)],
    [Paragraph("Source Dialect\nInterpreters", small_style),
     Paragraph("Infer source type (CSV, ATS JSON, PDF, DOCX, TXT, GitHub API). Each extractor speaks its own 'language' (camelCase/snake_case/structured/free-text).", small_style),
     Paragraph("Unknown → skip + warn", small_style)],
    [Paragraph("Canonicalization\nBus", small_style),
     Paragraph("Phones → E.164 (phonenumbers). Dates → YYYY-MM (regex cascade). Country → ISO-3166 alpha-2 (pycountry). Emails → lowercase + RFC. Skills → alias map → canonical. Data is normalized BEFORE meeting other sources.", small_style),
     Paragraph("Unparseable → None", small_style)],
    [Paragraph("Identity\nClustering Layer", small_style),
     Paragraph("O(n) graph-based clustering using email/phone overlap. Fallback to normalized name + country for isolated records. Groups raw records into candidate clusters.", small_style),
     Paragraph("No match → single-candidate cluster", small_style)],
    [Paragraph("Staged Consensus\nEngine", small_style),
     Paragraph("Per-cluster merging: scalar fields resolved by dynamic source quality (not hardcoded). List fields union + dedupe. Experience entries merged with granular date selection.", small_style),
     Paragraph("Empty sources → zero weight", small_style)],
    [Paragraph("Trust & Corroboration\nVault", small_style),
     Paragraph("Per-skill: freq_weight×0.5 + avg_source_quality×0.5. Overall: field_coverage×0.5 + avg_source_quality×0.5. Source quality is DYNAMIC—based on data completeness, not file extension.", small_style),
     Paragraph("Bounded [0,1]", small_style)],
    [Paragraph("Projection\nGateway", small_style),
     Paragraph("Runtime config selects/renames fields via path DSL (emails[0], skills[].name, location.city). Applies per-field normalization, enforces on_missing (null/omit/error), validates types.", small_style),
     Paragraph("Missing required → ProjectionError", small_style)],
    [Paragraph("Schema\nVestibule", small_style),
     Paragraph("Post-projection type/required checks. Errors surfaced as list—pipeline does not crash. Supports source veto (ignored_sources) in config.", small_style),
     Paragraph("Returns error list", small_style)],
]

pipeline_table = Table(pipeline_data,
                        colWidths=[1.7*cm, 5.0*cm, 2.6*cm],
                        repeatRows=1)
pipeline_table.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), LIGHT_BLUE),
    ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
    ("FONTSIZE", (0,0), (-1,-1), 6.5),
    ("GRID", (0,0), (-1,-1), 0.3, MID_GRAY),
    ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT_GRAY]),
    ("TOPPADDING", (0,0), (-1,-1), 2),
    ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ("LEFTPADDING", (0,0), (-1,-1), 3),
]))
left_items.append(pipeline_table)
left_items.append(Spacer(1, 5))

# ── LEFT: Output Schema ───────────────────────────────────────────────────────
left_items += section("2. Canonical Output Schema")
left_items.append(Paragraph(
    "Pydantic CanonicalProfile. None = unknown — never invented.",
    body_style
))

schema_data = [
    [Paragraph(b("Field"), label_style), Paragraph(b("Type"), label_style), Paragraph(b("Normalization"), label_style)],
    ["candidate_id", "UUIDv5(name+email)", "deterministic"],
    ["full_name", "str | None", "—"],
    ["emails", "list[str]", "lowercase, RFC-5322"],
    ["phones", "list[str]", "E.164 via phonenumbers"],
    ["location", "{city, region, country}", "country → ISO-3166 alpha-2"],
    ["links", "{linkedin, github, portfolio, other[]}", "—"],
    ["headline", "str | None", "—"],
    ["years_experience", "float | None", "—"],
    ["skills", "[{name, confidence, sources[]}]", "alias map → canonical"],
    ["experience", "[{company,title,start,end,summary}]", "granular date merge"],
    ["education", "[{institution,degree,field,end_year}]", "end_year → int"],
    ["provenance", "[{field, source, method}]", "every accepted value"],
    ["overall_confidence", "float [0,1]", "dynamic source scoring"],
]

def _row(cells):
    return [Paragraph(str(c), small_style) for c in cells]

schema_rows = [schema_data[0]] + [_row(r) for r in schema_data[1:]]
schema_table = Table(schema_rows, colWidths=[2.3*cm, 2.9*cm, 2.8*cm], repeatRows=1)
schema_table.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), LIGHT_BLUE),
    ("FONTSIZE", (0,0), (-1,-1), 7),
    ("GRID", (0,0), (-1,-1), 0.3, MID_GRAY),
    ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT_GRAY]),
    ("TOPPADDING", (0,0), (-1,-1), 2),
    ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ("LEFTPADDING", (0,0), (-1,-1), 3),
]))
left_items.append(schema_table)

# ── RIGHT: Merge & Conflict Resolution ───────────────────────────────────────
right_items += section("3. Merge & Conflict Resolution")
right_items.append(Paragraph(
    b("Identity Clustering:") + " email overlap > phone overlap > normalized name. "
    "O(n) graph-based grouping. Each cluster = one candidate.",
    body_style
))
right_items.append(Paragraph(b("Scalar fields (name, headline):"), body_style))
right_items += [
    bullet("Pick value from source with highest <b>dynamic quality score</b> (based on data completeness, not file type)"),
    bullet("Tie → first encountered; flagged as 'conflict-resolved' in provenance"),
]
right_items.append(Paragraph(b("List fields (emails, phones, skills):"), body_style))
right_items += [
    bullet("Union + normalize → deduplicate by normalized form"),
    bullet("Skills: confidence = freq_weight×0.5 + avg_source_quality×0.5"),
]
right_items.append(Paragraph(b("Experience (Granular Merge):"), body_style))
right_items += [
    bullet("Groups by normalized company name"),
    bullet("For duplicates, picks the most precise date range (YYYY-MM over YYYY)"),
    bullet("Concatenates unique summaries"),
]
right_items.append(Spacer(1, 3))

# ── RIGHT: Runtime Config ─────────────────────────────────────────────────────
right_items += section("4. Runtime Config & Projection")
right_items.append(Paragraph(
    "Clean separation: engine → CanonicalProfile. Projection Gateway reshapes.",
    body_style
))

right_items.append(Paragraph(b("Config capabilities:"), body_style))
right_items += [
    bullet("<b>fields[].path</b> — output key name"),
    bullet("<b>fields[].from</b> — source path (supports [0] index and [] spread)"),
    bullet("<b>fields[].normalize</b> — E164 | canonical | lowercase | uppercase"),
    bullet("<b>fields[].required</b> — drives on_missing behavior"),
    bullet("<b>ignored_sources</b> — list of source types to skip (veto)"),
    bullet("<b>on_missing</b>: 'null' | 'omit' | 'error'"),
    bullet("<b>include_confidence / include_provenance</b> toggles"),
]

right_items.append(Paragraph(b("Path DSL examples:"), body_style))
right_items.append(Paragraph(
    '<font face="Courier" size="7">emails[0]</font> → first email &nbsp; '
    '<font face="Courier" size="7">skills[].name</font> → all skill names &nbsp; '
    '<font face="Courier" size="7">location.country</font> → nested field',
    small_style
))
right_items.append(Spacer(1, 4))

# ── RIGHT: Edge Cases ─────────────────────────────────────────────────────────
right_items += section("5. Edge Cases & Handling")

edge_data = [
    [Paragraph(b("Edge case"), label_style), Paragraph(b("How handled"), label_style)],
    ["Missing / empty source file",
     "Try/except around each extractor; returns []. Pipeline continues."],
    ["Multiple candidates in same CSV (3 rows → 3 profiles)",
     "Identity Clustering Layer groups by email/phone. Each cluster yields a separate canonical profile."],
    ["Conflicting name capitalisation ('alice doe' vs 'Alice Doe')",
     "Normalized lowercase for match key; highest-source-quality value for display."],
    ["Duplicate phone in two formats: '+1 (415) 555-0100' vs '4155550100'",
     "Both normalized to E.164; dict-key dedup."],
    ["ATS JSON with unknown field names",
     "Fields not mapped; ignored (never invented)."],
    ["Single-source skill with low confidence",
     "Confidence = source_quality × 0.5. Provenance records exactly one source."],
    ["User wants to ignore known-bad source type",
     "Runtime config supports 'ignored_sources' list (e.g., ['notes', 'csv'])."],
]

def _edge_row(cells):
    return [Paragraph(str(c), small_style) for c in cells]

edge_rows = [edge_data[0]] + [_edge_row(r) for r in edge_data[1:]]
edge_table = Table(edge_rows, colWidths=[3.0*cm, 4.8*cm], repeatRows=1)
edge_table.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), LIGHT_BLUE),
    ("FONTSIZE", (0,0), (-1,-1), 6.5),
    ("GRID", (0,0), (-1,-1), 0.3, MID_GRAY),
    ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT_GRAY]),
    ("TOPPADDING", (0,0), (-1,-1), 2),
    ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ("LEFTPADDING", (0,0), (-1,-1), 3),
]))
right_items.append(edge_table)
right_items.append(Spacer(1, 4))

right_items += section("6. Deliberate Descoping (time-pressure)")
right_items += [
    bullet("LinkedIn scraping skipped (ToS); URL stored in links, extraction noted as future work"),
    bullet("OCR for scanned PDFs not included; pypdf handles text-layer PDFs only"),
    bullet("Async/concurrent fetching not implemented—sequential sufficient at this scale"),
    bullet("Resume NER uses regex heuristics (fast, deterministic; lower recall but zero hallucinations)"),
]

# ── Assemble two columns ──────────────────────────────────────────────────────
from reportlab.platypus import KeepTogether

left_group = left_items
right_group = right_items

two_col = Table(
    [[left_group, right_group]],
    colWidths=[COL_L, COL_R],
)
two_col.setStyle(TableStyle([
    ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("LEFTPADDING", (0,0), (-1,-1), 0),
    ("RIGHTPADDING", (0,0), (-1,-1), 0),
    ("TOPPADDING", (0,0), (-1,-1), 0),
    ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ("LINEAFTER", (0,0), (0,-1), 0.5, MID_GRAY),
]))

story.append(two_col)

# ── Footer ───────────────────────────────────────────────────────────────────
story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GRAY, spaceBefore=4, spaceAfter=2))
story.append(Paragraph(
    "Implementation: Python 3.12 · pydantic · phonenumbers · pycountry · pypdf · python-docx · requests · reportlab &nbsp;|&nbsp; "
    "CLI: python cli.py --sources &lt;files&gt; [--config &lt;config.json&gt;] [--output &lt;out.json&gt;] &nbsp;|&nbsp; "
    "Demo: ./run_demo.sh  &nbsp;|&nbsp;  Tests: pytest tests/ -v &nbsp;|&nbsp;  Identity Clustering + Dynamic Source Scoring + Granular Experience Merge",
    ParagraphStyle("footer", fontSize=6.5, fontName="Helvetica", textColor=GRAY, alignment=TA_CENTER)
))

doc.build(story)
print("Design PDF generated.")