# Property Tax Project — Pipeline Plan

## Research Question

Are homeowners in Travis County fraudulently claiming the homestead exemption on properties
they are operating as short-term rentals? We test this by measuring whether neighborhoods
with high Airbnb density also show suppressed homestead exemption rates relative to their
single-family residential base.

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

### Stage 1 — Load TCAD JSON to SQLite
**Script:** `scripts/load_protax_to_sqlite.py`
**Status:** Complete

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

---

### Stage 3 — Visualization and Correlation Analysis
**Script:** `scripts/visualize.py`
**Status:** Not yet built

Planned outputs:

1. **Choropleth maps** — side-by-side maps of `homestead_rate` and `airbnb_rate` across
   Travis County hex cells, overlaid on a county boundary reference layer.

2. **Scatter plot** — `homestead_rate` (y-axis) vs. `airbnb_rate` (x-axis), one point per
   hex cell, with a regression line and `registration_gap` encoded as point size or color.

3. **Correlation summary** — Pearson/Spearman correlation between `homestead_rate` and
   `airbnb_rate`, with a brief interpretation.

**Input:** `data/products/hex_ratios.geojson`
**Output:** figures saved to `data/products/` (formats TBD)

---

## Project Structure

```
property_tax_project/
├── main.py                        # Runs full pipeline in sequence
├── scripts/
│   ├── __init__.py
│   ├── fetch_tcad.py              # Manual prerequisite — run before main.py
│   ├── load_protax_to_sqlite.py   # Stage 1
│   ├── stage1_ouput_test.py       # Stage 1 output verification
│   ├── aggregate_to_hex.py        # Stage 2
│   ├── stage2_ouput_test.py       # Stage 2 output verification
│   └── visualize.py               # Stage 3 (not yet built)
├── data/
│   ├── sources/                   # Raw inputs and SQLite db
│   └── products/                  # Pipeline outputs
├── queries/                       # Ad hoc SQL queries
├── docs/                          # Project documentation
├── environment.yml                # Conda environment spec
└── boot_dev_env.bat               # Environment bootstrap script
```
