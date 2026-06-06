"""
Property Tax Pipeline - Entry Point

Runs all pipeline stages in sequence to reproduce outputs from raw data.

Usage:
    python main.py
"""

from scripts.stage0_preflight import db_ready
from scripts.load_protax_to_sqlite import run as load
from scripts.stage1_output_test import run as test_stage1
from scripts.aggregate_to_hex import run as aggregate
from scripts.stage2_output_test import run as test_stage2
from scripts.visualize import run as visualize


if __name__ == "__main__":
    if not db_ready():
        print("\n--- Stage 1: Load TCAD JSON to SQLite ---")
        load()
        test_stage1()

    print("\n--- Stage 2: Hex Aggregation and Ratio Computation ---")
    aggregate()
    test_stage2()

    print("\n--- Stage 3: Visualization and Correlation Analysis ---")
    visualize()

    print("\nPipeline complete.")
