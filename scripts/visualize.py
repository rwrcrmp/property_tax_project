"""
Stage 3: Visualization and Correlation Analysis

Inputs:  data/products/hex_ratios.geojson
Outputs: data/products/map_homestead_airbnb.png
         data/products/map_registration_gap.png
         data/products/scatter_homestead_vs_airbnb.png
         data/products/correlation_summary.csv
         data/products/candidate_neighborhoods.csv
"""

from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from scipy import stats

# ===================================================
# Configuration
# ===================================================

PROJECT_ROOT = Path(__file__).parent.parent
INPUT_PATH = PROJECT_ROOT / "data" / "products" / "hex_ratios.geojson"
OUTPUT_DIR = PROJECT_ROOT / "data" / "products"


def main():

    # ====================================================
    # Load Data
    # ====================================================

    hex_gdf = gpd.read_file(INPUT_PATH)

    print(f"Loaded {len(hex_gdf)} hex cells")
    print(hex_gdf[["homestead_rate", "airbnb_rate", "registration_gap"]].describe().round(3))

    # ==================================================
    # Fetch Travis County Boundary
    # ==================================================

    TIGERWEB_URL = (
        "https://tigerweb.geo.census.gov/arcgis/rest/services/"
        "TIGERweb/State_County/MapServer/13/query"
        "?where=STATE%3D%2748%27+AND+COUNTY%3D%27453%27"
        "&outFields=*&outSR=4326&f=geojson"
        )

    response = requests.get(TIGERWEB_URL, timeout=30)
    response.raise_for_status()
    features = response.json().get("features", [])
    county_gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")

    print(f"County boundary rows: {len(county_gdf)}")
    print(county_gdf.geometry.geom_type.values)

    # =======================================================
    # Figure 1: Side-by-Side Choropleth Maps
    # =======================================================

    fig, (ax1, ax2) = plt.subplots(1,2, figsize=(16, 8))

    # --- Left map: homestead_rate ---
    county_gdf.plot(ax=ax1, color = "whitesmoke", edgecolor="black", linewidth=0.8)
    hex_gdf.plot(
        ax=ax1,
        column="homestead_rate",
        cmap="Blues",
        legend=True,
        legend_kwds={"shrink": 0.6, "label": "Homestead Rate"}
    )
    ax1.set_title("Homestead Exemption Rate\nby H3 Hex Cell (Res 8)", fontsize=13)
    ax1.set_axis_off()

    # --- Right map: airbnb_rate ---
    county_gdf.plot(ax=ax2, color="whitesmoke", edgecolor="black", linewidth=0.8)
    hex_gdf.plot(
        ax=ax2,
        column="airbnb_rate",
        cmap="Oranges",
        legend=True,
        legend_kwds={"shrink": 0.6, "label": "Airbnb Rate"},
    )
    ax2.set_title("Airbnb Entire-Home Rate\nby H3 Hex Cell (Res 8)", fontsize=13)
    ax2.set_axis_off()

    fig.suptitle("Travis County — STR Activity vs. Homestead Exemption", fontsize=15)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "map_homestead_airbnb.png", dpi=150, bbox_inches="tight")
    plt.close()

    # =======================================================
    # Figure 2: Registration Gap Choropleth
    # =======================================================

    fig, ax = plt.subplots(1, 1, figsize=(10, 8))

    county_gdf.plot(ax=ax, color="whitesmoke", edgecolor="black", linewidth=0.8)
    hex_gdf.plot(
        ax=ax,
        column="registration_gap",
        cmap="YlOrRd",
        legend=True,
        legend_kwds={"shrink": 0.6, "label": "Unregistered STR Listings (est.)"},
    )
    ax.set_title(
        "Registration Gap by H3 Hex Cell\n(Airbnb Entire-Home Listings minus STR Permits)",
        fontsize=13
    )
    ax.set_axis_off()

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "map_registration_gap.png", dpi=150, bbox_inches="tight")
    plt.close()

    # =======================================================
    # Figure 3: Scatter Plot — Homestead Rate vs Airbnb Rate
    # =======================================================

    # Fit OLS regression line using scipy
    # stats.linregress returns slope, intercept, r-value, p-value, std error
    slope, intercept, r_value, p_value, _ = stats.linregress(
        hex_gdf["homestead_rate"], hex_gdf["airbnb_rate"]
    )

    # Build x values for the regression line across the observed range
    x_line = np.linspace(hex_gdf["homestead_rate"].min(), hex_gdf["homestead_rate"].max(), 200)
    y_line = slope * x_line + intercept

    # Scale point size by registration_gap — clip at 0 so the one -1 row doesn't shrink
    # Adding 10 ensures even zero-gap hexes are visible
    sizes = np.clip(hex_gdf["registration_gap"], 0, None) * 1.5 + 10

    fig, ax = plt.subplots(figsize=(9, 7))

    ax.scatter(
        hex_gdf["homestead_rate"],
        hex_gdf["airbnb_rate"],
        s=sizes,
        alpha=0.5,
        color="steelblue",
        edgecolors="white",
        linewidths=0.4,
    )

    ax.plot(x_line, y_line, color="tomato", linewidth=1.5, label=f"OLS fit  (r = {r_value:.3f}, p = {p_value:.3f})")

    ax.set_xlabel("Homestead Exemption Rate", fontsize=12)
    ax.set_ylabel("Airbnb Entire-Home Rate", fontsize=12)
    ax.set_title(
        "Homestead Rate vs. Airbnb Density\n(point size = registration gap)",
        fontsize=13,
    )
    ax.legend(fontsize=10)

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "scatter_homestead_vs_airbnb.png", dpi=150, bbox_inches="tight")
    plt.close()

    # =======================================================
    # Correlation Summary CSV
    # =======================================================

    pairs = [
        ("homestead_rate", "airbnb_rate"),
        ("homestead_rate", "registration_gap"),
        ("airbnb_rate","registration_gap")
    ]

    rows = []
    for var1, var2 in pairs:
        pearson_r, pearson_p = stats.pearsonr(hex_gdf[var1], hex_gdf[var2])
        spearman_r, spearman_p = stats.spearmanr(hex_gdf[var1], hex_gdf[var2])
        rows.append({
            "variable_1":  var1,
            "variable_2":  var2,
            "pearson_r":   round(pearson_r,  4),
            "pearson_p":   round(pearson_p,  4),
            "spearman_r":  round(spearman_r, 4),
            "spearman_p":  round(spearman_p, 4),
        })

    corr_df = pd.DataFrame(rows)
    corr_df.to_csv(OUTPUT_DIR / "correlation_summary.csv", index=False)
    print("Correlation summary:")
    print(corr_df.to_string(index=False))

    # =======================================================
    # Candidate Neighborhoods CSV
    # =======================================================

    candidate_cols = [
        "hex_id", "sfr_total", "sfr_homestead", "homestead_rate",
        "airbnb_entire_home", "airbnb_rate",
        "str_permits_type2", "registration_gap",
    ]

    candidates_df = (
        hex_gdf[candidate_cols]
        .sort_values("registration_gap", ascending=False)
        .head(25)
        .reset_index(drop=True)
    )

    candidates_df.to_csv(OUTPUT_DIR / "candidate_neighborhoods.csv", index=False)
    print(f"\nTop 25 candidate neighborhoods saved.")
    print(candidates_df.head(10).to_string(index=False))

    print("=" * 60)
    print("Done.")


run = main


if __name__ == "__main__":
    main()
