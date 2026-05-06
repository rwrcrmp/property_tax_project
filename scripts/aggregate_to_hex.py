"""
Stage 2: Ratio Computation Pipeline

For each H3 hexagonal cell at resolution 8, compute:
  - sfr_total:          SFR parcels with valid geometry
  - sfr_homestead:      SFR parcels claiming homestead (HS) exemption
  - str_permits_type2:  Type 2 residential STR permits (whole-home, non-owner-occupied)
  - airbnb_entire_home: Active entire-home Airbnb listings
  - homestead_rate:     sfr_homestead / sfr_total
  - str_permit_rate:    str_permits_type2 / sfr_total
  - airbnb_rate:        airbnb_entire_home / sfr_total
  - registration_gap:   airbnb_entire_home - str_permits_type2

Output: data/processed/hex_ratios.geojson
"""

import json
import sqlite3
from pathlib import Path

import geopandas as gpd
import h3
import pandas as pd
from shapely.geometry import Polygon


# =============================================================================
# Configuration
# =============================================================================

PROJECT_ROOT    = Path(__file__).parent.parent
DB_PATH         = PROJECT_ROOT / "data" / "sources" / "travis_property_tax.db"
STR_PATH        = PROJECT_ROOT / "data" / "sources" / "shortrent_locations.geojson"
AIRBNB_PATH     = PROJECT_ROOT / "data" / "sources" / "listings.geojson"
OUTPUT_PATH     = PROJECT_ROOT / "data" / "products" / "hex_ratios.geojson"

H3_RESOLUTION   = 8
MIN_SFR_TOTAL   = 20    # minimum SFR parcels per cell for stable ratios
MIN_AIRBNB_ABS  = 3     # minimum absolute Airbnb listings per cell
MIN_AIRBNB_RATE = 0.02  # minimum airbnb_entire_home / sfr_total


# =============================================================================
# Helper
# =============================================================================

def cell_to_polygon(cell_id: str) -> Polygon:
    # h3.cell_to_boundary() returns (lat, lon) pairs; Shapely expects (lon, lat)
    boundary = h3.cell_to_boundary(cell_id)
    return Polygon([(lon, lat) for lat, lon in boundary])


# =============================================================================
# Stage 2 Functions
# =============================================================================

