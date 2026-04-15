## Hospital Proximity & Market Analysis Tool

## Overview

The **Hospital Proximity & Market Analysis Tool** enriches ZIP-level account data with geographic, demographic, and infrastructure insights. It computes proximity to hospitals, classifies rural versus urban segments, and integrates income data to support market analysis.

The final outputs include:

* An enriched Excel dataset for analysis
* An interactive HTML map for stakeholder exploration

---

## Repository Structure

```
.
├── config.py              # Central configuration and business logic
├── download_data.py      # Reference data ingestion pipeline
├── process.py            # Core enrichment engine
├── generate_map.py       # Interactive map generator
├── requirements.txt      # Python dependencies
├── data/
│   ├── raw/              # Raw downloaded datasets
│   └── processed/        # Cleaned reference datasets
├── output/
│   ├── accounts_enriched.xlsx
│   └── hospital_proximity_map.html
```

---

## Installation

Ensure Python 3.9+ is installed, then run:

```bash
pip install -r requirements.txt
```

### Dependencies

* pandas
* numpy
* scipy
* openpyxl
* requests
* tqdm

---

## Setup & Configuration

### 1. Census API Key (Required for Income Data)

Get a free API key from the US Census Bureau and add it in `config.py`:

```python
CENSUS_API_KEY = "your_api_key_here"
```

If omitted, income fields will remain empty.

---

### 2. Hospital Dataset (Manual Step)

Download hospital data from the HIFLD Open Data portal and place it in:

```
data/raw/
```

Accepted formats:

* CSV
* GeoJSON

---

### 3. Input File

Set your input file in `config.py`:

```python
INPUT_FILE = "zips_only.xlsx"
```

#### Required Format

The Excel file must include a ZIP code column such as:

* Zip
* Zipcode
* Postal

---

## Execution Workflow

### Step 1: Download Reference Data

```bash
python download_data.py
```

This generates:

```
data/processed/
├── zip_centroids.csv
├── ruca_codes.csv
├── hospitals.csv
└── income_by_zip.csv
```

---

### Step 2: Run Enrichment

```bash
python process.py
```

#### What Happens

* ZIP codes are cleaned and standardized
* Distance to nearest hospital is computed
* RUCA classifications are assigned
* Income data is merged

#### Output

```
output/accounts_enriched.xlsx
```

---

### Step 3: Generate Map

```bash
python generate_map.py
```

#### Output

```
output/hospital_proximity_map.html
```

---

## Core Logic

### Distance Calculation

* Uses `scipy.spatial.cKDTree` for fast nearest-neighbor search
* Operates on spherical coordinates
* Converts distances using Earth radius: ~3958.8 miles

---

### Proximity Binning

Defined in `config.py`:

```python
PROXIMITY_BINS = [
    (0, 5),
    (5, 15),
    (15, 30),
    (30, 60),
    (60, float("inf"))
]
```

---

### RUCA Classification

Maps USDA RUCA codes (1–10) into categories:

* Metropolitan
* Micropolitan
* Small Town
* Rural

Configured via:

```python
RUCA_CATEGORY_MAP = {...}
```

---

## Module Details

### config.py

* Central control for:

  * File paths
  * API keys
  * Distance bins
  * RUCA mappings

---

### download_data.py

* Fetches:

  * ZIP centroids
  * RUCA codes
  * Census income data
* Standardizes and saves datasets

---

### process.py

* Core pipeline:

  * ZIP normalization (handles ZIP+4, leading zeros)
  * Spatial nearest-hospital lookup
  * Data merging and enrichment
* Includes test mode:

```bash
python process.py --sample 100
```

* Outputs null analysis summary

---

### generate_map.py

* Builds a standalone Leaflet map
* Uses Canvas rendering for performance
* Supports large datasets (up to ~25,000 points)

#### Features

* Distance-based color scaling
* Income gradient visualization
* RUCA category filters
* Interactive tooltips

---

## Output Artifacts

### Enriched Dataset

```
output/accounts_enriched.xlsx
```

Includes:

* Distance to nearest hospital
* Proximity category
* RUCA classification
* Median household income

---

### Interactive Map

```
output/hospital_proximity_map.html
```

Fully self-contained, no server required.

---

## Limitations & Caveats

### 1. Manual Hospital Data

Hospital dataset must be manually downloaded if not present.

---

### 2. Census API Dependency

Without a valid API key:

* Income data will be missing

---

### 3. Distance Accuracy

* Based on ZIP centroids, not exact addresses
* Real-world travel distance may differ slightly

---

### 4. Input Requirements

* Must include a valid ZIP column
* Incorrect formatting may cause failures

---

## Future Improvements

* Automate hospital dataset download
* Add driving-time based distances
* Integrate additional demographic features
* Add CLI interface for full pipeline execution

---
