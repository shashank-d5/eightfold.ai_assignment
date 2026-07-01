#!/bin/bash
# run_demo.sh — One-command demo for the reviewer

echo "========================================"
echo "Eightfold Candidate Transformer - Demo"
echo "========================================"

# Check if dependencies are installed
echo "Checking dependencies..."
python -c "import phonenumbers, pycountry, pypdf, docx, pydantic, requests" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ Missing dependencies. Run: pip install phonenumbers pycountry pypdf python-docx pydantic requests"
    exit 1
fi

echo ""

# 1. Run default full profile
echo "[1/3] Running default output (all fields + provenance)..."
python cli.py \
  --sources sample_inputs/recruiter_export.csv \
             sample_inputs/ats_export.json \
             sample_inputs/sample_resume_priya.pdf \
             sample_inputs/recruiter_notes_priya.txt \
  --output sample_outputs/demo_default.json \
  --verbose

if [ $? -ne 0 ]; then
    echo "❌ Default run failed. Check errors above."
    exit 1
fi

echo ""

# 2. Run custom config (Recruiter view)
echo "[2/3] Running custom recruiter view (with source veto)..."
python cli.py \
  --sources sample_inputs/recruiter_export.csv \
             sample_inputs/ats_export.json \
             sample_inputs/sample_resume_priya.pdf \
             sample_inputs/recruiter_notes_priya.txt \
  --config config/recruiter_view.json \
  --output sample_outputs/demo_recruiter_view.json \
  --verbose

if [ $? -ne 0 ]; then
    echo "❌ Custom config run failed. Check errors above."
    exit 1
fi

echo ""

# 3. Print summary
echo "[3/3] ✅ Demo complete! Outputs written to sample_outputs/"
echo ""
echo "   📄 demo_default.json          (full canonical profile with provenance)"
echo "   📄 demo_recruiter_view.json   (custom projection: name, email, phone, location, headline, skills)"
echo ""
echo "To inspect the output, run:"
echo "   cat sample_outputs/demo_default.json | python -m json.tool | head -50"
echo "   cat sample_outputs/demo_recruiter_view.json | python -m json.tool | head -30"