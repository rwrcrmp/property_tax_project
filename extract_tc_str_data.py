# This script downloads and prepares three spatial datasets:
#   1. Travis County boundary polygon (reference layer)
#   2. City of Austin STR permit locations (geocoded to points)
#   3. Inside Airbnb listings (already has lat/lon)
# All outputs are saved as GeoJSON to data/raw/

# --- Libraries ---
import pandas as pd
import geopandas as gpd
from io import StringIO
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import json
import requests

# Shared coordinate reference system — WGS84 lat/lon
# Used consistently across all datasets for compatibility
base_crs = "EPSG:4326"


# --- Helper: clean_names() ---
# Equivalent to janitor::clean_names() in R
# Standardizes all column names to lowercase snake_case
# e.g. "PROP_ADDRESS" -> "prop_address", "STR Type" -> "str_type"
def clean_names(df):
    df.columns = (
        df.columns
        .str.lower()
        .str.replace(r'[^a-z0-9]', '_', regex=True)  # replace special chars
        .str.replace(r'_+', '_', regex=True)           # collapse multiple underscores
        .str.strip('_')                                 # remove leading/trailing underscores
    )
    return df


# =============================================================================
# 1. Travis County Boundary
# =============================================================================
# Source: US Census Bureau TIGERweb REST API (no authentication required)
# State FIPS 48 = Texas, County FIPS 453 = Travis County
# The %3D and %27 are URL-encoded = and ' characters respectively
travis_county_url = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "TIGERweb/State_County/MapServer/13/query"
    "?where=STATE%3D%2748%27+AND+COUNTY%3D%27453%27"
    "&outFields=*&f=geojson"
)

travis_county_response = requests.get(travis_county_url)

# from_features() reads a GeoJSON FeatureCollection into a GeoDataFrame
# equivalent to sf::st_read() on a GeoJSON string in R
travis_county_gdf = gpd.GeoDataFrame.from_features(
    json.loads(travis_county_response.text)["features"],
    crs=base_crs
)
travis_county_gdf = clean_names(travis_county_gdf)

travis_county_gdf.to_file(
    "data/raw/travis_county.geojson",
    driver="GeoJSON"
)
print("Saved Travis County boundary to data/raw")


# =============================================================================
# 2. City of Austin STR Permit Locations
# =============================================================================
# Source: City of Austin Open Data Portal (Socrata API)
# Addresses are obfuscated to block level — requires geocoding to get lat/lon
shortrent_url = (
    "https://data.austintexas.gov/api/views/2fah-4p7e/"
    "rows.csv?accessType=DOWNLOAD"
)
shortrent_response = requests.get(shortrent_url)

# StringIO wraps the response text so pandas can read it like a file object
# equivalent to read.csv(text = ...) in R
shortrent_locations = pd.read_csv(StringIO(shortrent_response.text))
shortrent_locations = clean_names(shortrent_locations)

# Permit addresses follow the pattern "BLOCK OF 2400 DORMARION LN"
# Stripping "BLOCK OF " leaves a valid block-face address for geocoding
# str.replace() with regex=True uses a regular expression pattern
# ^ means "start of string", so this only strips the prefix
shortrent_locations["clean_address"] = (
    shortrent_locations["prop_address"]
    .str.replace(r"^BLOCK OF ", "", regex=True)
)

# --- 2a. Primary geocoding: Census Geocoder batch API ---
# Free, no API key required, handles up to 10,000 addresses per request
# Input format required: Unique ID, Street, City, State, ZIP
geocode_input = shortrent_locations[[
    "case_number",
    "clean_address",
    "prop_city",
    "prop_state",
    "prop_zip"
]].copy()

geocode_url = (
    "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
)

# to_csv() with index=False and header=False produces a plain CSV string
# with no row numbers or column headers — exactly what the API expects
geocode_response = requests.post(
    geocode_url,
    files={
        "addressFile": (
            "addresses.csv",
            geocode_input.to_csv(index=False, header=False),
            "text/csv"
        )
    },
    data={"benchmark": "Public_AR_Current"}
)

# The Census API returns a CSV (no header) — we assign column names manually
geocode_results = pd.read_csv(
    StringIO(geocode_response.text),
    header=None,
    names=[
        "id",
        "input_address",
        "match",
        "match_type",
        "matched_address",
        "coordinates",
        "tiger_line_id",
        "tiger_line_side"
    ],
    dtype={"id": str}
)

# Filter to successful matches only
# Coordinates are returned as a "longitude,latitude" string — split and cast
matched = geocode_results[geocode_results["match"] == "Match"].copy()
matched[["longitude", "latitude"]] = (
    matched["coordinates"]
    .str.split(",", expand=True)
    .astype(float)
)

