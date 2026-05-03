"""
Download the Travis CAD property tax export — manual prerequisite step.

This script is NOT part of the main pipeline (main.py). Run it once manually
to download and extract the raw TCAD JSON before running main.py.

Usage:
    python scripts/fetch_tcad.py

Requirements:
    pip install requests tqdm
"""

import requests
import zipfile
from pathlib import Path

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    print("Note: Install 'tqdm' for a nicer progress bar: pip install tqdm")

PROJECT_ROOT = Path(__file__).parent.parent
DATA_SOURCES = PROJECT_ROOT / "data" / "sources"

EXPORTS = {
    "special_2025": {
        "url": "https://traviscad.org/wp-content/largefiles/2025%20Special%20export%20Supp%201%2007202025.zip",
        "description": "2025 Special Export (July 2025)"
    },
    "special_2025_supp": {
        "url": "https://traviscad.org/wp-content/largefiles/2025%20Special%20export%20Supp%208%2001072026.zip",
        "description": "2025 Supplemental Special Export (January 2026)"
    }
}

SELECTED_EXPORT = "special_2025"


def download_large_file(url: str, dest_path: Path, chunk_size: int = 8192) -> bool:
    """
    Download a large file with progress tracking using chunked streaming.

    Streams the file in chunks rather than loading it all into memory,
    similar to how you might use chunked reading in R with readr::read_csv_chunked().
    """
    print(f"Downloading: {url}")
    print(f"Saving to: {dest_path}")

    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))

        if total_size:
            print(f"File size: {total_size / (1024 * 1024):.1f} MB")
        else:
            print("File size: Unknown (server didn't provide content-length)")

        downloaded = 0

        with open(dest_path, 'wb') as f:
            if HAS_TQDM and total_size:
                chunks = tqdm(
                    response.iter_content(chunk_size=chunk_size),
                    total=total_size // chunk_size,
                    unit='KB',
                    unit_scale=True,
                    desc="Downloading"
                )
            else:
                chunks = response.iter_content(chunk_size=chunk_size)

            for chunk in chunks:
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

                    if not HAS_TQDM and total_size:
                        pct = (downloaded / total_size) * 100
                        print(f"\rProgress: {pct:.1f}% ({downloaded / 1024 / 1024:.1f} MB)", end='')

        print(f"\nDownload complete: {dest_path}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"\nDownload failed: {e}")
        return False


def extract_zip(zip_path: Path, extract_to: Path) -> list:
    """Extract a ZIP file and return list of extracted files."""
    print(f"\nExtracting: {zip_path}")

    extracted_files = []

    with zipfile.ZipFile(zip_path, 'r') as zf:
        print(f"ZIP contains {len(zf.namelist())} file(s):")
        for name in zf.namelist():
            info = zf.getinfo(name)
            print(f"  - {name} ({info.file_size / (1024 * 1024):.1f} MB)")

        zf.extractall(extract_to)

        for name in zf.namelist():
            original_path = extract_to / name
            standardized_name = name.replace("-", "_")
            standardized_path = extract_to / standardized_name

            if original_path != standardized_path and original_path.exists():
                original_path.rename(standardized_path)
                print(f"  Renamed: {name} -> {standardized_name}")
                extracted_files.append(standardized_path)
            else:
                extracted_files.append(original_path)

    print(f"Extracted to: {extract_to}")
    return extracted_files


def run():
    DATA_SOURCES.mkdir(parents=True, exist_ok=True)

    export = EXPORTS[SELECTED_EXPORT]
    url = export["url"]
    zip_filename = url.split("/")[-1].replace("%20", "_")
    zip_path = DATA_SOURCES / zip_filename

    print("=" * 60)
    print("Travis CAD Export Downloader")
    print(f"Selected: {export['description']}")
    print("=" * 60)

    if zip_path.exists():
        print(f"ZIP already exists, skipping download: {zip_path}")
    else:
        success = download_large_file(url, zip_path)
        if not success:
            raise RuntimeError("Download failed. Check the URL and your internet connection.")

    if zip_path.exists():
        extract_zip(zip_path, DATA_SOURCES)

    print("\n" + "=" * 60)
    print("Done. Next step: run load_protax_to_sqlite.py to build the database.")
    print("=" * 60)


if __name__ == "__main__":
    run()
