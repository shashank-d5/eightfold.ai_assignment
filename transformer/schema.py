"""
Canonical schema definitions for the candidate transformer.
All internal types live here; downstream code imports from this module.
"""

from __future__ import annotations
from typing import Any, List, Optional
from pydantic import BaseModel, field_validator
import re


class Location(BaseModel):
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None   # ISO-3166 alpha-2


class Links(BaseModel):
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other: List[str] = []


class Skill(BaseModel):
    name: str                        # canonicalized
    confidence: float                # 0.0 – 1.0
    sources: List[str] = []         # source IDs that mentioned this skill


class Experience(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start: Optional[str] = None     # YYYY-MM
    end: Optional[str] = None       # YYYY-MM or None (current)
    summary: Optional[str] = None


class Education(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    end_year: Optional[int] = None


class ProvenanceEntry(BaseModel):
    field: str
    source: str                      # e.g. "recruiter_csv", "github", "resume"
    method: str                      # e.g. "direct", "regex", "llm_extract", "api"


class CanonicalProfile(BaseModel):
    candidate_id: str
    full_name: Optional[str] = None
    emails: List[str] = []
    phones: List[str] = []           # E.164
    location: Optional[Location] = None
    links: Optional[Links] = None
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: List[Skill] = []
    experience: List[Experience] = []
    education: List[Education] = []
    provenance: List[ProvenanceEntry] = []
    overall_confidence: float = 0.0
