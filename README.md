# Multi-Source Candidate Data Transformer

**Eightfold Engineering Intern Assignment — Dasoju Shashank**

---

## What it does

Ingests candidate data from multiple sources (Recruiter CSV, ATS JSON, Resume PDF/DOCX, Recruiter Notes `.txt`, GitHub API), **automatically clusters records by identity**, merges each cluster into a clean canonical profile, and projects the result through a runtime-configurable output schema — with full provenance and confidence scoring.

### Key Innovations

- **Identity Clustering** – Handles multiple candidates in a single run using an O(n) graph-based grouping algorithm.
- **Dynamic Source Quality** – Trust is based on data completeness rather than file type.
- **Granular Experience Merging** – Chooses the most precise date ranges from overlapping work experiences.
- **Source Veto** – Runtime configuration can ignore unreliable source types.

---

#  One-Command Demo

```bash
./run_demo.sh
```

This runs the complete pipeline and generates:

- `sample_outputs/demo_default.json` – Full canonical profile with provenance
- `sample_outputs/demo_recruiter_view.json` – Recruiter quick-view projection

---

# Quick Start

## 1. Install Dependencies

```bash
pip install phonenumbers pycountry pypdf python-docx pydantic reportlab requests pytest
```

**Python 3.10+ required**

---

## 2. Run the Pipeline

### Default Output (Full Canonical Profile)

```bash
python cli.py \
  --sources sample_inputs/recruiter_export.csv \
            sample_inputs/ats_export.json \
            sample_inputs/sample_resume_priya.pdf \
            sample_inputs/recruiter_notes_priya.txt \
  --output sample_outputs/priya_default.json \
  --full-profile \
  --verbose
```

---

### Recruiter Quick View

```bash
python cli.py \
  --sources sample_inputs/recruiter_export.csv \
            sample_inputs/ats_export.json \
            sample_inputs/sample_resume_priya.pdf \
            sample_inputs/recruiter_notes_priya.txt \
  --config config/recruiter_view.json \
  --output sample_outputs/priya_recruiter_view.json \
  --verbose
```

---

### ATS Integration Export

```bash
python cli.py \
  --sources sample_inputs/recruiter_export.csv \
            sample_inputs/ats_export.json \
  --config config/ats_integration.json \
  --output sample_outputs/priya_ats_integration.json \
  --verbose
```

---

### Output All Candidates

```bash
python cli.py \
  --sources sample_inputs/recruiter_export.csv \
            sample_inputs/ats_export.json \
  --all \
  --output sample_outputs/all_candidates.json \
  --verbose
```

---

### GitHub Source

```bash
python cli.py \
  --sources https://github.com/torvalds \
  --output sample_outputs/github_torvalds.json
```

---

### Print to Console

```bash
python cli.py --sources sample_inputs/recruiter_export.csv
```

---

## 3. Run Tests

```bash
python -m pytest tests/ -v
```

All **68 tests pass** in approximately **2 seconds**.

---

# Project Structure

```text
.
├── cli.py
├── run_demo.sh
├── transformer/
│   ├── __init__.py
│   ├── schema.py
│   ├── normalize.py
│   ├── extractors.py
│   ├── grouper.py
│   ├── merge.py
│   ├── project.py
│   └── pipeline.py
├── sample_inputs/
│   ├── recruiter_export.csv
│   ├── ats_export.json
│   ├── sample_resume_priya.pdf
│   └── recruiter_notes_priya.txt
├── config/
│   ├── recruiter_view.json
│   └── ats_integration.json
├── sample_outputs/
│   ├── all_candidates.json
│   ├── priya_default.json
│   ├── priya_default_full_profile.json
│   ├── priya_recruiter_view.json
│   └── priya_ats_integration.json
├── tests/
│   └── test_transformer.py
└── DasojuShashank_shashankdasoju111@gmail.com_Eightfold.pdf
```

---

# Supported Sources

| Source | Type | Notes |
|--------|------|------|
| Recruiter CSV | Structured | Flexible headers, semicolon-separated skills |
| ATS JSON | Structured | camelCase and snake_case mapping |
| Resume PDF | Unstructured | Regex extraction |
| Resume DOCX | Unstructured | Same pipeline as PDF |
| Recruiter Notes (.txt) | Unstructured | Pattern-based extraction |
| GitHub Profile URL | Unstructured | REST API |

---

# Configuration Schema

```json
{
  "fields": [
    {
      "path": "full_name",
      "type": "string",
      "required": true
    },
    {
      "path": "primary_email",
      "from": "emails[0]",
      "type": "string",
      "required": true
    },
    {
      "path": "phone",
      "from": "phones[0]",
      "type": "string",
      "normalize": "E164"
    },
    {
      "path": "skill_names",
      "from": "skills[].name",
      "type": "string[]",
      "normalize": "canonical"
    },
    {
      "path": "years_experience",
      "type": "number"
    }
  ],
  "ignored_sources": [
    "notes",
    "csv"
  ],
  "include_confidence": true,
  "include_provenance": false,
  "on_missing": "null"
}
```

---

# Configuration Options

| Option | Description |
|---------|-------------|
| `fields[].path` | Output field |
| `fields[].from` | Source mapping |
| `fields[].type` | Data type |
| `fields[].required` | Required field |
| `fields[].normalize` | Field normalization |
| `ignored_sources` | Ignore source types |
| `include_confidence` | Include confidence score |
| `include_provenance` | Include provenance |
| `on_missing` | Missing field behavior |

---

# Path DSL Examples

```text
emails[0]
skills[].name
location.country
experience[0].company
```

---

# Design Decisions

## Why Identity Clustering?

CSV exports may contain multiple candidates. A graph-based clustering layer groups records by shared emails or phone numbers with a fallback to normalized name plus country.

---

## Why Dynamic Source Quality?

Source trust depends on **information completeness**, not file extension.

```
quality = (core_fields_filled / 4) * 0.7 +
          (bonus_fields_filled / 3) * 0.3
```

Clamped to **0.2–0.95**.

---

## Why Granular Experience Merging?

When multiple sources describe the same job, the system keeps the most precise dates while preserving additional summaries.

---

## Why Pydantic?

Provides validation, serialization, and serves as living documentation.

---

## Why Regex Instead of LLMs?

Deterministic, fast, reproducible, and free from hallucinations.

---

## Why UUIDv5?

Generates deterministic IDs so repeated runs produce the same candidate identifier.

---

# Confidence Formula

```text
skill_confidence =
    frequency_weight * 0.5 +
    average_source_quality * 0.5
```

---

# Edge Cases Handled

| Edge Case | Handling |
|-----------|----------|
| Missing source | Pipeline continues |
| Multiple candidates | Identity clustering |
| Name capitalization | Normalized matching |
| Phone formats | E.164 normalization |
| Unknown ATS fields | Ignored |
| Single-source skills | Lower confidence |
| Ignored sources | Runtime configuration |
| Conflicting dates | More precise date retained |
| Missing required fields | ProjectionError |
| Equal-confidence conflicts | First value wins with provenance |

---

# Assumptions

- LinkedIn extraction is intentionally skipped.
- OCR for scanned PDFs is not implemented.
- Source fetching is sequential.
- Resume parsing uses heuristics.
- Cross-run deduplication is out of scope.

---

# Demo Video

The demo video demonstrates:

- End-to-end execution
- Canonical profile generation
- Recruiter quick-view projection
- Dynamic Source Quality
- Identity Clustering

---

# License

Created as part of the **Eightfold Engineering Intern Assignment**.
