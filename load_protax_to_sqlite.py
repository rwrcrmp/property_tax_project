"""
Load Travis County Property Tax Export JSON to SQLite

This script handles a 28GB+ JSON file by:
1. Streaming with ijson (never loads full file into memory)
2. Creating normalized tables for nested arrays
3. Inserting in batches with progress tracking
4. Using SQLite optimizations for bulk inserts

Usage:
    python load_protax_to_sqlite.py
"""

import sqlite3
import ijson
import time
import os
from pathlib import Path
from datetime import datetime
from decimal import Decimal


# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"

JSON_FILE = DATA_RAW / "Travis_protaxExport_20250720.json"
DB_FILE = DATA_PROCESSED / "travis_property_tax.db"

BATCH_SIZE = 10000  # Records per commit
PROGRESS_INTERVAL = 5000  # Print progress every N records


# ============================================================================
# Schema Definitions
# ============================================================================

# Main properties table - top-level fields only
CREATE_PROPERTIES_TABLE = """
CREATE TABLE IF NOT EXISTS properties (
    pID INTEGER PRIMARY KEY,
    pRollCorr INTEGER,
    pVersion INTEGER,
    pYear INTEGER,
    propCreateDt TEXT,
    propType TEXT,
    sitProperty INTEGER,
    reactivateDt TEXT,
    reactivateReason TEXT,
    reactivateNotes TEXT,
    rollCorrCode TEXT,
    rollCorrReason TEXT,
    exemptionReset INTEGER,
    exemptionResetReason TEXT,
    geometry TEXT,
    inactive INTEGER,
    inactiveDt TEXT,
    inactiveReason TEXT,
    inactiveNotes TEXT,
    inspectionYr INTEGER,
    lastAppraisalDt TEXT,
    taxingUnitPercentCalculation TEXT,
    taxingUnitPercentCalculationComment TEXT,
    taxingUnitSplitBoundaryLines INTEGER,
    isUDI INTEGER
);
"""

# Legal description table
CREATE_LEGAL_DESCRIPTION_TABLE = """
CREATE TABLE IF NOT EXISTS property_legal_description (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pID INTEGER NOT NULL,
    asCode TEXT,
    block TEXT,
    lot TEXT,
    additionalLegal TEXT,
    legalAcreage REAL,
    legalDescription TEXT,
    mhSpaceNum TEXT,
    tract TEXT,
    effectiveSizeAcres REAL,
    FOREIGN KEY (pID) REFERENCES properties(pID)
);
"""

# Identification table
CREATE_IDENTIFICATION_TABLE = """
CREATE TABLE IF NOT EXISTS property_identification (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pID INTEGER NOT NULL,
    geoID TEXT,
    refID1 TEXT,
    refID2 TEXT,
    mapID TEXT,
    mapsco TEXT,
    FOREIGN KEY (pID) REFERENCES properties(pID)
);
"""

# Characteristics table
CREATE_CHARACTERISTICS_TABLE = """
CREATE TABLE IF NOT EXISTS property_characteristics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pID INTEGER NOT NULL,
    marketArea TEXT,
    dba TEXT,
    altDBA TEXT,
    condoPct REAL,
    condoUnit TEXT,
    irrigationAcres REAL,
    irrigationCapacity REAL,
    irrigationGPM REAL,
    irrigationWells INTEGER,
    region TEXT,
    roadAccess TEXT,
    topography TEXT,
    sicCd TEXT,
    useCd TEXT,
    utilities TEXT,
    subType TEXT,
    subset TEXT,
    view TEXT,
    zoning TEXT,
    openBusinessDate TEXT,
    FOREIGN KEY (pID) REFERENCES properties(pID)
);
"""

