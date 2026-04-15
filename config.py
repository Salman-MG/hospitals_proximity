from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_RAW_DIR = BASE_DIR / "data" / "raw"
DATA_PROCESSED_DIR = BASE_DIR / "data" / "processed"
OUTPUT_DIR = BASE_DIR / "output"

# Set this to the path of your input Excel file
# The file should have at minimum columns: "Zip" and "Count of Zip"
INPUT_FILE = BASE_DIR / "zips_only.xlsx"  # ← update to your actual filename

# ── Census API ─────────────────────────────────────────────────────────────────
# Free key from: https://api.census.gov/data/signup.html
# Leave as None to skip income download (you can add it manually later)
CENSUS_API_KEY = "b908e96b6c75e2640101164b6e43217415243d6c"

# ── Hospital proximity bins ────────────────────────────────────────────────────
# List of (max_miles, label). The last entry should use float("inf").
PROXIMITY_BINS = [
    (5,           "< 5 miles"),
    (15,          "5-15 miles"),
    (30,          "15-30 miles"),
    (float("inf"), "> 30 miles"),
]

# ── RUCA category labels ───────────────────────────────────────────────────────
# Keys are RUCA primary codes (1–10); values are human-readable categories.
RUCA_CATEGORY_MAP = {
    1: "Metropolitan",
    2: "Metropolitan",
    3: "Metropolitan",
    4: "Micropolitan",
    5: "Micropolitan",
    6: "Micropolitan",
    7: "Small Town",
    8: "Small Town",
    9: "Small Town",
    10: "Rural",
}
