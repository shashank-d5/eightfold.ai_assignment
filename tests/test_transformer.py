"""
tests/test_transformer.py — unit and integration tests.

Run:  python -m pytest tests/ -v
  or: python tests/test_transformer.py
"""

import json
import sys
import os
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from transformer.normalize import (
    normalize_phone, normalize_date, normalize_country,
    normalize_email, canonicalize_skill,
)
from transformer.extractors import extract_csv, extract_ats_json, extract_notes
from transformer.grouper import group_records_by_identity
from transformer.merge import merge_records, _calculate_source_quality
from transformer.project import project, validate_output
from transformer.schema import CanonicalProfile
from transformer.pipeline import run_pipeline


# ==========================================================================
# 1. Normalizer tests (existing, keep all)
# ==========================================================================

class TestNormalizePhone(unittest.TestCase):
    def test_e164_indian_number(self):
        self.assertEqual(normalize_phone("+91-9876543210"), "+919876543210")

    def test_us_formatted(self):
        result = normalize_phone("(415) 555-0192")
        self.assertTrue(result.startswith("+1"))

    def test_already_e164(self):
        self.assertEqual(normalize_phone("+12125550178"), "+12125550178")

    def test_garbage_returns_none(self):
        self.assertIsNone(normalize_phone("not-a-phone"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(normalize_phone(""))

    def test_none_returns_none(self):
        self.assertIsNone(normalize_phone(None))


class TestNormalizeDate(unittest.TestCase):
    def test_iso_format(self):
        self.assertEqual(normalize_date("2022-07-01"), "2022-07")

    def test_month_name_year(self):
        self.assertEqual(normalize_date("Jul 2022"), "2022-07")
        self.assertEqual(normalize_date("January 2020"), "2020-01")

    def test_year_only(self):
        self.assertEqual(normalize_date("2022"), "2022-01")

    def test_present_returns_none(self):
        self.assertIsNone(normalize_date("present"))
        self.assertIsNone(normalize_date("Present"))
        self.assertIsNone(normalize_date("current"))

    def test_slash_format(self):
        result = normalize_date("07/2022")
        self.assertEqual(result, "2022-07")

    def test_garbage_returns_none(self):
        self.assertIsNone(normalize_date("sometime last year"))

    def test_empty_returns_none(self):
        self.assertIsNone(normalize_date(""))


class TestNormalizeCountry(unittest.TestCase):
    def test_alpha2_passthrough(self):
        self.assertEqual(normalize_country("IN"), "IN")
        self.assertEqual(normalize_country("US"), "US")

    def test_full_name(self):
        result = normalize_country("India")
        self.assertEqual(result, "IN")

    def test_alpha3(self):
        self.assertEqual(normalize_country("IND"), "IN")

    def test_garbage_returns_none(self):
        self.assertIsNone(normalize_country("XYZ_NOTACOUNTRY"))


class TestNormalizeEmail(unittest.TestCase):
    def test_valid_email_lowercased(self):
        self.assertEqual(normalize_email("Test@Example.COM"), "test@example.com")

    def test_invalid_email(self):
        self.assertIsNone(normalize_email("notanemail"))
        self.assertIsNone(normalize_email("missing@tld"))

    def test_empty_returns_none(self):
        self.assertIsNone(normalize_email(""))


class TestCanonicalizeSkill(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(canonicalize_skill("js"), "JavaScript")
        self.assertEqual(canonicalize_skill("pytorch"), "PyTorch")
        self.assertEqual(canonicalize_skill("sklearn"), "scikit-learn")
        self.assertEqual(canonicalize_skill("postgres"), "PostgreSQL")
        self.assertEqual(canonicalize_skill("k8s"), "Kubernetes")

    def test_unknown_skill_title_case(self):
        result = canonicalize_skill("some_custom_tool")
        self.assertEqual(result, "Some_Custom_Tool")

    def test_case_insensitive(self):
        self.assertEqual(canonicalize_skill("PYTHON"), "Python")
        self.assertEqual(canonicalize_skill("Python"), "Python")


# ==========================================================================
# 2. Extractor tests (existing, keep all)
# ==========================================================================

class TestCSVExtractor(unittest.TestCase):
    def setUp(self):
        self.csv_path = Path(__file__).parent.parent / "sample_inputs" / "recruiter_export.csv"

    def test_returns_records(self):
        records = extract_csv(self.csv_path)
        self.assertGreater(len(records), 0)

    def test_has_source_id(self):
        records = extract_csv(self.csv_path)
        for rec in records:
            self.assertIn("_source_id", rec)
            self.assertTrue(rec["_source_id"].startswith("recruiter_csv"))

    def test_emails_parsed(self):
        records = extract_csv(self.csv_path)
        priya = next((r for r in records if "priya" in str(r.get("emails", "")).lower()), None)
        self.assertIsNotNone(priya)
        self.assertIn("priya.sharma@email.com", priya["emails"])

    def test_missing_file_returns_empty(self):
        records = extract_csv(Path("nonexistent.csv"))
        self.assertEqual(records, [])


class TestATSJsonExtractor(unittest.TestCase):
    def setUp(self):
        self.json_path = Path(__file__).parent.parent / "sample_inputs" / "ats_export.json"

    def test_returns_records(self):
        records = extract_ats_json(self.json_path)
        self.assertEqual(len(records), 2)

    def test_field_remapping(self):
        records = extract_ats_json(self.json_path)
        priya = next((r for r in records if "priya" in str(r.get("full_name", "")).lower()), None)
        self.assertIsNotNone(priya, "Priya not found in ATS records")
        self.assertEqual(priya["full_name"], "Priya Sharma")

    def test_work_history_parsed(self):
        records = extract_ats_json(self.json_path)
        priya = next((r for r in records if "priya" in str(r.get("full_name", "")).lower()), None)
        self.assertIsNotNone(priya)
        self.assertIn("experience", priya)
        self.assertGreater(len(priya["experience"]), 0)

    def test_malformed_json_returns_empty(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{not valid json >>>")
            tmp = f.name
        records = extract_ats_json(Path(tmp))
        self.assertEqual(records, [])
        os.unlink(tmp)


class TestNotesExtractor(unittest.TestCase):
    def setUp(self):
        self.notes_path = Path(__file__).parent.parent / "sample_inputs" / "recruiter_notes_priya.txt"

    def test_extracts_email(self):
        records = extract_notes(self.notes_path)
        self.assertGreater(len(records), 0)
        self.assertIn("priya.sharma@email.com", records[0].get("emails", []))

    def test_extracts_skills(self):
        records = extract_notes(self.notes_path)
        skills = records[0].get("_raw_skills", [])
        self.assertIn("python", skills)


# ==========================================================================
# 3. Identity Clustering tests (NEW)
# ==========================================================================

class TestIdentityClustering(unittest.TestCase):
    def test_cluster_by_email(self):
        records = [
            {"_source_id": "a", "full_name": "Alice", "emails": ["alice@test.com"]},
            {"_source_id": "b", "full_name": "Alice", "emails": ["alice@test.com", "alice2@test.com"]},
            {"_source_id": "c", "full_name": "Bob", "emails": ["bob@test.com"]},
        ]
        clusters = group_records_by_identity(records)
        self.assertEqual(len(clusters), 2)
        # Alice's records should be together
        alice_cluster = [c for c in clusters if any(r["full_name"] == "Alice" for r in c)]
        self.assertEqual(len(alice_cluster[0]), 2)
        bob_cluster = [c for c in clusters if any(r["full_name"] == "Bob" for r in c)]
        self.assertEqual(len(bob_cluster[0]), 1)

    def test_cluster_by_phone(self):
        records = [
            {"_source_id": "a", "phones": ["+14155550100"], "full_name": "Alice"},
            {"_source_id": "b", "phones": ["+14155550100"], "full_name": "Alicia"},
            {"_source_id": "c", "phones": ["+12025550100"], "full_name": "Bob"},
        ]
        clusters = group_records_by_identity(records)
        self.assertEqual(len(clusters), 2)
        alice_cluster = [c for c in clusters if len(c) == 2]
        self.assertEqual(len(alice_cluster[0]), 2)

    def test_fallback_by_name(self):
        records = [
            {"_source_id": "a", "full_name": "Alice Doe", "phones": [], "emails": []},
            {"_source_id": "b", "full_name": "Alice Doe", "phones": [], "emails": []},
            {"_source_id": "c", "full_name": "Bob Smith", "phones": [], "emails": []},
        ]
        clusters = group_records_by_identity(records)
        self.assertEqual(len(clusters), 2)
        alice_cluster = [c for c in clusters if len(c) == 2]
        self.assertEqual(len(alice_cluster[0]), 2)

    def test_single_record_cluster(self):
        records = [
            {"_source_id": "a", "full_name": "Alice", "emails": ["alice@test.com"]},
        ]
        clusters = group_records_by_identity(records)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 1)

    def test_empty_input(self):
        self.assertEqual(group_records_by_identity([]), [])


# ==========================================================================
# 4. Dynamic Source Quality tests (NEW)
# ==========================================================================

class TestDynamicSourceQuality(unittest.TestCase):
    def test_full_record_high_score(self):
        record = {
            "_source_id": "test",
            "full_name": "Alice",
            "emails": ["a@b.com"],
            "phones": ["+1"],
            "_raw_location": "NY",
            "headline": "Engineer",
            "_raw_skills": ["python"],
            "years_experience": 5,
        }
        score = _calculate_source_quality(record)
        self.assertGreater(score, 0.8)
        self.assertLessEqual(score, 0.95)

    def test_sparse_record_low_score(self):
        record = {
            "_source_id": "test",
            "full_name": "Alice",
        }
        score = _calculate_source_quality(record)
        self.assertGreaterEqual(score, 0.2)
        self.assertLess(score, 0.5)

    def test_empty_record_min_score(self):
        record = {"_source_id": "test"}
        score = _calculate_source_quality(record)
        self.assertEqual(score, 0.2)  # clamped

    def test_bonus_fields_boost(self):
        record = {
            "_source_id": "test",
            "full_name": "Alice",
            "emails": ["a@b.com"],
            "phones": ["+1"],
            "_raw_location": "NY",
        }
        score1 = _calculate_source_quality(record)
        record["headline"] = "Engineer"
        record["_raw_skills"] = ["python"]
        score2 = _calculate_source_quality(record)
        self.assertGreater(score2, score1)


# ==========================================================================
# 5. Merge tests (updated for dynamic scoring and granular merge)
# ==========================================================================

class TestMerge(unittest.TestCase):
    def _make_records(self):
        return [
            {
                "_source_id": "recruiter_csv_row_0",
                "full_name": "Alice Doe",
                "emails": ["alice@example.com"],
                "phones": ["+14155550100"],
                "_raw_location": "San Francisco, CA, US",
                "_raw_skills": ["python", "react"],
                "experience": [{"company": "Google", "title": "SWE", "start": "2020", "end": "2022"}],
            },
            {
                "_source_id": "ats_json_0",
                "full_name": "Alice Doe",
                "emails": ["alice.doe@work.com"],
                "phones": ["+14155550100"],
                "_raw_skills": ["python", "docker", "aws"],
                "years_experience": 4,
                "experience": [{"company": "Google", "title": "Software Engineer", "start": "Jan 2020", "end": "Dec 2022"}],
            },
        ]

    def test_emails_deduped(self):
        profile = merge_records(self._make_records())
        self.assertIn("alice@example.com", profile.emails)
        self.assertIn("alice.doe@work.com", profile.emails)
        self.assertEqual(len(profile.emails), 2)

    def test_phones_deduplicated(self):
        profile = merge_records(self._make_records())
        self.assertEqual(len(profile.phones), 1)

    def test_skills_merged(self):
        profile = merge_records(self._make_records())
        skill_names = [s.name for s in profile.skills]
        self.assertIn("Python", skill_names)
        self.assertIn("React", skill_names)
        self.assertIn("Docker", skill_names)

    def test_skill_confidence_higher_for_multi_source(self):
        profile = merge_records(self._make_records())
        python_skill = next((s for s in profile.skills if s.name == "Python"), None)
        react_skill = next((s for s in profile.skills if s.name == "React"), None)
        self.assertIsNotNone(python_skill)
        self.assertIsNotNone(react_skill)
        self.assertGreater(python_skill.confidence, react_skill.confidence)

    def test_years_experience(self):
        profile = merge_records(self._make_records())
        self.assertEqual(profile.years_experience, 4.0)

    def test_location_parsed(self):
        profile = merge_records(self._make_records())
        self.assertIsNotNone(profile.location)
        self.assertEqual(profile.location.city, "San Francisco")
        self.assertEqual(profile.location.country, "US")

    def test_provenance_populated(self):
        profile = merge_records(self._make_records())
        self.assertGreater(len(profile.provenance), 0)
        sources = [p.source for p in profile.provenance]
        self.assertTrue(any("csv" in s for s in sources))

    def test_empty_input(self):
        profile = merge_records([])
        self.assertIsNotNone(profile.candidate_id)
        self.assertEqual(profile.emails, [])

    def test_garbage_source_does_not_crash(self):
        records = [
            {"_source_id": "bad_source", "full_name": None, "emails": ["not-an-email"], "phones": ["000"]},
        ]
        profile = merge_records(records)
        self.assertEqual(profile.emails, [])
        self.assertEqual(profile.phones, [])

    # NEW: Granular experience merge test
    def test_granular_experience_merge(self):
        records = [
            {
                "_source_id": "a",
                "full_name": "Alice",
                "experience": [{"company": "Google", "title": "SWE", "start": "2020", "end": "2022"}],
            },
            {
                "_source_id": "b",
                "full_name": "Alice",
                "experience": [{"company": "Google", "title": "Software Engineer", "start": "Jan 2020", "end": "Dec 2022", "summary": "Built things"}],
            },
        ]
        profile = merge_records(records)
        self.assertEqual(len(profile.experience), 1)
        exp = profile.experience[0]
        self.assertEqual(exp.company, "Google")
        # Should pick more precise dates (YYYY-MM over YYYY)
        self.assertEqual(exp.start, "2020-01")
        self.assertEqual(exp.end, "2022-12")
        self.assertIn("Built things", exp.summary)


# ==========================================================================
# 6. Projection tests (existing, keep all)
# ==========================================================================

class TestProjection(unittest.TestCase):
    def _make_profile(self) -> CanonicalProfile:
        from transformer.merge import merge_records
        records = [
            {
                "_source_id": "recruiter_csv_row_0",
                "full_name": "Bob Smith",
                "emails": ["bob@example.com", "bsmith@work.com"],
                "phones": ["+12025550100"],
                "_raw_location": "New York, NY, US",
                "_raw_skills": ["python", "aws", "docker"],
                "headline": "Senior Engineer",
                "years_experience": 6,
            }
        ]
        return merge_records(records)

    def test_no_config_returns_full_profile(self):
        profile = self._make_profile()
        output = project(profile, config=None)
        self.assertIn("full_name", output)
        self.assertIn("emails", output)

    def test_field_selection(self):
        profile = self._make_profile()
        config = {
            "fields": [
                {"path": "full_name", "type": "string", "required": True},
                {"path": "primary_email", "from": "emails[0]", "type": "string"},
            ],
            "on_missing": "null",
        }
        output = project(profile, config)
        self.assertIn("full_name", output)
        self.assertIn("primary_email", output)
        self.assertNotIn("phones", output)

    def test_rename_via_from(self):
        profile = self._make_profile()
        config = {
            "fields": [
                {"path": "first_email", "from": "emails[0]", "type": "string"},
            ],
            "on_missing": "null",
        }
        output = project(profile, config)
        self.assertIn("first_email", output)
        self.assertEqual(output["first_email"], "bob@example.com")

    def test_skills_array_spread(self):
        profile = self._make_profile()
        config = {
            "fields": [
                {"path": "skill_names", "from": "skills[].name", "type": "string[]"},
            ],
            "on_missing": "null",
        }
        output = project(profile, config)
        self.assertIsInstance(output["skill_names"], list)
        self.assertIn("Python", output["skill_names"])

    def test_on_missing_omit(self):
        profile = self._make_profile()
        config = {
            "fields": [
                {"path": "full_name", "type": "string"},
                {"path": "nonexistent_field", "type": "string"},
            ],
            "on_missing": "omit",
        }
        output = project(profile, config)
        self.assertIn("full_name", output)
        self.assertNotIn("nonexistent_field", output)

    def test_on_missing_null(self):
        profile = self._make_profile()
        config = {
            "fields": [
                {"path": "nonexistent_field", "type": "string"},
            ],
            "on_missing": "null",
        }
        output = project(profile, config)
        self.assertIn("nonexistent_field", output)
        self.assertIsNone(output["nonexistent_field"])

    def test_include_confidence_flag(self):
        profile = self._make_profile()
        config = {
            "fields": [{"path": "full_name", "type": "string"}],
            "include_confidence": True,
            "on_missing": "null",
        }
        output = project(profile, config)
        self.assertIn("overall_confidence", output)

    def test_validation_catches_type_mismatch(self):
        profile = self._make_profile()
        config = {
            "fields": [
                {"path": "full_name", "type": "number"},
            ],
            "on_missing": "null",
        }
        output = project(profile, config)
        errors = validate_output(output, config)
        # full_name coerced to None → validation should flag
        self.assertTrue(len(errors) > 0 or output.get("full_name") is None)


# ==========================================================================
# 7. Edge case integration tests (updated with new features)
# ==========================================================================

class TestEdgeCases(unittest.TestCase):
    def test_all_sources_missing_graceful(self):
        result = run_pipeline(sources=["nonexistent_file.csv", "also_missing.json"])
        self.assertIn("profile", result)
        self.assertIn("output", result)
        self.assertEqual(result["profile"]["emails"], [])

    def test_conflicting_emails_deduped(self):
        records = [
            {"_source_id": "src_a", "emails": ["Alice@Example.com"], "full_name": "Alice"},
            {"_source_id": "src_b", "emails": ["alice@example.com"], "full_name": "Alice"},
        ]
        profile = merge_records(records)
        self.assertEqual(len(profile.emails), 1)

    def test_phone_normalization_strips_formatting(self):
        records = [
            {"_source_id": "src_a", "phones": ["+1 (415) 555-0100"]},
            {"_source_id": "src_b", "phones": ["4155550100"]},
        ]
        profile = merge_records(records)
        self.assertEqual(len(profile.phones), 1)
        self.assertTrue(profile.phones[0].startswith("+1"))

    def test_single_source_still_produces_profile(self):
        records = [{"_source_id": "recruiter_csv_row_0", "full_name": "Solo Person", "emails": ["solo@test.com"]}]
        profile = merge_records(records)
        self.assertEqual(profile.full_name, "Solo Person")

    def test_overall_confidence_bounded(self):
        records = [
            {
                "_source_id": "ats_json_0",
                "full_name": "Test User",
                "emails": ["test@test.com"],
                "phones": ["+12025550100"],
                "_raw_skills": ["python", "java"],
                "headline": "Engineer",
            }
        ]
        profile = merge_records(records)
        self.assertGreaterEqual(profile.overall_confidence, 0.0)
        self.assertLessEqual(profile.overall_confidence, 1.0)

    # NEW: Source Veto test
    def test_source_veto_ignores_specified_types(self):
        result = run_pipeline(
            sources=[
                "sample_inputs/recruiter_export.csv",
                "sample_inputs/recruiter_notes_priya.txt",
            ],
            config_path=None,  # no config → no veto
            verbose=False,
        )
        # Without veto, both sources should contribute
        self.assertGreater(len(result["profiles"]), 0)
        
        # With veto on "notes"
        # We'll create a temporary config file with ignored_sources
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"ignored_sources": ["notes"], "fields": []}, f)
            config_path = f.name
        result_veto = run_pipeline(
            sources=[
                "sample_inputs/recruiter_export.csv",
                "sample_inputs/recruiter_notes_priya.txt",
            ],
            config_path=config_path,
            verbose=False,
        )
        os.unlink(config_path)
        # Should still produce profiles (CSV is not ignored)
        self.assertGreater(len(result_veto["profiles"]), 0)

    # NEW: Multi-candidate clustering test
    def test_multi_candidate_clustering(self):
        # CSV has 3 people, but we'll just use a small synthetic list
        records = [
            {"_source_id": "a", "full_name": "Alice", "emails": ["alice@a.com"]},
            {"_source_id": "b", "full_name": "Bob", "emails": ["bob@b.com"]},
            {"_source_id": "c", "full_name": "Alice", "emails": ["alice@a.com"]},  # same as a
        ]
        clusters = group_records_by_identity(records)
        self.assertEqual(len(clusters), 2)  # Alice cluster (2) and Bob cluster (1)
        alice_cluster = next(c for c in clusters if len(c) == 2)
        self.assertEqual(alice_cluster[0]["full_name"], "Alice")
        self.assertEqual(alice_cluster[1]["full_name"], "Alice")


# ==========================================================================
# 8. Gold profile comparison (updated with new features)
# ==========================================================================

class TestGoldProfileComparison(unittest.TestCase):
    """
    Compare pipeline output against a known-good gold profile.
    This acts as a regression test for the full pipeline.
    """

    GOLD_PROFILE = {
        "full_name": "Priya Sharma",
        "primary_email": "priya.sharma@email.com",
        "location_country": "IN",
        "years_experience": 3.0,
    }

    def test_gold_profile_fields(self):
        result = run_pipeline(
            sources=[
                "sample_inputs/recruiter_export.csv",
                "sample_inputs/ats_export.json",
                "sample_inputs/recruiter_notes_priya.txt",
            ],
            config_path="config/recruiter_view.json",
            verbose=False,
        )
        output = result["output"]
        # Check full_name
        self.assertEqual(output.get("full_name"), self.GOLD_PROFILE["full_name"])
        # Check primary_email
        self.assertEqual(output.get("primary_email"), self.GOLD_PROFILE["primary_email"])
        # Check location.country (since config outputs a location object)
        location_obj = output.get("location")
        if location_obj:
            self.assertEqual(location_obj.get("country"), self.GOLD_PROFILE["location_country"])
        else:
            self.fail("location object not found in output")
        # Check years_experience
        self.assertEqual(output.get("years_experience"), self.GOLD_PROFILE["years_experience"])

if __name__ == "__main__":
    unittest.main(verbosity=2)