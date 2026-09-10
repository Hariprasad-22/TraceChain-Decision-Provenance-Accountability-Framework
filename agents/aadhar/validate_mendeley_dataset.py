"""
Downloads (manually, see below) and validates the Mendeley synthetic
Aadhaar dataset. Since the "Aadhaar number" only exists as printed text
inside each image, this reuses the same Gemini vision extraction your
agent already uses, then checks each extracted number against the real
Verhoeff checksum.

--- Getting the data ---
Mendeley blocks scripted/automated downloads, so this step is manual:
1. Go to https://data.mendeley.com/datasets/wk6n8fhx3c/1
2. Click "Download all 1000 files (as ZIP)" (or similar button on the page)
3. Extract the ZIP into a folder next to this script, e.g. mendeley_aadhar/
4. Run this script: python validate_mendeley_dataset.py

--- What this does ---
- Scans the folder for image files
- Samples N of them (default 20, to control Gemini API usage - raise
  --limit if you want to check more; the full 1000 will use real quota)
- Extracts fields from each with Gemini vision (same extract_aadhaar_fields
  used by the real agent)
- Validates the extracted Aadhaar number against the Verhoeff checksum
- Prints a summary and saves full results to validation_results.json
"""
import argparse
import glob
import json
import os
import random
import time

from aadhar_extraction import extract_aadhaar_fields
from verhoeff import is_valid_aadhaar_checksum

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")


def find_images(folder: str) -> list:
    files = []
    for ext in IMAGE_EXTENSIONS:
        files.extend(glob.glob(os.path.join(folder, "**", f"*{ext}"), recursive=True))
    return sorted(files)


def validate(folder: str, limit: int, seed: int = 42, delay: float = 1.0):
    all_images = find_images(folder)
    if not all_images:
        print(f"No images found in '{folder}'. Did you extract the ZIP there?")
        return

    random.seed(seed)
    sample = random.sample(all_images, min(limit, len(all_images)))
    print(f"Found {len(all_images)} images total. Checking a sample of {len(sample)}.\n")

    results = []
    valid_count = 0
    error_count = 0

    for i, path in enumerate(sample, 1):
        print(f"[{i}/{len(sample)}] {os.path.basename(path)} ...", end=" ")
        try:
            extracted = extract_aadhaar_fields(path)
            number = (extracted.get("aadhaar_number") or "").replace(" ", "")
            valid = is_valid_aadhaar_checksum(number)
            valid_count += valid
            results.append({"file": path, "extracted": extracted, "checksum_valid": valid})
            print(f"number={number or 'N/A'}  checksum_valid={valid}")
        except Exception as e:
            error_count += 1
            results.append({"file": path, "error": str(e)})
            print(f"ERROR: {e}")

        time.sleep(delay)  # gentle on API rate limits

    with open("validation_results.json", "w") as f:
        json.dump(results, f, indent=2)

    checked = len(sample) - error_count
    print("\n=== Summary ===")
    print(f"Checked:        {checked}/{len(sample)} (errors: {error_count})")
    if checked:
        print(f"Checksum valid: {valid_count}/{checked} ({100*valid_count/checked:.1f}%)")
    print("Full results saved to validation_results.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", default="mendeley_aadhar", help="Folder containing extracted images")
    parser.add_argument("--limit", type=int, default=20, help="How many images to sample and check")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between API calls")
    args = parser.parse_args()

    validate(args.folder, args.limit, delay=args.delay)