# Profile table (this has many columns based on what we saw)
CREATE_PROFILE_TABLE = """
CREATE TABLE IF NOT EXISTS property_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pID INTEGER NOT NULL,
    bppStateCd TEXT,
    centralAirHeat INTEGER,
    cityTaxingUnitCode TEXT,
    cityTaxingUnitID INTEGER,
    cityTaxingUnitName TEXT,
    exemptions TEXT,
    fieldInspectionDt TEXT,
    fieldInspectionSource TEXT,
    imprvActualYearBuilt INTEGER,
    imprvAge INTEGER,
    imprvClass TEXT,
    imprvClasses TEXT,
    imprvCondition TEXT,
    imprvDeprec REAL,
    imprvDeprecGood REAL,
    imprvEconomicAdj REAL,
    imprvEffYearBuilt INTEGER,
    imprvFactor REAL,
    imprvFunctionalAdj REAL,
    imprvMABaseUnitPrice REAL,
    imprvMAUnitPrice REAL,
    imprvMainArea REAL,
    -- Additional profile fields will be added dynamically if needed
    extra_fields TEXT,  -- JSON for any fields not in schema
    FOREIGN KEY (pID) REFERENCES properties(pID)
);
"""

# Situs (address) table
CREATE_SITUS_TABLE = """
CREATE TABLE IF NOT EXISTS property_situs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pID INTEGER NOT NULL,
    situsAddressID INTEGER,
    primarySitus INTEGER,
    streetNum TEXT,
    streetPrefix TEXT,
    streetName TEXT,
    streetSuffix TEXT,
    streetSecondary TEXT,
    city TEXT,
    state TEXT,
    zip TEXT,
    country TEXT,
    FOREIGN KEY (pID) REFERENCES properties(pID)
);
"""

# Create indexes for faster queries
CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_properties_pYear ON properties(pYear);
CREATE INDEX IF NOT EXISTS idx_properties_propType ON properties(propType);
CREATE INDEX IF NOT EXISTS idx_situs_pID ON property_situs(pID);
CREATE INDEX IF NOT EXISTS idx_situs_zip ON property_situs(zip);
CREATE INDEX IF NOT EXISTS idx_situs_streetName ON property_situs(streetName);
CREATE INDEX IF NOT EXISTS idx_properties_inactive ON properties(inactive);
CREATE INDEX IF NOT EXISTS idx_legal_pID ON property_legal_description(pID);
CREATE INDEX IF NOT EXISTS idx_identification_pID ON property_identification(pID);
CREATE INDEX IF NOT EXISTS idx_identification_geoID ON property_identification(geoID);
CREATE INDEX IF NOT EXISTS idx_characteristics_pID ON property_characteristics(pID);
CREATE INDEX IF NOT EXISTS idx_profile_pID ON property_profile(pID);
"""


# ============================================================================
# Helper Functions
# ============================================================================

def format_time(seconds):
    """Format seconds into human readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def format_size(bytes_size):
    """Format bytes into human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f}{unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f}TB"


def convert_value(value):
    """Convert Decimal and other unsupported types for SQLite."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        # Convert to int if it's a whole number, otherwise float
        return int(value) if value == int(value) else float(value)
    if isinstance(value, (list, dict)):
        # Convert complex types to JSON string
        import json
        return json.dumps(value)
    return value


def get_value(record, key, default=None):
    """Safely get a value from a record, converting types as needed."""
    value = record.get(key, default)
    return convert_value(value)


# ============================================================================
# Database Functions
# ============================================================================

def create_database(db_path):
    """Create the database and tables."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create tables
    cursor.execute(CREATE_PROPERTIES_TABLE)
    cursor.execute(CREATE_LEGAL_DESCRIPTION_TABLE)
    cursor.execute(CREATE_IDENTIFICATION_TABLE)
    cursor.execute(CREATE_CHARACTERISTICS_TABLE)
    cursor.execute(CREATE_PROFILE_TABLE)
    cursor.execute(CREATE_SITUS_TABLE)

    conn.commit()
    return conn


def create_indexes(conn):
    """Create indexes after data load for better performance."""
    print("\nCreating indexes...")
    cursor = conn.cursor()
    for statement in CREATE_INDEXES.strip().split(';'):
        if statement.strip():
            cursor.execute(statement)
    conn.commit()
    print("Indexes created.")


def optimize_for_bulk_insert(conn):
    """Configure SQLite for fast bulk inserts."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA synchronous = OFF")
    cursor.execute("PRAGMA journal_mode = MEMORY")
    cursor.execute("PRAGMA cache_size = -64000")  # 64MB cache
    cursor.execute("PRAGMA temp_store = MEMORY")
    conn.commit()