def load_str_airbnb(str_path: Path, airbnb_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load STR permits and Airbnb listings, assign to H3 cells, return per-cell counts.

    STR filter:    Type 2 Residential only (whole-home, non-owner-occupied)
    Airbnb filter: Entire home/apt with at least 1 review in last 12 months
    """
    str_gdf    = gpd.read_file(str_path)
    airbnb_gdf = gpd.read_file(airbnb_path)

    str_gdf["hex_id"] = str_gdf.apply(
        lambda r: h3.latlng_to_cell(r.geometry.y, r.geometry.x, H3_RESOLUTION), axis=1
    )
    airbnb_gdf["hex_id"] = airbnb_gdf.apply(
        lambda r: h3.latlng_to_cell(r["latitude"], r["longitude"], H3_RESOLUTION), axis=1
    )

    str_type2 = str_gdf[str_gdf["str_type"] == "Short Term Rental Type 2 Residential"].copy()
    airbnb_active = airbnb_gdf[
        (airbnb_gdf["room_type"] == "Entire home/apt") &
        (airbnb_gdf["number_of_reviews_ltm"] >= 1)
    ].copy()

    str_counts = (
        str_type2.groupby("hex_id").size().reset_index(name="str_permits_type2")
    )
    airbnb_counts = (
        airbnb_active.groupby("hex_id").size().reset_index(name="airbnb_entire_home")
    )

    print(f"  STR Type 2 permits:         {len(str_type2):,} across {len(str_counts):,} hex cells")
    print(f"  Active entire-home Airbnb:  {len(airbnb_active):,} across {len(airbnb_counts):,} hex cells")

    return str_counts, airbnb_counts


def load_tcad_parcels(db_path: Path) -> pd.DataFrame:
    """
    Query SQLite for SFR parcels, parse geometry, assign to H3 cells.

    SFR definition: propType='R', inactive=0, subType='RES'
    Geometry field: JSON string [lat, lon] — NOT GeoJSON or WKT.

    NOTE: ~13-14% of SFR parcels have geometry='[null, null]' and are excluded.
    Their homestead rate is lower than the geocoded set, introducing a mild
    upward bias in homestead_rate estimates — noted as a known limitation.
    """
    conn = sqlite3.connect(db_path)

    sfr_universe = pd.read_sql_query("""
        SELECT COUNT(*) AS n FROM properties p
        JOIN property_characteristics pc ON p.pID = pc.pID
        WHERE p.propType = 'R' AND p.inactive = 0 AND pc.subType = 'RES'
    """, conn).iloc[0, 0]
    print(f"  SFR parcel universe (propType=R, active, subType=RES): {sfr_universe:,}")

    df = pd.read_sql_query("""
        SELECT
            p.pID,
            p.geometry,
            CASE WHEN pp.exemptions LIKE '%HS%' THEN 1 ELSE 0 END AS has_homestead
        FROM properties p
        JOIN property_profile pp         ON p.pID = pp.pID
        JOIN property_characteristics pc ON p.pID = pc.pID
        WHERE p.propType  = 'R'
          AND p.inactive  = 0
          AND pc.subType  = 'RES'
          AND p.geometry != '[null, null]'
    """, conn)
    conn.close()

    null_dropped = sfr_universe - len(df)
    print(f"  Parcels dropped (null geometry): {null_dropped:,} ({null_dropped/sfr_universe:.1%})")

    coords = df["geometry"].apply(json.loads)
    df["lat"] = coords.apply(lambda c: c[0])
    df["lon"] = coords.apply(lambda c: c[1])
    df = df.dropna(subset=["lat", "lon"])

    df["hex_id"] = df.apply(
        lambda r: h3.latlng_to_cell(r["lat"], r["lon"], H3_RESOLUTION), axis=1
    )

    print(f"  Parcels assigned to H3 cells: {len(df):,}")
    return df[["pID", "hex_id", "has_homestead"]]


def aggregate_tcad_to_hex(sfr_df: pd.DataFrame) -> pd.DataFrame:
    """Count SFR parcels and homestead-exempt parcels per hex cell."""
    tcad_hex = sfr_df.groupby("hex_id").agg(
        sfr_total=("pID", "count"),
        sfr_homestead=("has_homestead", "sum")
    ).reset_index()

    print(f"  TCAD populated hex cells: {len(tcad_hex):,}")
    return tcad_hex


def merge_all_counts(
    tcad_hex: pd.DataFrame,
    str_counts: pd.DataFrame,
    airbnb_counts: pd.DataFrame
) -> pd.DataFrame:
    """
    Join STR and Airbnb counts onto the TCAD hex table.

    TCAD defines the universe — cells with zero STR/Airbnb activity are retained
    so homestead_rate can be computed across all residential neighborhoods,
    not just STR-active ones.
    """
    hex_df = tcad_hex.merge(str_counts,    on="hex_id", how="left")
    hex_df = hex_df.merge(airbnb_counts,   on="hex_id", how="left")

    hex_df[["str_permits_type2", "airbnb_entire_home"]] = (
        hex_df[["str_permits_type2", "airbnb_entire_home"]].fillna(0).astype(int)
    )

    return hex_df


def compute_ratios_and_filter(hex_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-cell ratios and apply inclusion thresholds from study_area_parameters.md:
      - sfr_total >= MIN_SFR_TOTAL (stable ratio denominator)
      - airbnb_entire_home >= MIN_AIRBNB_ABS AND airbnb_rate >= MIN_AIRBNB_RATE
    """
    hex_df["homestead_rate"]   = (hex_df["sfr_homestead"]      / hex_df["sfr_total"]).round(4)
    hex_df["str_permit_rate"]  = (hex_df["str_permits_type2"]   / hex_df["sfr_total"]).round(4)
    hex_df["airbnb_rate"]      = (hex_df["airbnb_entire_home"]  / hex_df["sfr_total"]).round(4)
    hex_df["registration_gap"] =  hex_df["airbnb_entire_home"]  - hex_df["str_permits_type2"]

    print(f"  Hex cells before threshold filtering: {len(hex_df):,}")

    mask = (
        (hex_df["sfr_total"]          >= MIN_SFR_TOTAL)  &
        (hex_df["airbnb_entire_home"] >= MIN_AIRBNB_ABS) &
        (hex_df["airbnb_rate"]        >= MIN_AIRBNB_RATE)
    )
    hex_filtered = hex_df[mask].copy()

    print(f"  Hex cells after threshold filtering:  {len(hex_filtered):,}")
    print(f"  (thresholds: sfr_total>={MIN_SFR_TOTAL}, "
          f"airbnb>={MIN_AIRBNB_ABS}, airbnb_rate>={MIN_AIRBNB_RATE})")

    return hex_filtered

def build_and_save_geodataframe(hex_filtered: pd.DataFrame, output_path: Path) -> gpd.GeoDataFrame:
    """Convert filtered hex cells to GeoDataFrame and write to GeoJSON."""
    column_order = [
        "hex_id", "sfr_total", "sfr_homestead", "str_permits_type2", "airbnb_entire_home",
        "homestead_rate", "str_permit_rate", "airbnb_rate", "registration_gap"
    ]

    hex_gdf = gpd.GeoDataFrame(
        hex_filtered[column_order],
        geometry=[cell_to_polygon(c) for c in hex_filtered["hex_id"]],
        crs="EPSG:4326"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    hex_gdf.to_file(output_path, driver="GeoJSON")
    print(f"  Saved {len(hex_gdf):,} hex cells → {output_path}")

    return hex_gdf

# =============================================================================
# Main
# =============================================================================

def main():
    print("=" * 60)
    print("Stage 2: Ratio Computation")
    print("=" * 60)

    print("\n[1/5] Loading STR permits and Airbnb listings...")
    str_counts, airbnb_counts = load_str_airbnb(STR_PATH, AIRBNB_PATH)

    print("\n[2/5] Loading TCAD parcels from SQLite...")
    sfr_df = load_tcad_parcels(DB_PATH)

    print("\n[3/5] Aggregating TCAD parcels to hex cells...")
    tcad_hex = aggregate_tcad_to_hex(sfr_df)

    print("\n[4/5] Merging counts and computing ratios...")
    hex_df       = merge_all_counts(tcad_hex, str_counts, airbnb_counts)
    hex_filtered = compute_ratios_and_filter(hex_df)

    print("\n[5/5] Building GeoDataFrame and saving output...")
    hex_gdf = build_and_save_geodataframe(hex_filtered, OUTPUT_PATH)

    print("\n" + "=" * 60)
    print("Summary statistics for filtered cells:")
    print(hex_gdf[["homestead_rate", "str_permit_rate", "airbnb_rate", "registration_gap"]].describe().round(4))
    print("=" * 60)
    print("Done.")


run = main


if __name__ == "__main__":
    main()