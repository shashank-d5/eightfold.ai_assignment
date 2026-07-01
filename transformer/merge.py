"""
merge.py — Staged Consensus Engine.

Key upgrades:
  1. Dynamic Source Quality: scores sources by data completeness, not file extension.
  2. Granular Experience Merging: picks most precise date ranges for overlapping jobs.
  3. Confidence based on corroboration + source quality.
"""

from __future__ import annotations
import re
import uuid
from collections import defaultdict
from typing import Any, Optional

from .schema import (
    CanonicalProfile, Location, Links, Skill, Experience,
    Education, ProvenanceEntry,
)
from .normalize import (
    normalize_phone, normalize_date, normalize_country,
    normalize_email, canonicalize_skill,
)


# ---------------------------------------------------------------------------
# Dynamic Source Quality (Replaces hardcoded weights)
# ---------------------------------------------------------------------------

def _calculate_source_quality(record: dict) -> float:
    """
    Score a source by how much high-signal data it actually provided.
    A source that gives Name + Email + Phone is better than one that gives just Name.
    This adapts to garbage sources automatically.
    """
    # High-value fields that strongly identify a candidate
    core_fields = ["full_name", "emails", "phones", "_raw_location"]
    # Bonus fields that show depth
    bonus_fields = ["headline", "_raw_skills", "years_experience"]
    
    populated_core = sum(1 for f in core_fields if record.get(f))
    populated_bonus = sum(1 for f in bonus_fields if record.get(f))
    
    # Max score if all core + half bonus are filled
    raw_score = (populated_core / len(core_fields)) * 0.7 + (populated_bonus / len(bonus_fields)) * 0.3
    
    # Clamp between 0.2 (barely trust) and 0.95 (high trust). Never 0, never 1.
    return max(0.2, min(0.95, raw_score))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm_name(name: Optional[str]) -> str:
    if not name:
        return ""
    return re.sub(r"\s+", " ", name.strip().lower())


def _parse_location(raw: str) -> Location:
    """Best-effort parse of a free-form location string."""
    raw = raw.strip()
    if not raw:
        return Location()

    # Try comma-separated
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) >= 3:
        # city, region, country
        loc = Location()
        loc.city = parts[0]
        loc.region = parts[1]
        loc.country = normalize_country(parts[2]) or parts[2]
        return loc
    elif len(parts) == 2:
        # Try to interpret second part as country
        loc = Location()
        loc.city = parts[0]
        country = normalize_country(parts[1])
        if country:
            loc.country = country
        else:
            loc.region = parts[1]
        return loc

    # No comma: try to split by last space to separate city from country
    # Example: "Hyderabad India" → city="Hyderabad", country="IN"
    if " " in raw:
        last_space = raw.rfind(" ")
        city_part = raw[:last_space].strip()
        potential_country = raw[last_space+1:].strip()
        country = normalize_country(potential_country)
        if country:
            loc = Location()
            loc.city = city_part
            loc.country = country
            return loc
        else:
            # If the last token isn't a country, treat whole as city
            return Location(city=raw)

    # Entire string could be a country
    country = normalize_country(raw)
    if country:
        return Location(country=country)
    else:
        return Location(city=raw)

def _parse_experience(raw_exp: Any, source_id: str) -> list[dict]:
    """Parse raw experience into dicts for later merging, keeping raw strings."""
    exps = []
    if not isinstance(raw_exp, list):
        return exps
    for item in raw_exp:
        if not isinstance(item, dict):
            continue
        start_raw = item.get("start") or ""
        end_raw = item.get("end") or ""
        start_norm = normalize_date(start_raw) if start_raw else None
        end_norm = None if end_raw.lower() in ("present", "current", "now", "") else normalize_date(end_raw)
        exps.append({
            "company": item.get("company"),
            "title": item.get("title"),
            "start_raw": start_raw,
            "end_raw": end_raw,
            "start": start_norm,
            "end": end_norm,
            "summary": item.get("summary") or item.get("_context"),
            "_source": source_id,
        })
    return exps