def insert_property(cursor, record):
    """Insert main property record."""
    sql = """
    INSERT OR REPLACE INTO properties (
        pID, pRollCorr, pVersion, pYear, propCreateDt, propType, sitProperty,
        reactivateDt, reactivateReason, reactivateNotes, rollCorrCode, rollCorrReason,
        exemptionReset, exemptionResetReason, geometry, inactive, inactiveDt,
        inactiveReason, inactiveNotes, inspectionYr, lastAppraisalDt,
        taxingUnitPercentCalculation, taxingUnitPercentCalculationComment,
        taxingUnitSplitBoundaryLines, isUDI
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    cursor.execute(sql, (
        get_value(record, 'pID'),
        get_value(record, 'pRollCorr'),
        get_value(record, 'pVersion'),
        get_value(record, 'pYear'),
        get_value(record, 'propCreateDt'),
        get_value(record, 'propType'),
        get_value(record, 'sitProperty'),
        get_value(record, 'reactivateDt'),
        get_value(record, 'reactivateReason'),
        get_value(record, 'reactivateNotes'),
        get_value(record, 'rollCorrCode'),
        get_value(record, 'rollCorrReason'),
        get_value(record, 'exemptionReset'),
        get_value(record, 'exemptionResetReason'),
        get_value(record, 'geometry'),
        get_value(record, 'inactive'),
        get_value(record, 'inactiveDt'),
        get_value(record, 'inactiveReason'),
        get_value(record, 'inactiveNotes'),
        get_value(record, 'inspectionYr'),
        get_value(record, 'lastAppraisalDt'),
        get_value(record, 'taxingUnitPercentCalculation'),
        get_value(record, 'taxingUnitPercentCalculationComment'),
        get_value(record, 'taxingUnitSplitBoundaryLines'),
        get_value(record, 'isUDI'),
    ))


def insert_legal_descriptions(cursor, pID, legal_descs):
    """Insert property legal description records."""
    if not legal_descs:
        return

    sql = """
    INSERT INTO property_legal_description (
        pID, asCode, block, lot, additionalLegal, legalAcreage,
        legalDescription, mhSpaceNum, tract, effectiveSizeAcres
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    for desc in legal_descs:
        cursor.execute(sql, (
            pID,
            get_value(desc, 'asCode'),
            get_value(desc, 'block'),
            get_value(desc, 'lot'),
            get_value(desc, 'additionalLegal'),
            get_value(desc, 'legalAcreage'),
            get_value(desc, 'legalDescription'),
            get_value(desc, 'mhSpaceNum'),
            get_value(desc, 'tract'),
            get_value(desc, 'effectiveSizeAcres'),
        ))


def insert_identifications(cursor, pID, identifications):
    """Insert property identification records."""
    if not identifications:
        return

    sql = """
    INSERT INTO property_identification (
        pID, geoID, refID1, refID2, mapID, mapsco
    ) VALUES (?, ?, ?, ?, ?, ?)
    """
    for ident in identifications:
        cursor.execute(sql, (
            pID,
            get_value(ident, 'geoID'),
            get_value(ident, 'refID1'),
            get_value(ident, 'refID2'),
            get_value(ident, 'mapID'),
            get_value(ident, 'mapsco'),
        ))


def insert_characteristics(cursor, pID, characteristics):
    """Insert property characteristics records."""
    if not characteristics:
        return

    sql = """
    INSERT INTO property_characteristics (
        pID, marketArea, dba, altDBA, condoPct, condoUnit, irrigationAcres,
        irrigationCapacity, irrigationGPM, irrigationWells, region, roadAccess,
        topography, sicCd, useCd, utilities, subType, subset, view, zoning,
        openBusinessDate
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    for char in characteristics:
        cursor.execute(sql, (
            pID,
            get_value(char, 'marketArea'),
            get_value(char, 'dba'),
            get_value(char, 'altDBA'),
            get_value(char, 'condoPct'),
            get_value(char, 'condoUnit'),
            get_value(char, 'irrigationAcres'),
            get_value(char, 'irrigationCapacity'),
            get_value(char, 'irrigationGPM'),
            get_value(char, 'irrigationWells'),
            get_value(char, 'region'),
            get_value(char, 'roadAccess'),
            get_value(char, 'topography'),
            get_value(char, 'sicCd'),
            get_value(char, 'useCd'),
            get_value(char, 'utilities'),
            get_value(char, 'subType'),
            get_value(char, 'subset'),
            get_value(char, 'view'),
            get_value(char, 'zoning'),
            get_value(char, 'openBusinessDate'),
        ))


def insert_profiles(cursor, pID, profiles):
    """Insert property profile records."""
    if not profiles:
        return

    import json

    # Known columns in our schema
    known_columns = {
        'bppStateCd', 'centralAirHeat', 'cityTaxingUnitCode', 'cityTaxingUnitID',
        'cityTaxingUnitName', 'exemptions', 'fieldInspectionDt', 'fieldInspectionSource',
        'imprvActualYearBuilt', 'imprvAge', 'imprvClass', 'imprvClasses',
        'imprvCondition', 'imprvDeprec', 'imprvDeprecGood', 'imprvEconomicAdj',
        'imprvEffYearBuilt', 'imprvFactor', 'imprvFunctionalAdj', 'imprvMABaseUnitPrice',
        'imprvMAUnitPrice', 'imprvMainArea', 'pID'
    }

    sql = """
    INSERT INTO property_profile (
        pID, bppStateCd, centralAirHeat, cityTaxingUnitCode, cityTaxingUnitID,
        cityTaxingUnitName, exemptions, fieldInspectionDt, fieldInspectionSource,
        imprvActualYearBuilt, imprvAge, imprvClass, imprvClasses, imprvCondition,
        imprvDeprec, imprvDeprecGood, imprvEconomicAdj, imprvEffYearBuilt,
        imprvFactor, imprvFunctionalAdj, imprvMABaseUnitPrice, imprvMAUnitPrice,
        imprvMainArea, extra_fields
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    for profile in profiles:
        # Collect extra fields not in our schema, converting Decimals
        extra = {k: convert_value(v) for k, v in profile.items() if k not in known_columns}
        extra_json = json.dumps(extra) if extra else None

        cursor.execute(sql, (
            pID,
            get_value(profile, 'bppStateCd'),
            get_value(profile, 'centralAirHeat'),
            get_value(profile, 'cityTaxingUnitCode'),
            get_value(profile, 'cityTaxingUnitID'),
            get_value(profile, 'cityTaxingUnitName'),
            get_value(profile, 'exemptions'),
            get_value(profile, 'fieldInspectionDt'),
            get_value(profile, 'fieldInspectionSource'),
            get_value(profile, 'imprvActualYearBuilt'),
            get_value(profile, 'imprvAge'),
            get_value(profile, 'imprvClass'),
            get_value(profile, 'imprvClasses'),
            get_value(profile, 'imprvCondition'),
            get_value(profile, 'imprvDeprec'),
            get_value(profile, 'imprvDeprecGood'),
            get_value(profile, 'imprvEconomicAdj'),
            get_value(profile, 'imprvEffYearBuilt'),
            get_value(profile, 'imprvFactor'),
            get_value(profile, 'imprvFunctionalAdj'),
            get_value(profile, 'imprvMABaseUnitPrice'),
            get_value(profile, 'imprvMAUnitPrice'),
            get_value(profile, 'imprvMainArea'),
            extra_json,
        ))


def insert_situses(cursor, pID, situses):
    """Insert property situs (address) records."""
    if not situses:
        return

    sql = """
    INSERT INTO property_situs (
        pID, situsAddressID, primarySitus, streetNum, streetPrefix,
        streetName, streetSuffix, streetSecondary, city, state, zip, country
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    for situs in situses:
        cursor.execute(sql, (
            pID,
            get_value(situs, 'situsAddressID'),
            get_value(situs, 'primarySitus'),
            get_value(situs, 'streetNum'),
            get_value(situs, 'streetPrefix'),
            get_value(situs, 'streetName'),
            get_value(situs, 'streetSuffix'),
            get_value(situs, 'streetSecondary'),
            get_value(situs, 'city'),
            get_value(situs, 'state'),
            get_value(situs, 'zip'),
            get_value(situs, 'country'),
        ))


def process_record(cursor, record):
    """Process a single property record and insert into all tables."""
    pID = convert_value(record.get('pID'))
    if pID is None:
        return False

    # Insert main property
    insert_property(cursor, record)

    # Insert nested arrays
    insert_legal_descriptions(cursor, pID, record.get('propertyLegalDescription', []))
    insert_identifications(cursor, pID, record.get('propertyIdentification', []))
    insert_characteristics(cursor, pID, record.get('propertyCharacteristics', []))
    insert_profiles(cursor, pID, record.get('propertyProfile', []))
    insert_situses(cursor, pID, record.get('situses', []))

    return True


# ============================================================================
# Main Processing
# ============================================================================

def load_json_to_sqlite(json_path, db_path, batch_size=BATCH_SIZE):
    """
    Stream JSON file and load into SQLite database.
    """
    # Get file size for progress tracking
    file_size = os.path.getsize(json_path)
    print(f"Input file: {json_path}")
    print(f"File size: {format_size(file_size)}")
    print(f"Output database: {db_path}")
    print(f"Batch size: {batch_size:,} records")
    print()

    # Ensure output directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing database if present
    if db_path.exists():
        print(f"Removing existing database...")
        db_path.unlink()

    # Create database and tables
    print("Creating database and tables...")
    conn = create_database(db_path)
    optimize_for_bulk_insert(conn)
    cursor = conn.cursor()

    # Process records
    print("\nProcessing records...")
    print("-" * 60)

    start_time = time.time()
    records_processed = 0
    records_failed = 0
    last_progress_time = start_time

    try:
        with open(json_path, 'rb') as f:
            # Stream parse the JSON array
            parser = ijson.items(f, 'item')

            for record in parser:
                try:
                    if process_record(cursor, record):
                        records_processed += 1
                    else:
                        records_failed += 1
                except Exception as e:
                    records_failed += 1
                    if records_failed <= 10:  # Only print first 10 errors
                        print(f"Error processing record: {e}")

                # Commit in batches
                if records_processed % batch_size == 0:
                    conn.commit()

                # Progress update
                if records_processed % PROGRESS_INTERVAL == 0:
                    current_time = time.time()
                    elapsed = current_time - start_time
                    rate = records_processed / elapsed if elapsed > 0 else 0

                    # Estimate position in file
                    file_pos = f.tell()
                    pct_complete = (file_pos / file_size) * 100

                    print(f"  Processed: {records_processed:>10,} records | "
                          f"Rate: {rate:>8,.0f}/sec | "
                          f"Progress: {pct_complete:>5.1f}% | "
                          f"Elapsed: {format_time(elapsed)}")

        # Final commit
        conn.commit()

    except KeyboardInterrupt:
        print("\n\nInterrupted! Saving progress...")
        conn.commit()

    except Exception as e:
        print(f"\nError during processing: {e}")
        conn.commit()
        raise

    # Summary
    end_time = time.time()
    total_time = end_time - start_time

    print("-" * 60)
    print(f"\nProcessing complete!")
    print(f"  Total records processed: {records_processed:,}")
    print(f"  Failed records: {records_failed:,}")
    print(f"  Total time: {format_time(total_time)}")
    print(f"  Average rate: {records_processed/total_time:,.0f} records/sec")

    # Create indexes
    create_indexes(conn)

    # Final statistics
    print("\nTable row counts:")
    for table in ['properties', 'property_legal_description', 'property_identification',
                  'property_characteristics', 'property_profile', 'property_situs']:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"  {table}: {count:,}")

    # Database file size
    conn.close()
    db_size = os.path.getsize(db_path)
    print(f"\nDatabase file size: {format_size(db_size)}")

    return records_processed


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Travis County Property Tax Export - JSON to SQLite Loader")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    # Verify input file exists
    if not JSON_FILE.exists():
        print(f"ERROR: Input file not found: {JSON_FILE}")
        exit(1)

    # Run the loader
    try:
        load_json_to_sqlite(JSON_FILE, DB_FILE)
        print("\nSuccess!")
    except Exception as e:
        print(f"\nFailed with error: {e}")
        exit(1)