n_matched = len(matched)
print(
    f"Census geocoder: {n_matched} of {len(shortrent_locations)} matched "
    f"({n_matched/len(shortrent_locations):.1%} match rate)"
)

# --- 2b. Secondary geocoding: Nominatim (OpenStreetMap) ---
# Catches addresses the Census geocoder missed
# Rate limited to 1 request/second per Nominatim usage policy
unmatched_ids = geocode_results[geocode_results["match"] != "Match"]["id"]

unmatched = shortrent_locations[
    shortrent_locations["case_number"].astype(str).isin(unmatched_ids)
].copy()

print(f"{len(unmatched)} records passed to Nominatim for re-geocoding")

geolocator = Nominatim(user_agent="property_tax_project")

# RateLimiter wraps the geocode function and enforces a delay between calls
# Without this, Nominatim will block requests for exceeding rate limits
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)


def geocode_address(row):
    # Build a full address query string from the row fields
    query = (
        f"{row['clean_address']}, "
        f"{row['prop_city']}, "
        f"{row['prop_state']} "
        f"{row['prop_zip']}"
    )
    result = geocode(query)
    if result:
        return pd.Series({
            "longitude": result.longitude,
            "latitude": result.latitude
        })
    return pd.Series({"longitude": None, "latitude": None})


# apply() calls geocode_address once per row — axis=1 means row-wise
# equivalent to purrr::pmap() or a rowwise mutate in R
unmatched[["longitude", "latitude"]] = unmatched.apply(
    geocode_address,
    axis=1
)

n_recovered = unmatched["latitude"].notna().sum()
print(
    f"Nominatim recovered {n_recovered} of {len(unmatched)} "
    f"unmatched records"
)

# --- 2c. Combine results and save ---
nominatim_matched = unmatched[unmatched["latitude"].notna()].copy()
truly_unmatched = unmatched[unmatched["latitude"].isna()].copy()

# Cast to string before merge to align types with the geocoder id column
shortrent_locations["case_number"] = (
    shortrent_locations["case_number"].astype(str)
)

# Merge Census-matched records back to full permit data, then stack with
# Nominatim results — equivalent to dplyr::bind_rows() in R
all_matched = pd.concat([
    shortrent_locations.merge(
        matched[["id", "longitude", "latitude"]],
        left_on="case_number",
        right_on="id"
    ),
    nominatim_matched
], ignore_index=True)

# points_from_xy() creates point geometry from coordinate columns
# equivalent to sf::st_as_sf(coords = c("longitude", "latitude")) in R
shortrent_gdf = gpd.GeoDataFrame(
    all_matched,
    geometry=gpd.points_from_xy(
        all_matched["longitude"],
        all_matched["latitude"]
    ),
    crs=base_crs
)

shortrent_gdf.to_file(
    "data/raw/shortrent_locations.geojson",
    driver="GeoJSON"
)
print(f"Saved {len(shortrent_gdf)} geocoded STR permits to data/raw")

# Save unresolvable records separately for later review
truly_unmatched.to_csv("data/raw/str_unmatched.csv", index=False)
print(f"Saved {len(truly_unmatched)} unmatched records to data/raw")


# =============================================================================
# 3. Inside Airbnb Listings
# =============================================================================
# Source: Inside Airbnb (https://insideairbnb.com/get-the-data/)
# Scrape date: 2025-09-16 — update the date in the URL to use a newer scrape
# pandas reads .gz compressed files automatically — no manual decompression
airbnb_url = (
    "https://data.insideairbnb.com/united-states/tx/austin/"
    "2025-09-16/data/listings.csv.gz"
)
listings = pd.read_csv(airbnb_url)
listings = clean_names(listings)

# Drop columns with list/array data types unsupported by the GeoJSON format
# OGR (the underlying geospatial library) cannot write these to file
# Add more column names here as needed to slim down the dataset
listings = listings.drop(columns=[
    "host_verifications",
    "amenities"
])

# Convert to GeoDataFrame using lat/lon columns
# equivalent to sf::st_as_sf(coords = c("longitude", "latitude")) in R
listings_gdf = gpd.GeoDataFrame(
    listings,
    geometry=gpd.points_from_xy(
        listings["longitude"],
        listings["latitude"]
    ),
    crs=base_crs
)

listings_gdf.to_file("data/raw/listings.geojson", driver="GeoJSON")
print(f"Saved {len(listings_gdf)} Airbnb listings to data/raw")
