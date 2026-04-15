"""
process.py
----------
Enriches a ZIP-level Excel file (columns: Zip, Count of Zip) with:
  - hospital_distance_miles     nearest hospital distance (ZIP centroid → hospital)
  - hospital_proximity_category binned label (e.g. "< 5 miles")
  - ruca_code                   USDA RUCA primary code
  - ruca_category               "Metropolitan" / "Micropolitan" / "Small Town" / "Rural"
  - median_hh_income            ACS B19013 median household income (ZCTA level)

Usage:
    python process.py                    # uses INPUT_FILE from config.py
    python process.py path/to/file.xlsx  # override input path
    python process.py --sample 100       # process only first 100 rows (for testing)
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from config import (
    DATA_PROCESSED_DIR,
    INPUT_FILE,
    OUTPUT_DIR,
    PROXIMITY_BINS,
)

EARTH_RADIUS_MILES = 3958.8


def load_reference_data():
    """Load all processed reference CSVs into DataFrames keyed by zip."""
    centroids_path = DATA_PROCESSED_DIR / "zip_centroids.csv"
    ruca_path      = DATA_PROCESSED_DIR / "ruca_codes.csv"
    hospitals_path = DATA_PROCESSED_DIR / "hospitals.csv"
    income_path    = DATA_PROCESSED_DIR / "income_by_zip.csv"

    missing = [p for p in [centroids_path, ruca_path, hospitals_path] if not p.exists()]
    if missing:
        print("ERROR: Missing reference files. Run download_data.py first:")
        for p in missing:
            print(f"  {p}")
        sys.exit(1)

    centroids = pd.read_csv(centroids_path, dtype={"zip": str})
    centroids["zip"] = centroids["zip"].str.zfill(5)
    centroids = centroids.set_index("zip")

    ruca = pd.read_csv(ruca_path, dtype={"zip": str})
    ruca["zip"] = ruca["zip"].str.zfill(5)
    ruca = ruca.set_index("zip")

    hospitals = pd.read_csv(hospitals_path)
    hospitals = hospitals.dropna(subset=["lat", "lon"])

    income = None
    if income_path.exists():
        income = pd.read_csv(income_path, dtype={"zip": str})
        income["zip"] = income["zip"].str.zfill(5)
        income = income.set_index("zip")
    else:
        warnings.warn(
            "income_by_zip.csv not found — median_hh_income column will be empty. "
            "Set CENSUS_API_KEY in config.py and re-run download_data.py."
        )

    return centroids, ruca, hospitals, income


def build_hospital_tree(hospitals: pd.DataFrame):
    """Return a cKDTree built from hospital coordinates (in radians)."""
    lats_rad = np.radians(hospitals["lat"].values)
    lons_rad = np.radians(hospitals["lon"].values)
    coords = np.column_stack([lats_rad, lons_rad])
    return cKDTree(coords), hospitals


def arc_to_miles(arc_distance: np.ndarray) -> np.ndarray:
    """Convert cKDTree Euclidean distance (on unit sphere) to miles."""
    # cKDTree returns chord length; convert via: angle = 2*arcsin(d/2)
    angle = 2 * np.arcsin(np.clip(arc_distance / 2, -1, 1))
    return angle * EARTH_RADIUS_MILES


def bin_distance(miles: float) -> str:
    for threshold, label in PROXIMITY_BINS:
        if miles <= threshold:
            return label
    return PROXIMITY_BINS[-1][1]


def enrich_zip_lookup(
    unique_zips: pd.Index,
    centroids: pd.DataFrame,
    ruca: pd.DataFrame,
    hospitals: pd.DataFrame,
    income,
    tree: cKDTree,
) -> pd.DataFrame:
    """
    For each unique ZIP, compute all enrichment columns.
    Returns a DataFrame indexed by zip.
    """
    rows = []
    missing_centroid = []

    zip_lat = centroids["lat"].reindex(unique_zips)
    zip_lon = centroids["lon"].reindex(unique_zips)

    has_centroid = zip_lat.notna() & zip_lon.notna()
    missing_centroid = list(unique_zips[~has_centroid])
    if missing_centroid:
        warnings.warn(
            f"{len(missing_centroid):,} ZIP codes not found in centroid data "
            f"(hospital distance will be null). Examples: {missing_centroid[:5]}"
        )

    # Batch hospital query for ZIPs that have centroids
    valid_zips = unique_zips[has_centroid]
    lats_rad = np.radians(zip_lat[valid_zips].values)
    lons_rad = np.radians(zip_lon[valid_zips].values)
    coords = np.column_stack([lats_rad, lons_rad])

    distances_arc, _ = tree.query(coords, k=1)
    distances_miles = arc_to_miles(distances_arc)

    lookup = pd.DataFrame(index=unique_zips)
    lookup["hospital_distance_miles"] = np.nan
    lookup["hospital_proximity_category"] = None

    lookup.loc[valid_zips, "hospital_distance_miles"] = np.round(distances_miles, 2)
    lookup.loc[valid_zips, "hospital_proximity_category"] = [
        bin_distance(d) for d in distances_miles
    ]

    # RUCA
    lookup["ruca_code"]     = ruca["ruca_code"].reindex(unique_zips)
    lookup["ruca_category"] = ruca["ruca_category"].reindex(unique_zips)

    # Income
    if income is not None:
        lookup["median_hh_income"] = income["median_hh_income"].reindex(unique_zips)
    else:
        lookup["median_hh_income"] = np.nan

    return lookup


def main():
    # ── Parse args ────────────────────────────────────────────────────────────
    input_path = INPUT_FILE
    sample_n = None

    args = sys.argv[1:]
    if "--sample" in args:
        idx = args.index("--sample")
        sample_n = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]
    if args:
        input_path = Path(args[0])

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        print("  Set INPUT_FILE in config.py or pass the path as an argument.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load input ─────────────────────────────────────────────────────────────
    print(f"Loading input: {input_path}")
    df = pd.read_excel(input_path, dtype=str)
    if sample_n:
        df = df.head(sample_n)
        print(f"  Running on sample of {sample_n} rows")
    print(f"  {len(df):,} rows, columns: {list(df.columns)}")

    # Normalize ZIP column — accepts "Zip", "ZIP", "zip", "zipcode", etc.
    zip_col = next(
        (c for c in df.columns if c.strip().lower() in ("zip", "zipcode", "zip_code", "postal")),
        None,
    )
    if not zip_col:
        print(f"ERROR: Could not find a ZIP column. Columns: {list(df.columns)}")
        sys.exit(1)

    df[zip_col] = df[zip_col].astype(str).str.strip().str.split("-").str[0].str.zfill(5)

    # Drop summary/total rows (e.g. "Grand Total") — not valid ZIP codes
    df = df[df[zip_col].str.match(r"^\d{5}$")]

    # ── Load reference data ────────────────────────────────────────────────────
    print("Loading reference data...")
    centroids, ruca, hospitals, income = load_reference_data()
    tree, hospitals = build_hospital_tree(hospitals)
    print(f"  {len(hospitals):,} hospitals | {len(centroids):,} ZIP centroids | {len(ruca):,} RUCA records")

    # ── Enrich directly — one row per ZIP, no join needed ─────────────────────
    unique_zips = pd.Index(df[zip_col].unique())
    print(f"Computing enrichment for {len(unique_zips):,} ZIPs...")
    lookup = enrich_zip_lookup(unique_zips, centroids, ruca, hospitals, income, tree)

    df = df.join(lookup, on=zip_col)

    # ── Export ─────────────────────────────────────────────────────────────────
    suffix = f"_sample{sample_n}" if sample_n else ""
    out_path = OUTPUT_DIR / f"accounts_enriched{suffix}.xlsx"
    print(f"Writing output → {out_path}")
    df.to_excel(out_path, index=False, engine="openpyxl")

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n── Enrichment summary ───────────────────────────────────")
    for col in ["hospital_distance_miles", "hospital_proximity_category", "ruca_code", "ruca_category", "median_hh_income"]:
        null_pct = df[col].isna().mean() * 100
        print(f"  {col:<35} {null_pct:.1f}% null")

    print(f"\nDone. Output: {out_path}")


if __name__ == "__main__":
    main()