def _merge_experience_lists(exp_lists: list[list[dict]]) -> list[Experience]:
    """
    Groups experience by normalized company name.
    For duplicates, picks the entry with the most precise dates (by raw string length).
    """
    grouped: dict[str, dict] = {}
    
    for exp_list in exp_lists:
        for exp in exp_list:
            if not exp.get("company"):
                continue
            key = _norm_name(exp["company"])
            if key not in grouped:
                grouped[key] = exp.copy()
            else:
                existing = grouped[key]
                # Compare raw start length for precision
                if exp.get("start_raw") and len(exp["start_raw"]) > len(existing.get("start_raw", "")):
                    existing["start_raw"] = exp["start_raw"]
                    existing["start"] = exp["start"]  # normalized
                # Compare raw end length for precision
                if exp.get("end_raw") and len(exp["end_raw"]) > len(existing.get("end_raw", "")):
                    existing["end_raw"] = exp["end_raw"]
                    existing["end"] = exp["end"]  # normalized
                # Concatenate summaries if different
                if exp.get("summary"):
                    existing_summary = existing.get("summary") or ""
                    if exp["summary"] not in existing_summary:
                        existing["summary"] = (existing.get("summary") or "") + " | " + exp["summary"]
    
    return [Experience(
        company=v.get("company"),
        title=v.get("title"),
        start=v.get("start"),
        end=v.get("end"),
        summary=v.get("summary"),
    ) for v in grouped.values()]

def _parse_education(edu_list: Any) -> list[Education]:
    result = []
    if not isinstance(edu_list, list):
        return result
    for item in edu_list:
        if not isinstance(item, dict):
            continue
        end_year = item.get("end_year")
        if end_year:
            try:
                end_year = int(str(end_year)[:4])
            except (ValueError, TypeError):
                end_year = None
        result.append(Education(
            institution=item.get("institution"),
            degree=item.get("degree"),
            field=item.get("field"),
            end_year=end_year,
        ))
    return result


# ---------------------------------------------------------------------------
# Main merge function
# ---------------------------------------------------------------------------

