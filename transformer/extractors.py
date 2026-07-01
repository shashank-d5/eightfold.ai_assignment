"""
extractors.py — one function per source type.

Each extractor returns a dict with keys matching (a subset of) CanonicalProfile fields,
plus a special key  "_source_id"  identifying which source this came from.
Values are always raw strings (or lists of raw strings); normalization happens later.
"""

from __future__ import annotations
import csv
import json
import re
import io
from pathlib import Path
from typing import Any, Optional

import requests
import pypdf
from docx import Document


 
# Helpers
 

def _safe_read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


 
# 1. Recruiter CSV
 

def extract_csv(path: Path) -> list[dict]:
    """
    Expected columns (case-insensitive, flexible):
      name | email | phone | current_company | title | location | linkedin | github
    Returns one record per row.
    """
    records = []
    try:
        text = _safe_read_text(path)
        if not text:
            return []
        reader = csv.DictReader(io.StringIO(text))
        for i, row in enumerate(reader):
            # Normalise header names to lowercase stripped
            clean = {k.strip().lower().replace(" ", "_"): (v or "").strip()
                     for k, v in row.items()}

            record = {"_source_id": f"recruiter_csv_row_{i}"}

            # Map common header variants
            for name_key in ("name", "full_name", "candidate_name", "fullname"):
                if clean.get(name_key):
                    record["full_name"] = clean[name_key]
                    break

            for email_key in ("email", "email_address", "emails"):
                if clean.get(email_key):
                    record["emails"] = [e.strip() for e in clean[email_key].split(";") if e.strip()]
                    break

            for phone_key in ("phone", "phone_number", "phones", "mobile"):
                if clean.get(phone_key):
                    record["phones"] = [clean[phone_key]]
                    break

            if clean.get("current_company") or clean.get("company"):
                company = clean.get("current_company") or clean.get("company", "")
                title = clean.get("title") or clean.get("current_title") or clean.get("job_title", "")
                record["experience"] = [{"company": company, "title": title}]

            if clean.get("location") or clean.get("city"):
                record["_raw_location"] = clean.get("location") or clean.get("city", "")

            if clean.get("linkedin"):
                record["links"] = {"linkedin": clean["linkedin"]}

            if clean.get("github"):
                existing = record.get("links", {})
                existing["github"] = clean["github"]
                record["links"] = existing

            if clean.get("headline") or clean.get("summary"):
                record["headline"] = clean.get("headline") or clean.get("summary", "")

            if clean.get("skills"):
                record["_raw_skills"] = [s.strip() for s in re.split(r"[,;|]", clean["skills"]) if s.strip()]

            records.append(record)
    except Exception as e:
        print(f"[WARN] CSV extraction failed: {e}")
    return records


 
# 2. ATS JSON
 

_ATS_FIELD_MAP = {
    # ATS key → our key
    "applicant_name": "full_name",
    "applicantName": "full_name",
    "candidate_name": "full_name",
    "candidateName": "full_name",
    "contactEmail": "emails",
    "contact_email": "emails",
    "email_address": "emails",
    "emailAddress": "emails",
    "phone_number": "phones",
    "phoneNumber": "phones",
    "contact_phone": "phones",
    "contactPhone": "phones",
    "job_title": "_ats_title",
    "jobTitle": "_ats_title",
    "current_role": "_ats_title",
    "currentRole": "_ats_title",
    "company": "_ats_company",
    "currentCompany": "_ats_company",
    "current_company": "_ats_company",
    "location": "_raw_location",
    "city": "_raw_location",
    "linkedin_url": "_linkedin",
    "linkedinUrl": "_linkedin",
    "github_url": "_github",
    "githubUrl": "_github",
    "skills": "_raw_skills",
    "technicalSkills": "_raw_skills",
    "technical_skills": "_raw_skills",
    "summary": "headline",
    "professional_summary": "headline",
    "professionalSummary": "headline",
    "years_of_experience": "years_experience",
    "yearsExperience": "years_experience",
    "work_history": "_work_history",
    "workHistory": "_work_history",
    "experience": "_work_history",
    "education": "_education",
}


