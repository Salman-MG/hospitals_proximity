"""
download_data.py
----------------
Downloads and prepares the three reference datasets needed by process.py:

  1. ZIP code centroids     → data/processed/zip_centroids.csv
  2. RUCA codes by ZIP      → data/processed/ruca_codes.csv
  3. Hospital locations     → data/processed/hospitals.csv
     (requires manual download — see instructions below)
  4. Median HH income/ZCTA → data/processed/income_by_zip.csv
     (requires a free Census API key in config.py)

Run once before process.py:
    python download_data.py
"""

import io
import sys
import zipfile

import numpy as np
import pandas as pd
import requests

from config import (
    CENSUS_API_KEY,
    DATA_PROCESSED_DIR,
    DATA_RAW_DIR,
    RUCA_CATEGORY_MAP,
)

DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


# ── 1. ZIP code centroids ──────────────────────────────────────────────────────

def download_zip_centroids():
    out = DATA_PROCESSED_DIR / "zip_centroids.csv"
    if out.exists():
        print(f"[skip] {out.name} already exists")
        return

    url = (
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
        "2023_Gazetteer/2023_Gaz_zcta_national.zip"
    )
    print("Downloading ZIP code centroids from Census Bureau...")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".txt"))
        with zf.open(name) as f:
            df = pd.read_csv(f, sep="\t", dtype=str)

    # Strip whitespace from column names (Census file has trailing spaces)
    df.columns = [c.strip() for c in df.columns]
    df = df[["GEOID", "INTPTLAT", "INTPTLONG"]]
    df = df.rename(columns={"GEOID": "zip", "INTPTLAT": "lat", "INTPTLONG": "lon"})
    df["zip"] = df["zip"].str.zfill(5)
    df["lat"] = pd.to_numeric(df["lat"])
    df["lon"] = pd.to_numeric(df["lon"])
    df.to_csv(out, index=False)
    print(f"  Saved {len(df):,} ZIPs → {out}")


# ── 2. RUCA codes ──────────────────────────────────────────────────────────────

def download_ruca_codes():
    out = DATA_PROCESSED_DIR / "ruca_codes.csv"
    if out.exists():
        print(f"[skip] {out.name} already exists")
        return

    url = "https://www.ers.usda.gov/media/5444/2020-rural-urban-commuting-area-codes-zip-codes.csv?v=54354"
    print("Downloading 2020 RUCA codes from USDA ERS...")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()

    import io as _io
    df = pd.read_csv(_io.StringIO(resp.text), dtype=str)
    df = df[["ZIPCode", "PrimaryRUCA"]].copy()
    df.columns = ["zip", "ruca_code"]
    df["zip"] = df["zip"].str.strip().str.zfill(5)

    df["ruca_code"] = pd.to_numeric(df["ruca_code"], errors="coerce")
    df = df.dropna(subset=["ruca_code"])
    df["ruca_code"] = df["ruca_code"].astype(int)

    df["ruca_category"] = df["ruca_code"].map(RUCA_CATEGORY_MAP).fillna("Unknown")
    df.to_csv(out, index=False)
    print(f"  Saved {len(df):,} ZIP RUCA codes → {out}")


# ── 3. Hospital locations (manual download) ────────────────────────────────────

def prepare_hospitals():
    out = DATA_PROCESSED_DIR / "hospitals.csv"
    if out.exists():
        print(f"[skip] {out.name} already exists")
        return

    # Look for any CSV the user may have dropped in data/raw/
    candidates = list(DATA_RAW_DIR.glob("*hospital*")) + list(DATA_RAW_DIR.glob("*Hospital*"))
    if not candidates:
        print(
            "\n[ACTION REQUIRED] Hospital data not found.\n"
            "  1. Go to: https://portal.datarescueproject.org/datasets/hifld-open-hospitals/\n"
            "  2. Download the CSV (or GeoJSON) file.\n"
            f"  3. Place the file in: {DATA_RAW_DIR}\n"
            "  4. Re-run this script.\n"
        )
        return

    src = candidates[0]
    print(f"Reading hospital data from {src.name}...")

    if src.suffix.lower() == ".csv":
        df = pd.read_csv(src, dtype=str, low_memory=False)
    elif src.suffix.lower() in (".geojson", ".json"):
        import json
        with open(src) as f:
            gj = json.load(f)
        rows = []
        for feat in gj.get("features", []):
            props = feat.get("properties", {})
            coords = feat.get("geometry", {}).get("coordinates", [None, None])
            props["lon"] = coords[0]
            props["lat"] = coords[1]
            rows.append(props)
        df = pd.DataFrame(rows)
    else:
        print(f"  Unsupported file type: {src.suffix}. Expected .csv or .geojson")
        return

    # Normalize column names to uppercase for consistent lookup
    df.columns = [c.upper().strip() for c in df.columns]

    # Filter to open hospitals only (field may be STATUS or STATE)
    if "STATUS" in df.columns:
        df = df[df["STATUS"].str.upper().str.strip() == "OPEN"]

    # Identify lat/lon columns
    lat_col = next((c for c in df.columns if c in ("LATITUDE", "LAT", "Y")), None)
    lon_col = next((c for c in df.columns if c in ("LONGITUDE", "LON", "LONG", "X")), None)
    name_col = next((c for c in df.columns if "NAME" in c), df.columns[0])

    if not lat_col or not lon_col:
        print(f"  Could not find lat/lon columns. Available: {list(df.columns)}")
        return

    df = df[[name_col, lat_col, lon_col]].copy()
    df.columns = ["name", "lat", "lon"]
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

    df.to_csv(out, index=False)
    print(f"  Saved {len(df):,} hospitals → {out}")


# ── 4. Median household income by ZCTA ────────────────────────────────────────

def download_income():
    out = DATA_PROCESSED_DIR / "income_by_zip.csv"
    if out.exists():
        print(f"[skip] {out.name} already exists")
        return

    if not CENSUS_API_KEY:
        print(
            "\n[ACTION REQUIRED] Census API key not set.\n"
            "  1. Get a free key at: https://api.census.gov/data/signup.html\n"
            "  2. Set CENSUS_API_KEY in config.py\n"
            "  3. Re-run this script.\n"
            "  (Income data will be skipped until then.)\n"
        )
        return

    print("Downloading ACS median household income by ZCTA from Census API...")
    url = (
        "https://api.census.gov/data/2023/acs/acs5"
        f"?get=B19013_001E,NAME&for=zip+code+tabulation+area:*&key={CENSUS_API_KEY}"
    )
    resp = requests.get(url, timeout=180)
    resp.raise_for_status()

    data = resp.json()
    headers = data[0]
    rows = data[1:]
    df = pd.DataFrame(rows, columns=headers)

    df = df.rename(columns={
        "B19013_001E": "median_hh_income",
        "zip code tabulation area": "zip",
    })
    df["zip"] = df["zip"].str.zfill(5)
    df["median_hh_income"] = pd.to_numeric(df["median_hh_income"], errors="coerce")
    # Census returns -666666666 for suppressed/missing values
    df.loc[df["median_hh_income"] < 0, "median_hh_income"] = np.nan
    df = df[["zip", "median_hh_income"]]

    df.to_csv(out, index=False)
    print(f"  Saved {len(df):,} ZCTA income records → {out}")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    download_zip_centroids()
    download_ruca_codes()
    prepare_hospitals()
    download_income()
    print("\nDone. Check data/processed/ for output files.")
