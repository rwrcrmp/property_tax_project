import pandas as pd
import geopandas as gpd
import h3
from shapely.geometry import Polygon

# Shared coordinate reference system — WGS84 lat/lon
# Used consistently across all datasets for compatibility
base_crs = "EPSG:4326"


def load_raw_data():
    travis_county = gpd.read_file("data/raw/travis_county.geojson")
    str_permits = gpd.read_file("data/raw/shortrent_locations.geojson")
    airbnb = gpd.read_file("data/raw/listings.geojson")
    return travis_county, str_permits, airbnb


travis_county, str_permits, airbnb = load_raw_data()

# Dissolve Travis County to a single polygon before filling with hexagons
# union_all() merges all features — equivalent to sf::st_union() in R
travis_polygon = travis_county.geometry.union_all()

# geo_to_cells() fills the polygon with all H3 cell IDs at the given resolution
# returns a set of hex ID strings
cells = list(h3.geo_to_cells(travis_polygon.__geo_interface__, res=8))
print(f"Generated {len(cells)} H3 cells at resolution 8")


# Convert each cell ID to a Shapely polygon
# h3.cell_to_boundary() returns vertices as (lat, lon) — note the order
# Shapely expects (lon, lat), so we swap when building the polygon
def cell_to_polygon(cell_id):
    boundary = h3.cell_to_boundary(cell_id)
    return Polygon([(lon, lat) for lat, lon in boundary])


# Build one row per hexagon with its ID and geometry
hex_gdf = gpd.GeoDataFrame(
    {"hex_id": cells},
    geometry=[cell_to_polygon(c) for c in cells],
    crs=base_crs
)

print(hex_gdf.head())

# =============================================================================
# Airbnb listings — assign to hex cells and count
# =============================================================================

# Assign each listing to an H3 cell based on its coordinates
# latlng_to_cell() takes lat, lon, resolution and returns the hex ID
airbnb["hex_id"] = airbnb.apply(
    lambda row: h3.latlng_to_cell(row["latitude"], row["longitude"], 8),
    axis=1
)

# Filter to entire home listings with at least 1 review in last 12 months
# Excludes private rooms and likely-dormant listings
airbnb_active = airbnb[
    (airbnb["room_type"] == "Entire home/apt") &
    (airbnb["number_of_reviews_ltm"] >= 1)
].copy()

# Count listings per hex cell — equivalent to dplyr::count() in R
airbnb_counts = (
    airbnb_active
    .groupby("hex_id")
    .size()
    .reset_index(name="airbnb_entire_home")
)

print(f"Airbnb listings across {len(airbnb_counts)} hex cells")

# =============================================================================
# STR permits — assign to hex cells and count
# =============================================================================

# Assign each permit to an H3 cell based on geocoded coordinates
str_permits["hex_id"] = str_permits.apply(
    lambda row: h3.latlng_to_cell(row["latitude"], row["longitude"], 8),
    axis=1
)

# Filter to Type 2 Residential — whole-home, non-owner-occupied
# This is the primary fraud signal per the study design
str_permits_type2 = str_permits[
    str_permits["str_type"] == "Short Term Rental Type 2 Residential"
].copy()

# Count permits per hex cell
str_counts = (
    str_permits_type2
    .groupby("hex_id")
    .size()
    .reset_index(name="str_permits_type2")
)

print(f"Type 2 STR permits across {len(str_counts)} hex cells")

# =============================================================================
# Join counts onto hex grid
# =============================================================================

# Left join keeps all hex cells, filling unmatched cells with 0
# equivalent to dplyr::left_join() followed by tidyr::replace_na() in R
hex_gdf = hex_gdf.merge(airbnb_counts, on="hex_id", how="left")
hex_gdf = hex_gdf.merge(str_counts, on="hex_id", how="left")

hex_gdf[["airbnb_entire_home", "str_permits_type2"]] = (
    hex_gdf[["airbnb_entire_home", "str_permits_type2"]].fillna(0)
)

print(hex_gdf[["hex_id", "airbnb_entire_home", "str_permits_type2"]].head(10))
