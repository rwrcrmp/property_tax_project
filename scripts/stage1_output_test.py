"""
Output verification tests for Stage 1 (Load TCAD JSON to SQLite).

Usage:
    python scripts/stage1_output_test.py
"""

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH      = PROJECT_ROOT / "data" / "sources" / "travis_property_tax.db"

EXPECTED_TABLES = [
    "properties",
    "property_profile",
    "property_characteristics",
    "property_situs",
    "property_legal_description",
    "property_identification",
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

    print("\n=== Stage 1: SQLite Database ===")

    check("Database file exists", DB_PATH.exists(), f"expected at {DB_PATH}")

    if DB_PATH.exists():
        size_gb = DB_PATH.stat().st_size / (1024 ** 3)
        print(f"  Database size: {size_gb:.2f} GB")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        for table in EXPECTED_TABLES:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            check(f"Table '{table}' exists and has rows", count > 0, f"row count: {count:,}")

        conn.close()

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("All checks passed — Stage 1 outputs look good.")
    else:
        print("Some checks failed — review output above.")
    print()


if __name__ == "__main__":
    run()
