# Property Tax Project — Pipeline Plan

## Research Question

Are homeowners in Travis County fraudulently claiming the homestead exemption on properties
they are operating as short-term rentals? We test this by measuring whether neighborhoods
with high Airbnb density show homestead exemption rates that are lower in proportion to
their STR activity — as would be expected if the tax rolls were accurate. The fraud signal
is when homestead rates are *higher* than STR density would predict: operators are still
claiming exemptions on properties they no longer occupy as a primary residence.

---

## Prerequisites

Before running the pipeline, the following files must be present in `data/sources/`:

| File | Description | How to obtain |
|---|---|---|
| `Travis_protaxExport_20250720.json` | TCAD property tax export (~29GB) | Run `python scripts/fetch_tcad.py` |
| `shortrent_locations.geojson` | City of Austin STR permit locations | Downloaded manually from Austin Open Data Portal |
| `listings.geojson` | Inside Airbnb listings with coordinates | Downloaded manually from Inside Airbnb |

`fetch_tcad.py` downloads and extracts the TCAD ZIP from traviscad.org. It skips the download
if the JSON already exists in `data/sources/`.

---

## Pipeline

Run the full pipeline end-to-end with:

```
python main.py
```

### Stage 0 — Preflight Check
**Script:** `scripts/stage0_preflight.py`
**Status:** Complete

Runs automatically at the start of `main.py` before any other stage. Checks whether a valid
SQLite database already exists so that Stage 1 (which takes several hours to run) can be
skipped if the database is already built.

Checks performed:
- Database file exists at `data/sources/travis_property_tax.db`
- File size is at least 0.5 GB (guards against truncated/incomplete builds)
- All six expected tables are present and non-empty
- `properties` table has at least 100,000 rows

If all checks pass, Stage 1 is skipped and the pipeline proceeds to Stage 2. If any check
fails, Stage 1 runs and rebuilds the database from scratch.

---

### Stage 1 — Load TCAD JSON to SQLite
**Script:** `scripts/load_protax_to_sqlite.py`
**Status:** Complete
**Skipped if:** Stage 0 preflight passes

Streams the 29GB TCAD JSON using `ijson` (never loads the full file into memory) and inserts
records in batches of 10,000 into a normalized SQLite database. Creates six tables:

- `properties` — top-level parcel fields (propType, geometry, inactive, etc.)
- `property_profile` — exemptions, improvement characteristics
- `property_characteristics` — use code, subtype, zoning
- `property_situs` — street address
- `property_legal_description` — legal acreage, lot/block
- `property_identification` — geoID, refID cross-references

Indexes are created after the bulk insert for performance.

**Output:** `data/sources/travis_property_tax.db` (~1.1GB)

After Stage 1 completes, `scripts/stage1_output_test.py` runs automatically to verify the
database file exists, all six tables are present, and each table has rows.

---

### Stage 2 — Hex Aggregation and Ratio Computation
**Script:** `scripts/aggregate_to_hex.py`
**Status:** Complete

For each H3 hexagonal cell at resolution 8, computes:

| Field | Definition |
|---|---|
| `sfr_total` | Active SFR parcels with valid geometry (propType=R, inactive=0, subType=RES) |
| `sfr_homestead` | SFR parcels with HS exemption code in property_profile |
| `str_permits_type2` | Type 2 Residential STR permits (whole-home, non-owner-occupied) |
| `airbnb_entire_home` | Active entire-home Airbnb listings (≥1 review in last 12 months) |
| `homestead_rate` | sfr_homestead / sfr_total |
| `str_permit_rate` | str_permits_type2 / sfr_total |
| `airbnb_rate` | airbnb_entire_home / sfr_total |
| `registration_gap` | airbnb_entire_home − str_permits_type2 |

Inclusion thresholds (cells must meet all three to be retained):
- `sfr_total >= 20` — stable ratio denominator
- `airbnb_entire_home >= 3` — minimum absolute Airbnb presence
- `airbnb_rate >= 0.02` — minimum 2% Airbnb density

Known limitation: ~13-14% of SFR parcels have null geometry and are excluded. Their homestead
rate is lower than the geocoded set, introducing a mild upward bias in `homestead_rate`.

**Output:** `data/products/hex_ratios.geojson` (246 hex cells)

After Stage 2 completes, `scripts/stage2_output_test.py` runs automatically to verify the
GeoJSON exists, has features, contains all expected columns, and that `homestead_rate` values
are bounded between 0 and 1.

---

### Stage 3 — Visualization and Correlation Analysis
**Script:** `scripts/visualize.py`
**Status:** Complete

Outputs:

1. **`map_homestead_airbnb.png`** — side-by-side choropleth maps of `homestead_rate` (Blues) and `airbnb_rate` (Oranges) across Travis County hex cells.

2. **`map_registration_gap.png`** — choropleth of `registration_gap` (Airbnb listings minus STR permits) per hex cell.

3. **`scatter_homestead_vs_airbnb.png`** — `homestead_rate` vs. `airbnb_rate`, one point per hex cell, OLS regression line, point size proportional to `registration_gap`. A negative slope is the expected result under no fraud; a positive slope is the anomaly signal.

4. **`correlation_summary.csv`** — Pearson and Spearman correlations for three variable pairs:
   - `homestead_rate` vs. `airbnb_rate`
   - `homestead_rate` vs. `registration_gap`
   - `airbnb_rate` vs. `registration_gap`

5. **`candidate_neighborhoods.csv`** — top 25 hex cells by `registration_gap` (Airbnb listings minus STR permits), as the primary "where to look" output for parcel-level follow-up.

**Input:** `data/products/hex_ratios.geojson`
**Output:** figures and CSVs saved to `data/products/`; committed figures in `images/`

---

## Project Structure

```
property_tax_project/
├── main.py                        # Runs full pipeline in sequence
├── scripts/
│   ├── __init__.py
│   ├── fetch_tcad.py              # Manual prerequisite — run before main.py
│   ├── stage0_preflight.py        # Stage 0: DB check, gates Stage 1
│   ├── load_protax_to_sqlite.py   # Stage 1
│   ├── stage1_output_test.py      # Stage 1 output verification (auto-runs)
│   ├── aggregate_to_hex.py        # Stage 2
│   ├── stage2_output_test.py      # Stage 2 output verification (auto-runs)
│   └── visualize.py               # Stage 3
├── images/                        # Committed output figures for README
├── data/
│   ├── sources/                   # Raw inputs and SQLite db (gitignored)
│   └── products/                  # Pipeline outputs (gitignored)
├── queries/                       # Ad hoc SQL queries
├── docs/                          # Project documentation
├── environment.yml                # Conda environment spec
└── boot_dev_env.bat               # Environment bootstrap script
```

---

## Key Assumptions and Sensitivity Checks

- **H3 resolution**: Run at both resolution 8 (neighborhood) and resolution 9 (block cluster) to confirm pattern stability
- **STR type filter**: Compare results using only Type 2 vs. all STR types to verify the signal is driven by whole-home rentals
- **Airbnb activity threshold**: Test different minimum review counts as a proxy for "active" listing status
- **Minimum cell size**: Test sensitivity to the minimum SFR parcel threshold for ratio computation
