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
| Inside Airbnb listings | [Inside Airbnb](http://insideairbnb.com) | `data/raw/listings.csv.gz` |
| Austin STR permits | City of Austin Open Data Portal | `data/raw/shortrent_locations.csv` |
| Travis County boundary | U.S. Census TIGERweb REST API | `data/raw/travis_county.geojson` |
| Austin city limits | City of Austin Open Data Portal | `data/raw/austin_city_limits.geojson` |
| TCAD property tax export | Travis County Appraisal District | `data/raw/Travis_protaxExport_*.json` |

---

## Geospatial Pipeline

### Step 1: Exploratory Data Checks (`explore_geodata.ipynb`)

Before building the aggregation pipeline, this notebook verifies that downloaded boundary and listing data are valid:

- Loads and inspects the Austin city limits polygon (CRS, bounding box, jurisdiction type breakdown)
- Converts the Airbnb CSV to a GeoDataFrame using lat/lon columns and plots listings over the city boundary
- Loads and inspects the STR permit dataset

All layers use **EPSG:4326** (WGS84 lat/lon) as the common coordinate reference system.

### Step 2: H3 Hexagonal Aggregation (`aggregate_to_hex.py`)

To enable spatial comparison across datasets, the county is divided into a hexagonal grid using [Uber's H3 library](https://h3geo.org/) at **resolution 8** (hexagons roughly 0.7 km² each). Each data source is then aggregated to hex cells.

**Processing steps:**

1. **Build the hex grid** — dissolve Travis County to a single polygon, then fill it with H3 cell IDs (`h3.geo_to_cells()`). Each cell ID is converted to a Shapely polygon and stored in a GeoDataFrame.

2. **Airbnb listings** — each listing is assigned to its containing hex cell (`h3.latlng_to_cell()`). Two filters are applied before counting:
   - `room_type == "Entire home/apt"` — excludes private/shared rooms, which pose lower fraud risk
   - `number_of_reviews_ltm >= 1` — excludes likely-dormant listings with no recent activity

3. **STR permits** — each permit is similarly assigned to a hex cell and filtered to **Type 2 Residential** (whole-home, non-owner-occupied), which is the permit classification most relevant to homestead fraud.

4. **Join** — Airbnb counts and STR permit counts are left-joined onto the hex grid, with unmatched cells filled with zero.

The result is a single GeoDataFrame where each row is a hexagon containing:
- `hex_id` — H3 cell identifier
- `airbnb_entire_home` — count of active entire-home Airbnb listings
- `str_permits_type2` — count of Type 2 STR permits

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