def _flatten_ats(obj: Any, prefix: str = "") -> dict:
    """Recursively flatten nested ATS JSON into dot-notation keys."""
    flat = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                flat.update(_flatten_ats(v, full_key))
            else:
                flat[full_key] = v
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            flat.update(_flatten_ats(item, f"{prefix}[{i}]"))
    else:
        flat[prefix] = obj
    return flat


def extract_ats_json(path: Path) -> list[dict]:
    """Parse ATS JSON blob (single object or array of objects)."""
    records = []
    try:
        text = _safe_read_text(path)
        if not text:
            return []
        data = json.loads(text)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return []

        for i, blob in enumerate(data):
            record = {"_source_id": f"ats_json_{i}"}

            for ats_key, our_key in _ATS_FIELD_MAP.items():
                if ats_key in blob:
                    val = blob[ats_key]
                    if our_key == "emails":
                        record["emails"] = [val] if isinstance(val, str) else val
                    elif our_key == "phones":
                        record["phones"] = [val] if isinstance(val, str) else val
                    elif our_key == "_raw_skills":
                        if isinstance(val, list):
                            record["_raw_skills"] = val
                        elif isinstance(val, str):
                            record["_raw_skills"] = [s.strip() for s in re.split(r"[,;|]", val) if s.strip()]
                    elif our_key == "_work_history":
                        record["_work_history"] = val
                    elif our_key == "_education":
                        record["_education"] = val
                    elif our_key in ("_ats_title", "_ats_company"):
                        record[our_key] = str(val)
                    elif our_key == "_linkedin":
                        existing = record.get("links", {})
                        existing["linkedin"] = str(val)
                        record["links"] = existing
                    elif our_key == "_github":
                        existing = record.get("links", {})
                        existing["github"] = str(val)
                        record["links"] = existing
                    else:
                        record[our_key] = val

            # Combine title+company into experience if available
            if record.get("_ats_title") or record.get("_ats_company"):
                record["experience"] = [{
                    "company": record.pop("_ats_company", None),
                    "title": record.pop("_ats_title", None),
                }]

            # Parse work_history array
            if "_work_history" in record:
                wh = record.pop("_work_history")
                if isinstance(wh, list):
                    exps = []
                    for job in wh:
                        if isinstance(job, dict):
                            exps.append({
                                "company": job.get("company") or job.get("employer") or job.get("organization"),
                                "title": job.get("title") or job.get("role") or job.get("position"),
                                "start": job.get("start") or job.get("start_date") or job.get("startDate"),
                                "end": job.get("end") or job.get("end_date") or job.get("endDate"),
                                "summary": job.get("summary") or job.get("description"),
                            })
                    if exps:
                        record["experience"] = exps

            # Parse education array
            if "_education" in record:
                edu = record.pop("_education")
                if isinstance(edu, list):
                    edus = []
                    for e in edu:
                        if isinstance(e, dict):
                            edus.append({
                                "institution": e.get("institution") or e.get("school") or e.get("university"),
                                "degree": e.get("degree"),
                                "field": e.get("field") or e.get("major") or e.get("field_of_study"),
                                "end_year": e.get("end_year") or e.get("graduation_year") or e.get("year"),
                            })
                    if edus:
                        record["_education_list"] = edus

            records.append(record)
    except json.JSONDecodeError as e:
        print(f"[WARN] ATS JSON parse error: {e}")
    except Exception as e:
        print(f"[WARN] ATS JSON extraction failed: {e}")
    return records


 
# 3. Resume PDF / DOCX
 

def _extract_text_from_pdf(path: Path) -> str:
    try:
        reader = pypdf.PdfReader(str(path))
        pages = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                pages.append(t)
        return "\n".join(pages)
    except Exception as e:
        print(f"[WARN] PDF read error {path}: {e}")
        return ""


