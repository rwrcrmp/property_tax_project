"""
Stage 0 preflight check — runs before main.py decides whether to build the database.

Checks if a valid SQLite database already exists with the expected tables and
a plausible file size. If all checks pass, Stage 1 is skipped.

Usage:
    python scripts/stage0_preflight.py
"""

import sqlite3
from pathlib import Path

PROJECT_ROOT   = Path(__file__).parent.parent
DB_PATH        = PROJECT_ROOT / "data" / "sources" / "travis_property_tax.db"
MIN_SIZE_GB    = 0.5   # below this likely indicates an incomplete build
MIN_ROW_COUNT  = 100_000  # minimum plausible row count for properties table

EXPECTED_TABLES = [
    "properties",
    "property_profile",
    "property_characteristics",
    "property_situs",
    "property_legal_description",
    "property_identification",
]


def db_ready() -> bool:
    """
    Return True if the database exists and passes all preflight checks.
    Prints a summary of what was found either way.
    """
    print("\n=== Stage 0 Preflight: Database Check ===")

    if not DB_PATH.exists():
        print("  No database found — Stage 1 will run.")
        return False

    size_gb = DB_PATH.stat().st_size / (1024 ** 3)
    print(f"  Found: {DB_PATH.name} ({size_gb:.2f} GB)")

    if size_gb < MIN_SIZE_GB:
        print(f"  FAIL  Database too small ({size_gb:.2f} GB < {MIN_SIZE_GB} GB) — likely incomplete.")
        print("  Stage 1 will run and rebuild the database.")
        return False

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        for table in EXPECTED_TABLES:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            if count == 0:
                print(f"  FAIL  Table '{table}' is empty — database may be incomplete.")
                conn.close()
                print("  Stage 1 will run and rebuild the database.")
                return False
            print(f"  PASS  {table}: {count:,} rows")

        cursor.execute("SELECT COUNT(*) FROM properties")
        prop_count = cursor.fetchone()[0]
        if prop_count < MIN_ROW_COUNT:
            print(f"  FAIL  properties table has only {prop_count:,} rows — expected at least {MIN_ROW_COUNT:,}.")
            conn.close()
            print("  Stage 1 will run and rebuild the database.")
            return False

        conn.close()

    except sqlite3.DatabaseError as e:
        print(f"  FAIL  Database error: {e}")
        print("  Stage 1 will run and rebuild the database.")
        return False

    print("  All preflight checks passed — skipping Stage 1.")
    return True


if __name__ == "__main__":
    db_ready()
