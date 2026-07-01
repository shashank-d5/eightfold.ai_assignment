#!/usr/bin/env python3
"""
cli.py — Command-line interface for the candidate data transformer.

Usage examples:
  # Default canonical output (all fields + provenance)
  python cli.py --sources sample_inputs/recruiter_export.csv sample_inputs/ats_export.json

  # Custom config (recruiter quick-view)
  python cli.py --sources sample_inputs/recruiter_export.csv sample_inputs/ats_export.json \\
                --config config/recruiter_view.json

  # Multiple sources including resume and notes
  python cli.py --sources sample_inputs/recruiter_export.csv \\
                           sample_inputs/ats_export.json \\
                           sample_inputs/sample_resume_priya.pdf \\
                           sample_inputs/recruiter_notes_priya.txt \\
                --config config/recruiter_view.json \\
                --output sample_outputs/priya_profile.json \\
                --verbose

  # GitHub source
  python cli.py --sources https://github.com/torvalds \\
                --output sample_outputs/github_profile.json
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent))

from transformer.pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Multi-source candidate data transformer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--sources", "-s",
        nargs="+",
        required=True,
        help="One or more source files or GitHub URLs (CSV, JSON, PDF, DOCX, TXT, github.com/username)",
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="Path to JSON projection config. Omit for full canonical output.",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Write JSON output to this file. Prints to stdout if omitted.",
    )
    parser.add_argument(
        "--full-profile",
        action="store_true",
        help="Also write the internal canonical profile (with provenance) alongside output.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Output all candidate profiles as a JSON array (default: only the most complete one).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print pipeline stage logs.",
    )

    args = parser.parse_args()

    print(f"\nEightfold Candidate Transformer")
    print(f"Sources  : {', '.join(args.sources)}")
    print(f"Config   : {args.config or '(default — full canonical)'}")
    print("-" * 60)

    result = run_pipeline(
        sources=args.sources,
        config_path=args.config,
        verbose=args.verbose,
    )

    profiles = result.get("profiles", [])
    best_profile = result.get("profile", {})
    validation_errors = result.get("validation_errors", [])

    print(f"\n✓ Merged {len(profiles)} candidate(s)")
    if profiles:
        print(f"  → Best candidate confidence: {best_profile.get('overall_confidence', 0):.3f}")

    if validation_errors:
        print("\n[VALIDATION ERRORS]")
        for err in validation_errors:
            print(f"  ✗ {err}")
    else:
        print(f"\n✓ Output valid  |  elapsed: {result['elapsed_ms']}ms")

    # Determine what to output
    if args.all:
        output_data = profiles  # Array of all profiles
    else:
        output_data = result.get("output", {})  # Best candidate projected output

    output_json = json.dumps(output_data, indent=2, ensure_ascii=False, default=str)

    # Also full profile if requested (for the best candidate only)
    profile_json = json.dumps(best_profile, indent=2, ensure_ascii=False, default=str)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"✓ Output written → {args.output}")

        if args.full_profile:
            profile_path = str(args.output).replace(".json", "_full_profile.json")
            Path(profile_path).write_text(profile_json, encoding="utf-8")
            print(f"✓ Full profile   → {profile_path}")
    else:
        print("\n--- OUTPUT ---")
        print(output_json)

    if validation_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()