def _extract_text_from_docx(path: Path) -> str:
    try:
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        print(f"[WARN] DOCX read error {path}: {e}")
        return ""


_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\+\d{7,15})(?!\d)"
)
_LINKEDIN_RE = re.compile(r"linkedin\.com/in/[\w\-]+", re.IGNORECASE)
_GITHUB_RE = re.compile(r"github\.com/[\w\-]+", re.IGNORECASE)

_SKILL_KEYWORDS = [
    "python", "java", "javascript", "typescript", "react", "node", "spring",
    "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
    "pytorch", "tensorflow", "scikit-learn", "sklearn", "pandas", "numpy",
    "langchain", "rag", "llm", "huggingface", "streamlit",
    "power bi", "powerbi", "git", "ci/cd", "rest", "graphql",
    "fastapi", "flask", "django", "kotlin", "swift", "scala", "rust", "go",
    "c++", "c#", "ruby", "spark", "kafka",
]

_SECTION_HEADERS = re.compile(
    r"^(experience|work experience|employment|education|skills|technical skills|"
    r"projects|certifications|summary|objective|about|profile)\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE
)

_DATE_RANGE_RE = re.compile(
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4})"
    r"\s*[-–—to]+\s*"
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4}|present|current|now)",
    re.IGNORECASE
)


def _parse_resume_text(text: str, source_id: str) -> dict:
    record = {"_source_id": source_id}

    # Emails
    emails = list(dict.fromkeys(_EMAIL_RE.findall(text)))
    if emails:
        record["emails"] = emails

    # Phones
    phones = list(dict.fromkeys(m.group(0) for m in _PHONE_RE.finditer(text)))
    if phones:
        record["phones"] = phones[:3]

    # LinkedIn / GitHub
    li = _LINKEDIN_RE.search(text)
    gh = _GITHUB_RE.search(text)
    if li or gh:
        record["links"] = {}
        if li:
            record["links"]["linkedin"] = "https://" + li.group(0)
        if gh:
            record["links"]["github"] = "https://" + gh.group(0)

    # Name heuristic: first non-empty line that looks like a name
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines[:8]:
        # Skip lines that are clearly not names
        if (len(line.split()) in (2, 3) and
                not any(c.isdigit() for c in line) and
                not re.search(r"[@|/\\]", line) and
                line[0].isupper()):
            record["full_name"] = line
            break

    # Skills — keyword scanning
    text_lower = text.lower()
    found_skills = []
    for kw in _SKILL_KEYWORDS:
        # Word-boundary match
        if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
            found_skills.append(kw)
    if found_skills:
        record["_raw_skills"] = found_skills

    # Experience — detect date ranges with surrounding context
    exp_list = []
    for m in _DATE_RANGE_RE.finditer(text):
        start_idx = max(0, m.start() - 200)
        end_idx = min(len(text), m.end() + 200)
        context = text[start_idx:end_idx]
        exp_list.append({
            "start": m.group(1),
            "end": m.group(2) if m.group(2).lower() not in ("present", "current", "now") else None,
            "_context": context[:150],
        })
    if exp_list:
        record["_raw_experience"] = exp_list

    # Headline — look for a short line near the top after the name
    for line in lines[1:6]:
        if 5 < len(line) < 120 and not _EMAIL_RE.search(line) and not _PHONE_RE.search(line):
            record["headline"] = line
            break

    return record


