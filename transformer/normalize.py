"""
normalize.py — deterministic, stateless normalizers.
Each function accepts a raw string and returns a clean string (or None on failure).
"""

from __future__ import annotations
import re
import datetime
from typing import Optional

import phonenumbers
import pycountry


# ---------------------------------------------------------------------------
# Phone  →  E.164
# ---------------------------------------------------------------------------

def normalize_phone(raw: str, default_region: str = "US") -> Optional[str]:
    """Return E.164 or None if unparseable."""
    if not raw:
        return None
    try:
        parsed = phonenumbers.parse(raw, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Date  →  YYYY-MM
# ---------------------------------------------------------------------------

_MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}



# Month name to number mapping (full and abbreviated)
_MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    "january": "01", "february": "02", "march": "03", "april": "04",
    "june": "06", "july": "07", "august": "08", "september": "09",
    "october": "10", "november": "11", "december": "12",
}

def normalize_date(raw: str) -> Optional[str]:
    """Return YYYY-MM or None."""
    if not raw:
        return None
    raw = raw.strip()
    if raw.lower() in ("present", "current", "now", "—", "-", ""):
        return None

    # Try ISO format: YYYY-MM or YYYY-MM-DD
    m = re.match(r"(\d{4})-(\d{2})(?:-\d{2})?", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    # Try MM/YYYY or MM-YYYY
    m = re.match(r"(\d{1,2})[/-](\d{4})", raw)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"

    # Try Month Name YYYY (e.g., "Dec 2022", "December 2022")
    m = re.match(r"([A-Za-z]+)\s+(\d{4})", raw)
    if m:
        month_name = m.group(1).lower()
        year = m.group(2)
        if month_name in _MONTH_MAP:
            return f"{year}-{_MONTH_MAP[month_name]}"

    # Try just a year
    if re.match(r"^\d{4}$", raw):
        return f"{raw}-01"

    return None


# ---------------------------------------------------------------------------
# Country  →  ISO-3166 alpha-2
# ---------------------------------------------------------------------------

def normalize_country(raw: str) -> Optional[str]:
    """Return ISO-3166 alpha-2 ('IN', 'US', …) or None."""
    if not raw:
        return None
    raw = raw.strip()
    # Already alpha-2
    if re.match(r"^[A-Za-z]{2}$", raw):
        c = pycountry.countries.get(alpha_2=raw.upper())
        return c.alpha_2 if c else None
    # Try alpha-3
    if re.match(r"^[A-Za-z]{3}$", raw):
        c = pycountry.countries.get(alpha_3=raw.upper())
        return c.alpha_2 if c else None
    # Fuzzy name search
    try:
        results = pycountry.countries.search_fuzzy(raw)
        if results:
            return results[0].alpha_2
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Skill canonicalization
# ---------------------------------------------------------------------------

_SKILL_ALIASES: dict[str, str] = {
    # Languages
    "js": "JavaScript", "javascript": "JavaScript",
    "ts": "TypeScript", "typescript": "TypeScript",
    "py": "Python", "python": "Python",
    "java": "Java",
    "golang": "Go", "go": "Go",
    "c#": "C#", "csharp": "C#",
    "c++": "C++", "cpp": "C++",
    "ruby": "Ruby", "rb": "Ruby",
    "rust": "Rust",
    "kotlin": "Kotlin",
    "swift": "Swift",
    "scala": "Scala",
    "r": "R",
    # Frameworks / libs
    "react": "React", "reactjs": "React", "react.js": "React",
    "vue": "Vue.js", "vuejs": "Vue.js", "vue.js": "Vue.js",
    "angular": "Angular", "angularjs": "Angular",
    "next": "Next.js", "nextjs": "Next.js", "next.js": "Next.js",
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "spring": "Spring Boot", "spring boot": "Spring Boot", "springboot": "Spring Boot",
    "node": "Node.js", "nodejs": "Node.js", "node.js": "Node.js",
    "express": "Express.js", "expressjs": "Express.js",
    # ML / AI
    "pytorch": "PyTorch", "torch": "PyTorch",
    "tensorflow": "TensorFlow", "tf": "TensorFlow",
    "sklearn": "scikit-learn", "scikit learn": "scikit-learn", "scikit-learn": "scikit-learn",
    "langchain": "LangChain",
    "huggingface": "Hugging Face", "hf": "Hugging Face",
    # Data
    "postgres": "PostgreSQL", "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB", "mongo": "MongoDB",
    "redis": "Redis",
    "elasticsearch": "Elasticsearch", "es": "Elasticsearch",
    "kafka": "Apache Kafka",
    "spark": "Apache Spark",
    "pandas": "pandas",
    "numpy": "NumPy",
    # DevOps / Cloud
    "aws": "AWS",
    "gcp": "Google Cloud", "google cloud": "Google Cloud",
    "azure": "Azure",
    "docker": "Docker",
    "k8s": "Kubernetes", "kubernetes": "Kubernetes",
    "terraform": "Terraform",
    "ci/cd": "CI/CD", "cicd": "CI/CD",
    "git": "Git", "github": "GitHub",
    # Other
    "sql": "SQL",
    "rest": "REST APIs", "rest api": "REST APIs", "restful": "REST APIs",
    "graphql": "GraphQL",
    "power bi": "Power BI", "powerbi": "Power BI",
    "streamlit": "Streamlit",
    "rag": "RAG",
    "llm": "LLMs", "llms": "LLMs",
}


def canonicalize_skill(raw: str) -> str:
    """Return the canonical skill name for a raw string."""
    key = raw.strip().lower()
    return _SKILL_ALIASES.get(key, raw.strip().title())


def normalize_email(raw: str) -> Optional[str]:
    """Lowercase and validate basic email shape."""
    if not raw:
        return None
    e = raw.strip().lower()
    if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e):
        return e
    return None
