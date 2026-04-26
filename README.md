# Property Tax Project

## Overview

This project investigates potential homestead exemption fraud in Travis County, Texas by combining three geospatial datasets:

- **Inside Airbnb listings** — short-term rental activity scraped from Airbnb
- **City of Austin STR permits** — registered short-term rental permits, classified by type
- **TCAD property tax records** — Travis County Appraisal District export with homestead exemption status

The core hypothesis is that properties operating as whole-home short-term rentals (STRs) are unlikely to qualify for a homestead exemption, which requires the property to be the owner's primary residence. By spatially joining these datasets, we can identify areas where high STR activity coincides with claimed homestead exemptions.

---

## Data Sources

| Dataset | Source | File |
|---|---|---|
| Inside Airbnb listings | [Inside Airbnb](http://insideairbnb.com) | `data/raw/listings.geojson` |
| Austin STR permits | City of Austin Open Data Portal | `data/raw/shortrent_locations.geojson` |
| Travis County boundary | U.S. Census TIGERweb REST API | `data/raw/travis_county.geojson` |
| TCAD property tax export | Travis County Appraisal District | `data/raw/Travis_protaxExport_*.json` |

---

## Pipeline

### Step 1: TCAD Data Ingestion (`load_protax_to_sqlite.py`)

The TCAD property tax export is a ~29GB JSON file. This script streams it record-by-record using `ijson` (never loading the full file into memory) and loads it into a normalized SQLite database at `data/processed/travis_property_tax.db`.

**Output tables:**

| Table | Contents |
|---|---|
| `properties` | Core parcel fields — pID, propType, geometry, inactive status |
| `property_profile` | Exemption codes, improvement details, taxing unit |
| `property_situs` | Addresses (street, city, zip) |
| `property_characteristics` | Use code, subtype, zoning |
| `property_identification` | geoID and cross-reference IDs |
| `property_legal_description` | Legal acreage and description |

SQL queries for exploring exemption data are in `queries/homestead_exemptions.sql`.

### Step 2: Ratio Computation (`aggregate_to_hex.py`)

The core analytical pipeline. Queries the SQLite database, combines all three data sources, and produces a per-neighborhood ratio dataset saved to `data/processed/hex_ratios.geojson`.

The county is divided into a hexagonal grid using [Uber's H3 library](https://h3geo.org/) at **resolution 8** (~0.7 km² per cell). For each cell the following are computed:

| Field | Description |
|---|---|
| `sfr_total` | SFR parcels with valid geometry |
| `sfr_homestead` | SFR parcels claiming homestead (HS) exemption |
| `str_permits_type2` | Type 2 Residential STR permits (whole-home, non-owner-occupied) |
| `airbnb_entire_home` | Active entire-home Airbnb listings |
| `homestead_rate` | sfr_homestead / sfr_total |
| `str_permit_rate` | str_permits_type2 / sfr_total |
| `airbnb_rate` | airbnb_entire_home / sfr_total |
| `registration_gap` | airbnb_entire_home − str_permits_type2 |

**Cell inclusion thresholds** (per `docs/study_area_parameters.md`):
- `sfr_total >= 20` — minimum parcel count for a stable ratio
- `airbnb_entire_home >= 3` AND `airbnb_rate >= 0.02` — minimum STR activity

**SFR definition:** `propType = 'R'`, `inactive = 0`, `subType = 'RES'`. Approximately 13–14% of SFR parcels have null geometry and are excluded; this introduces a mild upward bias in `homestead_rate` estimates.

> **Note on the license field:** The Inside Airbnb `license` column is 100% empty for this market, so permit cross-referencing by permit number is not possible. Spatial proximity is the only available link between Airbnb listings and the STR permit registry.

---

## Environment Setup

This project uses [Miniconda](https://docs.conda.io/en/latest/miniconda.html) to manage Python dependencies. Follow the steps below to get up and running.

### Prerequisites

- Windows 10 or 11
- Git

### Step 1: Install Miniconda

1. Download the Miniconda installer for Windows from https://docs.conda.io/en/latest/miniconda.html
2. Run the installer and follow the prompts
   - Install for "Just Me" (recommended)
   - **Important:** Install to the default location in your user directory: `C:\Users\<your-username>\miniconda3`. The setup script (`boot_dev_env.bat`) expects to find Miniconda at this path. Do not change the default install directory.
   - You do NOT need to add conda to PATH or register it as the default Python

### Step 2: Clone the Repository

```bash
git clone <repository-url>
cd property_tax_project
```

### Step 3: Run the Setup Script

Double-click `boot_dev_env.bat` or run it from a Command Prompt. The script will:

1. Locate your Miniconda installation in your user directory
2. Check if a conda environment named `property_tax_project` already exists
3. If not, create it from `environment.yml` (installs Python 3.12 and all dependencies)
4. Activate the environment
5. Open a command prompt in the project directory, ready to work

On subsequent runs, the script skips environment creation and just activates it.

### Step 4: Verify the Setup

In the command prompt opened by the script, run:

```bash
python -c "import geopandas; import pandas; print('Environment is working!')"
```

### Adding New Packages

If you need to add a new package:

1. Install it with conda first: `conda install <package-name>`
2. If conda doesn't have it, use pip: `pip install <package-name>`
3. Update `environment.yml` to include the new package so others can reproduce the environment

### Rebuilding the Environment

If the environment gets corrupted or you need a fresh start:

```bash
conda env remove --name property_tax_project
```

Then run `boot_dev_env.bat` again to recreate it from `environment.yml`.