def merge_records(records: list[dict]) -> CanonicalProfile:
    """
    Merge a cluster of records (belonging to the same candidate) into one CanonicalProfile.
    
    Uses dynamic source quality scoring, granular experience merging, and
    full provenance tracking.
    """
    if not records:
        return CanonicalProfile(candidate_id=str(uuid.uuid4()))

    provenance: list[ProvenanceEntry] = []
    confidence_scores: list[float] = []

    # --- Compute source quality for each record ---
    source_qualities = {rec["_source_id"]: _calculate_source_quality(rec) for rec in records}

    # ---- emails ----
    seen_emails: dict[str, str] = {}  # normalized -> source_id
    for rec in records:
        for raw_email in rec.get("emails", []):
            norm = normalize_email(raw_email)
            if norm and norm not in seen_emails:
                seen_emails[norm] = rec["_source_id"]

    all_emails = list(seen_emails.keys())
    for email, src in seen_emails.items():
        provenance.append(ProvenanceEntry(field="emails", source=src, method="direct"))

    # ---- phones ----
    seen_phones: dict[str, str] = {}
    for rec in records:
        for raw_phone in rec.get("phones", []):
            norm = normalize_phone(raw_phone)
            if norm and norm not in seen_phones:
                seen_phones[norm] = rec["_source_id"]

    all_phones = list(seen_phones.keys())
    for phone, src in seen_phones.items():
        provenance.append(ProvenanceEntry(field="phones", source=src, method="normalize_e164"))

    # ---- full_name: pick highest-quality source ----
    name_candidates: list[tuple[str, str, float]] = []
    for rec in records:
        if rec.get("full_name"):
            name_candidates.append((rec["full_name"], rec["_source_id"], source_qualities[rec["_source_id"]]))
    full_name = None
    if name_candidates:
        best = max(name_candidates, key=lambda x: x[2])
        full_name = best[0]
        provenance.append(ProvenanceEntry(field="full_name", source=best[1], method="direct"))
        confidence_scores.append(best[2])

    # ---- headline ----
    headline_candidates = [(rec["headline"], rec["_source_id"], source_qualities[rec["_source_id"]])
                           for rec in records if rec.get("headline")]
    headline = None
    if headline_candidates:
        best = max(headline_candidates, key=lambda x: x[2])
        headline = best[0]
        provenance.append(ProvenanceEntry(field="headline", source=best[1], method="direct"))

    # ---- location ----
    location = None
    for rec in sorted(records, key=lambda r: source_qualities[r["_source_id"]], reverse=True):
        raw_loc = rec.get("_raw_location")
        if raw_loc:
            location = _parse_location(raw_loc)
            provenance.append(ProvenanceEntry(field="location", source=rec["_source_id"], method="parse"))
            break

    # ---- links ----
    merged_links: dict[str, str] = {}
    for rec in records:
        lk = rec.get("links") or {}
        for key in ("linkedin", "github", "portfolio"):
            if lk.get(key) and key not in merged_links:
                merged_links[key] = lk[key]
                provenance.append(ProvenanceEntry(field=f"links.{key}", source=rec["_source_id"], method="direct"))
    links = Links(**{k: v for k, v in merged_links.items() if k in ("linkedin", "github", "portfolio")}) if merged_links else None

    # ---- years_experience ----
    years_exp = None
    for rec in sorted(records, key=lambda r: source_qualities[r["_source_id"]], reverse=True):
        ye = rec.get("years_experience")
        if ye is not None:
            try:
                years_exp = float(ye)
                provenance.append(ProvenanceEntry(field="years_experience", source=rec["_source_id"], method="direct"))
                break
            except (TypeError, ValueError):
                pass

    # ---- skills: union across sources, weighted by frequency ----
    skill_sources: dict[str, list[str]] = defaultdict(list)
    for rec in records:
        raw_skills = rec.get("_raw_skills", [])
        for raw in raw_skills:
            canonical = canonicalize_skill(str(raw))
            skill_sources[canonical].append(rec["_source_id"])

    total_sources = max(len(records), 1)
    skills: list[Skill] = []
    for name, sources in skill_sources.items():
        freq_weight = len(sources) / total_sources
        avg_source_quality = sum(source_qualities[s] for s in sources) / len(sources)
        conf = min(1.0, freq_weight * 0.5 + avg_source_quality * 0.5)
        skills.append(Skill(name=name, confidence=round(conf, 3), sources=list(dict.fromkeys(sources))))

    skills.sort(key=lambda s: s.confidence, reverse=True)

    if skills:
        provenance.append(ProvenanceEntry(
            field="skills",
            source=",".join(dict.fromkeys(s for sk in skills for s in sk.sources)),
            method="canonicalize+merge"
        ))

    # ---- experience: GRANULAR MERGE ----
    all_exp_lists = []
    for rec in records:
        raw_exp = rec.get("experience") or rec.get("_raw_experience", [])
        parsed = _parse_experience(raw_exp, rec["_source_id"])
        if parsed:
            all_exp_lists.append(parsed)
    
    all_experience = _merge_experience_lists(all_exp_lists)
    for exp in all_experience:
        provenance.append(ProvenanceEntry(
            field="experience", 
            source=",".join(r["_source_id"] for r in records), 
            method="granular_merge"
        ))

    # ---- education ----
    all_education: list[Education] = []
    seen_edu_keys: set[str] = set()
    for rec in records:
        edu_list = rec.get("_education_list", [])
        for edu in _parse_education(edu_list):
            key = f"{_norm_name(edu.institution)}|{edu.end_year}"
            if key not in seen_edu_keys:
                seen_edu_keys.add(key)
                all_education.append(edu)

    # ---- overall_confidence ----
    n_sources = len(records)
    populated_fields = sum(1 for v in [full_name, all_emails, all_phones, location, links, headline, skills]
                           if v and (not isinstance(v, list) or len(v) > 0))
    field_coverage = populated_fields / 7
    avg_source_quality = sum(source_qualities.values()) / n_sources if n_sources else 0
    overall_confidence = round(min(1.0, field_coverage * 0.5 + avg_source_quality * 0.5), 3)

    candidate_id = str(uuid.uuid5(uuid.NAMESPACE_DNS,
                                   (full_name or "") + "|" + (all_emails[0] if all_emails else "")))

    return CanonicalProfile(
        candidate_id=candidate_id,
        full_name=full_name,
        emails=all_emails,
        phones=all_phones,
        location=location,
        links=links,
        headline=headline,
        years_experience=years_exp,
        skills=skills,
        experience=all_experience,
        education=all_education,
        provenance=provenance,
        overall_confidence=overall_confidence,
    )