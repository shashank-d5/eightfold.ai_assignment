"""
pipeline.py — Orchestrator.

Stages:
  1. Source Dialect Interpreters (extractors)
  2. Canonicalization Bus (normalizers — already inside merge)
  3. Identity Clustering Layer (grouper)
  4. Staged Consensus Engine (merge)
  5. Trust & Corroboration Vault (confidence + provenance — inside merge)
  6. Projection Gateway (project)
  7. Schema Vestibule (validate)

Supports source veto via config["ignored_sources"].
"""

from __future__ import annotations
import re
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from .extractors import (
    extract_csv,
    extract_ats_json,
    extract_resume,
    extract_github,
    extract_notes,
)
from .grouper import group_records_by_identity
from .merge import merge_records
from .project import project, load_config, validate_output
from .schema import CanonicalProfile


# ---------------------------------------------------------------------------
# Source type detection
# ---------------------------------------------------------------------------

def _detect_source_type(source: str) -> str:
    """
    Return one of: csv | ats_json | resume | github | notes | unknown
    """
    src = source.strip()
    # URL-based
    if src.startswith("https://github.com/") or re.match(r"^[\w\-]+$", src):
        return "github_url"

    path = Path(src)
    ext = path.suffix.lower()

    if ext == ".csv":
        return "csv"
    if ext == ".json":
        return "ats_json"
    if ext in (".pdf", ".docx", ".doc"):
        return "resume"
    if ext == ".txt":
        return "notes"
    return "unknown"


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(
    sources: list[str],
    config_path: Optional[str] = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """
    End-to-end pipeline.

    Args:
        sources: list of file paths or GitHub usernames/URLs
        config_path: optional path to JSON projection config
        verbose: print stage timing

    Returns:
        dict with keys:
          "profiles"        → list of full canonical profiles (dicts)
          "profile"         → best (highest confidence) profile (dict)
          "output"          → projected output for best profile
          "validation_errors" → list of validation errors
          "elapsed_ms"      → int
    """
    t0 = time.perf_counter()

    # --- Load config early (for source veto) ---
    config = load_config(config_path)
    ignored_sources = set(config.get("ignored_sources", [])) if config else set()

    # --- Stage 1: Detect + Extract (with source veto) ---
    all_records: list[dict] = []
    for src in sources:
        src = src.strip()
        if not src:
            continue

        src_type = _detect_source_type(src)
        
        # Source Veto: skip if configured
        if src_type in ignored_sources:
            if verbose:
                print(f"  [veto] {src_type} ignored per config: {src}")
            continue

        if verbose:
            print(f"  [extract] {src_type}: {src}")

        try:
            if src_type == "csv":
                records = extract_csv(Path(src))
            elif src_type == "ats_json":
                records = extract_ats_json(Path(src))
            elif src_type == "resume":
                records = extract_resume(Path(src))
            elif src_type == "github_url":
                records = extract_github(src)
            elif src_type == "notes":
                records = extract_notes(Path(src))
            else:
                print(f"[WARN] Unknown source type for: {src}")
                records = []

            if verbose:
                print(f"         → {len(records)} record(s)")
            all_records.extend(records)

        except Exception as e:
            # Graceful degradation: log and continue
            print(f"[WARN] Failed to extract from {src}: {e}")

    if verbose:
        print(f"  [extract] Total raw records: {len(all_records)}")

    # --- Stage 2: Identity Clustering Layer ---
    clusters = group_records_by_identity(all_records)
    if verbose:
        print(f"  [identity] {len(all_records)} raw records → {len(clusters)} candidate cluster(s)")

    # --- Stage 3: Merge each cluster ---
    profiles = [merge_records(cluster) for cluster in clusters]
    
    # Sort by confidence (best first)
    profiles.sort(key=lambda p: p.overall_confidence, reverse=True)
    
    if verbose:
        for i, p in enumerate(profiles):
            print(f"  [merge] Candidate {i+1}: {p.full_name or 'Unknown'} (conf: {p.overall_confidence:.3f})")

    # --- Stage 4: Pick best profile for output ---
    best_profile = profiles[0] if profiles else CanonicalProfile(candidate_id=str(uuid.uuid4()))

    # --- Stage 5: Project ---
    output = project(best_profile, config)

    # --- Stage 6: Validate ---
    errors = validate_output(output, config)

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    return {
        "profiles": [p.model_dump() for p in profiles],
        "profile": best_profile.model_dump(),
        "output": output,
        "validation_errors": errors,
        "elapsed_ms": elapsed_ms,
    }