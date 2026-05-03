"""
Output verification tests for Stage 2 (Hex Aggregation and Ratio Computation).

Usage:
    python scripts/stage2_ouput_test.py
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
HEX_PATH     = PROJECT_ROOT / "data" / "products" / "hex_ratios.geojson"

EXPECTED_COLUMNS = [
    "hex_id", "sfr_total", "sfr_homestead", "str_permits_type2",
    "airbnb_entire_home", "homestead_rate", "str_permit_rate",
    "airbnb_rate", "registration_gap",
]


def run():
    passed = 0
    failed = 0

    def check(description, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"  PASS  {description}")
            passed += 1
        else:
            print(f"  FAIL  {description}" + (f" — {detail}" if detail else ""))
            failed += 1

    print("\n=== Stage 2: Hex Ratios GeoJSON ===")

    check("hex_ratios.geojson exists", HEX_PATH.exists(), f"expected at {HEX_PATH}")

    if HEX_PATH.exists():
        with open(HEX_PATH) as f:
            geojson = json.load(f)

        features = geojson.get("features", [])
        check("GeoJSON has features", len(features) > 0, f"found {len(features)} features")

        if features:
            props = features[0]["properties"]
            for col in EXPECTED_COLUMNS:
                check(f"Column '{col}' present", col in props or col == "hex_id")

            check(
                "homestead_rate is between 0 and 1",
                all(0 <= f["properties"]["homestead_rate"] <= 1 for f in features)
            )

            print(f"\n  Total hex cells: {len(features)}")
            rates = [f["properties"]["homestead_rate"] for f in features]
            print(f"  homestead_rate range: {min(rates):.3f} – {max(rates):.3f}")

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("All checks passed — Stage 2 outputs look good.")
    else:
        print("Some checks failed — review output above.")
    print()


if __name__ == "__main__":
    run()
