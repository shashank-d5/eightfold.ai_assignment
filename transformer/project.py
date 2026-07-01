"""
project.py — runtime config-driven projection of CanonicalProfile → output dict.

Config schema (JSON):
{
  "fields": [
    {"path": "full_name", "type": "string", "required": true},
    {"path": "primary_email", "from": "emails[0]", "type": "string", "required": true},
    {"path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164"},
    {"path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical"}
  ],
  "include_confidence": true,
  "include_provenance": false,
  "on_missing": "null"   // "null" | "omit" | "error"
}

If no config given, full canonical record is returned.
"""

from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Optional

from .schema import CanonicalProfile
from .normalize import normalize_phone, canonicalize_skill


 
# Path resolver
 

def _resolve_path(obj: Any, path: str) -> Any:
    """
    Resolve dot/bracket path against a nested dict / list.
    Supports:
      full_name            → obj["full_name"]
      emails[0]           → obj["emails"][0]
      skills[].name       → [item["name"] for item in obj["skills"]]
      location.city       → obj["location"]["city"]
    """
    if obj is None:
        return None

    # Handle array-spread: "skills[].name" → list of each item's .name
    spread_match = re.match(r"^([^\[.]+)\[\]\.(.*)", path)
    if spread_match:
        collection_key = spread_match.group(1)
        rest = spread_match.group(2)
        collection = _resolve_path(obj, collection_key)
        if not isinstance(collection, list):
            return []
        return [_resolve_path(item, rest) for item in collection if item is not None]

    # Handle indexed access: "emails[0]"
    index_match = re.match(r"^([^\[.]+)\[(\d+)\](.*)", path)
    if index_match:
        key = index_match.group(1)
        idx = int(index_match.group(2))
        rest = index_match.group(3).lstrip(".")
        sub = _resolve_path(obj, key)
        if not isinstance(sub, list) or idx >= len(sub):
            return None
        return _resolve_path(sub[idx], rest) if rest else sub[idx]

    # Handle dot navigation: "location.city"
    if "." in path:
        head, tail = path.split(".", 1)
        return _resolve_path(_resolve_path(obj, head), tail)

    # Plain key
    if isinstance(obj, dict):
        return obj.get(path)
    return None


 
# Normalizers applicable at projection time
 

def _apply_normalize(value: Any, norm: str) -> Any:
    if value is None:
        return None
    if norm == "E164":
        if isinstance(value, str):
            return normalize_phone(value) or value
    elif norm == "canonical":
        if isinstance(value, list):
            return [canonicalize_skill(str(v)) for v in value]
        if isinstance(value, str):
            return canonicalize_skill(value)
    elif norm == "lowercase":
        if isinstance(value, str):
            return value.lower()
    elif norm == "uppercase":
        if isinstance(value, str):
            return value.upper()
    return value


 
# Type coercion
 

def _coerce(value: Any, type_hint: str) -> Any:
    if value is None:
        return None
    if type_hint == "string":
        return str(value) if not isinstance(value, str) else value
    if type_hint == "string[]":
        if isinstance(value, list):
            return [str(v) for v in value]
        return [str(value)]
    if type_hint == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if type_hint == "boolean":
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("true", "1", "yes")
    return value


 
# Projection
 

class ProjectionError(Exception):
    pass


def project(profile: CanonicalProfile, config: Optional[dict] = None) -> dict:
    """
    Apply config to a CanonicalProfile and return the output dict.
    If config is None, returns the full canonical record.
    """
    # Convert profile to plain dict for path resolution
    profile_dict = profile.model_dump()

    if config is None:
        return _full_output(profile_dict, include_provenance=True, include_confidence=True)

    fields_spec = config.get("fields")
    include_confidence = config.get("include_confidence", False)
    include_provenance = config.get("include_provenance", False)
    on_missing = config.get("on_missing", "null")  # "null" | "omit" | "error"

    if not fields_spec:
        return _full_output(profile_dict, include_provenance, include_confidence)

    output: dict = {}
    errors: list[str] = []

    for field_def in fields_spec:
        out_key = field_def.get("path")
        src_path = field_def.get("from", out_key)  # default: same path as output key
        required = field_def.get("required", False)
        type_hint = field_def.get("type", "string")
        norm = field_def.get("normalize")

        # Resolve
        value = _resolve_path(profile_dict, src_path)

        # Normalize
        if norm and value is not None:
            value = _apply_normalize(value, norm)

        # Coerce
        value = _coerce(value, type_hint)

        # Missing value policy
        if value is None or value == [] or value == "":
            if required:
                if on_missing == "error":
                    errors.append(f"Required field '{out_key}' (from '{src_path}') is missing")
                    continue
                elif on_missing == "omit":
                    continue  # don't include key
                else:  # "null"
                    output[out_key] = None
            else:
                if on_missing == "omit":
                    continue
                output[out_key] = None
        else:
            output[out_key] = value

    if errors:
        raise ProjectionError("; ".join(errors))

    # Append confidence / provenance at top level if requested
    if include_confidence:
        output["overall_confidence"] = profile_dict.get("overall_confidence")
    if include_provenance:
        output["provenance"] = profile_dict.get("provenance", [])

    return output


def _full_output(profile_dict: dict, include_provenance: bool, include_confidence: bool) -> dict:
    out = dict(profile_dict)
    if not include_provenance:
        out.pop("provenance", None)
    if not include_confidence:
        out.pop("overall_confidence", None)
    return out


 
# Config loader
 

def load_config(path: Optional[str]) -> Optional[dict]:
    """Load JSON config from file path, or return None for default output."""
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[WARN] Config file not found: {path} — using default schema")
        return None
    except json.JSONDecodeError as e:
        print(f"[WARN] Config JSON parse error: {e} — using default schema")
        return None


 
# Validate output against requested schema
 

def validate_output(output: dict, config: Optional[dict]) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    if not config:
        return []
    errors = []
    for field_def in config.get("fields", []):
        out_key = field_def.get("path")
        required = field_def.get("required", False)
        type_hint = field_def.get("type", "string")
        value = output.get(out_key)

        if required and (value is None or value == "" or value == []):
            errors.append(f"Required field '{out_key}' is null/empty in output")
            continue

        if value is not None:
            if type_hint == "string" and not isinstance(value, str):
                errors.append(f"Field '{out_key}' expected string, got {type(value).__name__}")
            elif type_hint == "string[]" and not isinstance(value, list):
                errors.append(f"Field '{out_key}' expected string[], got {type(value).__name__}")
            elif type_hint == "number" and not isinstance(value, (int, float)):
                errors.append(f"Field '{out_key}' expected number, got {type(value).__name__}")

    return errors