def extract_resume(path: Path) -> list[dict]:
    """Extract from PDF or DOCX resume."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        text = _extract_text_from_pdf(path)
        source_id = f"resume_pdf:{path.name}"
    elif ext in (".docx", ".doc"):
        text = _extract_text_from_docx(path)
        source_id = f"resume_docx:{path.name}"
    else:
        print(f"[WARN] Unsupported resume format: {path.suffix}")
        return []

    if not text.strip():
        print(f"[WARN] Empty text extracted from {path}")
        return []

    return [_parse_resume_text(text, source_id)]


 
# 4. GitHub Profile
 

def extract_github(username_or_url: str) -> list[dict]:
    """
    Fetch public GitHub profile via REST API.
    username_or_url: 'octocat' or 'https://github.com/octocat'
    """
    try:
        # Extract username
        username = re.sub(r"https?://github\.com/", "", username_or_url).strip("/").split("/")[0]
        if not username:
            return []

        headers = {"Accept": "application/vnd.github.v3+json"}
        user_resp = requests.get(f"https://api.github.com/users/{username}",
                                  headers=headers, timeout=10)
        if user_resp.status_code != 200:
            print(f"[WARN] GitHub API returned {user_resp.status_code} for {username}")
            return []

        user = user_resp.json()
        record = {"_source_id": f"github:{username}"}

        if user.get("name"):
            record["full_name"] = user["name"]
        if user.get("email"):
            record["emails"] = [user["email"]]
        if user.get("blog"):
            record["links"] = {"portfolio": user["blog"]}
        record["links"] = record.get("links", {})
        record["links"]["github"] = f"https://github.com/{username}"
        if user.get("bio"):
            record["headline"] = user["bio"]
        if user.get("location"):
            record["_raw_location"] = user["location"]

        # Fetch repos to infer skills from languages
        repos_resp = requests.get(
            f"https://api.github.com/users/{username}/repos",
            headers=headers,
            params={"per_page": 30, "sort": "updated"},
            timeout=10
        )
        if repos_resp.status_code == 200:
            repos = repos_resp.json()
            lang_counts: dict[str, int] = {}
            for repo in repos:
                lang = repo.get("language")
                if lang:
                    lang_counts[lang] = lang_counts.get(lang, 0) + 1
            if lang_counts:
                # Sort by frequency; top languages become skills
                sorted_langs = sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)
                record["_raw_skills"] = [lang for lang, _ in sorted_langs[:10]]
                record["_github_repo_count"] = len(repos)

        return [record]
    except requests.exceptions.Timeout:
        print("[WARN] GitHub API timeout")
        return []
    except Exception as e:
        print(f"[WARN] GitHub extraction failed: {e}")
        return []


 
# 5. Recruiter Notes (free text .txt)
 

_NOTE_PATTERNS = {
    "full_name": [
        re.compile(r"candidate(?:\s+name)?[:\s]+([A-Z][a-z]+(?: [A-Z][a-z]+)+)", re.IGNORECASE),
        re.compile(r"name[:\s]+([A-Z][a-z]+(?: [A-Z][a-z]+)+)", re.IGNORECASE),
    ],
    "emails": [_EMAIL_RE],
    "phones": [_PHONE_RE],
    "_raw_location": [
        re.compile(r"(?:location|based in|lives in|from)[:\s]+([A-Za-z ,]+?)(?:\n|,|$)", re.IGNORECASE),
    ],
    "headline": [
        re.compile(r"(?:role|position|title|applying for)[:\s]+(.+?)(?:\n|$)", re.IGNORECASE),
    ],
    "_raw_skills": None,  # handled below
}


def extract_notes(path: Path) -> list[dict]:
    """Extract from free-text recruiter notes."""
    text = _safe_read_text(path)
    if not text:
        return []

    record = {"_source_id": f"recruiter_notes:{path.name}"}

    for field, patterns in _NOTE_PATTERNS.items():
        if patterns is None:
            continue
        for pat in patterns:
            m = pat.search(text)
            if m:
                if field == "emails":
                    record["emails"] = list(dict.fromkeys(_EMAIL_RE.findall(text)))
                elif field == "phones":
                    record["phones"] = [p.group(0) for p in _PHONE_RE.finditer(text)][:3]
                else:
                    record[field] = m.group(1).strip()
                break

    # Skills from notes
    text_lower = text.lower()
    found_skills = [kw for kw in _SKILL_KEYWORDS if re.search(r"\b" + re.escape(kw) + r"\b", text_lower)]
    if found_skills:
        record["_raw_skills"] = found_skills

    return [record] if len(record) > 1 else []
