# Study Area Parameters

## Geographic Boundary

**Outer boundary**: Travis County (cosmetic reference only — no analytical clipping applied)

Rationale: The TCAD property tax export is the binding dataset for this analysis, and it covers Travis County — not the City of Austin. Austin's city limits extend into Williamson and Hays counties in places, making it a poor fit as a clipping boundary when TCAD data is the primary source. Rather than clip to any administrative boundary, the study area is defined organically by the data: H3 cells are populated wherever TCAD parcel and Airbnb listing data exist, and the threshold filters (minimum SFR parcel count, minimum STR rate) naturally concentrate the analysis on the urban core. The Travis County boundary polygon is retained as a cosmetic reference layer for map visualization.

The zip code approach was also considered and rejected — zip codes straddle jurisdictional boundaries awkwardly and aggregate at a scale too coarse for neighborhood-level ratio computation.

Source: US Census Bureau TIGERweb REST API — State FIPS 48 (Texas), County FIPS 453 (Travis)

---

## H3 Resolution

**Resolution 8** (~0.7 km² per hexagon)

Rationale: Approximates neighborhood scale with enough parcels per cell to produce statistically stable ratios. Resolution 9 (~0.1 km²) is available as a sensitivity check but risks underpopulated cells in lower-density areas.

---

## Cell Inclusion Thresholds

The following filters are applied *after* H3 aggregation to exclude cells that would produce unreliable ratios:

### Population / Density Proxy

**Minimum SFR parcels per cell: ≥ 20**

Rationale: A cell with very few single-family residential parcels produces ratio estimates with high variance — e.g., 1 homestead exemption out of 3 parcels yields a 33% rate that means nothing statistically. Using SFR parcel count from TCAD as a density proxy avoids the need to pull a separate Census population dataset. Any cell below 20 SFR parcels is excluded from ratio computation and visualization.

### STR Concentration

**Inclusion threshold: ≥ 3 entire-home Airbnb listings AND `airbnb_rate` ≥ 0.02**

Where `airbnb_rate` = active entire-home listings / SFR parcels in cell.

Rationale: Both conditions must be met to include a cell as "STR-active" in the primary analysis. The absolute count floor (≥ 3) prevents a single listing in a large-parcel cell from producing a trivially small but non-zero rate. The rate floor (≥ 2%) sets a minimum density threshold — at that level, roughly 1 in 50 single-family homes in the neighborhood is operating as an Airbnb, which represents a meaningfully elevated concentration relative to background levels in non-tourist residential areas.

The 2% threshold is calibrated to Austin's market context. National STR penetration in hot markets runs 2–8% of housing stock; Austin's central neighborhoods sit toward the high end of that range. At 2%, the threshold is permissive enough to capture all genuinely active STR neighborhoods while excluding cells where STR presence is incidental.

---

## Sensitivity Checks (planned)

Per the methodology document, the following sensitivity analyses are planned:

- H3 resolution: compare resolution 8 vs. resolution 9
- STR type filter: Type 2 only vs. all permit types
- Airbnb activity threshold: vary minimum review count for "active" listing definition
- Minimum cell size: test ≥ 10 and ≥ 30 SFR parcel floors in addition to the ≥ 20 baseline
