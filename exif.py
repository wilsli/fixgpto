#!/usr/bin/env python3
"""Fill Exif metadata from Google Photos supplemental-metadata.json files."""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from exiftool_wrapper import write_metadata as fill_exiftool, write_file_created_date
from version import __version__

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".cr2", ".heic", ".heif", ".mov", ".mp4", ".gif", ".mpg"}


def timestamp_to_datetime(timestamp_str):
    from datetime import datetime, timezone
    ts = int(timestamp_str)
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y:%m:%d %H:%M:%S")


def _get_expected_image_name(json_stem):
    """Convert a JSON stem like 'IMG_0580.JPG.supplemental-metadata(1)' to 'IMG_0580(1).JPG'."""
    stem = json_stem.replace(".supplemental-metadata", "").rstrip(".")

    match = re.match(r"^(.+)(\(\d+\))$", stem)
    if match:
        base = match.group(1)
        suffix = match.group(2)

        # Check if base already has (N) right before extension: "NAME(N).ext"
        inner_match = re.match(r"^(.+)\((\d+)\)\.(.+)$", base)
        if inner_match:
            return base

        # Special case: base is just "(N).ext" like "(3).jpg"
        # The parenthesized number IS the original filename, not a duplicate marker
        if re.match(r"^\(\d+\)\.", base):
            return base

        # Insert suffix before the file extension
        dot_pos = base.rfind(".")
        if dot_pos != -1:
            return base[:dot_pos] + suffix + base[dot_pos:]
        return base + suffix

    return stem


def _get_trailing_dot_count(json_stem):
    """Count trailing dots in the JSON stem after removing .supplemental-metadata."""
    raw = json_stem.replace(".supplemental-metadata", "")
    return len(raw) - len(raw.rstrip('.'))


def _decode_google_escape(name_without_ext, trailing_dots):
    """Decode Google Photos' trailing dot-to-underscore encoding.
    
    Google Photos encodes trailing '_' as '.' in supplemental-metadata JSON stems.
    Since we can't distinguish original dots from encoded underscores, we try all
    possible suffix combinations of dots and underscores.
    """
    stripped = name_without_ext.rstrip('.')
    
    if trailing_dots == 0:
        return [name_without_ext]
    
    results = []
    for i in range(trailing_dots + 1):
        result = stripped + '.' * i + '_' * (trailing_dots - i)
        results.append(result)
    return results


def _find_matching_image(json_file, expected_name, trailing_dots):
    """Find a matching image file from a candidate name stem.
    
    Tries direct match first, then Google Photos escape decoding variants.
    """
    candidates = list(json_file.parent.iterdir())
    
    # Direct match against full filename
    matched = [c for c in candidates if c.name.upper() == expected_name.upper() and c.suffix.lower() in SUPPORTED_EXTENSIONS]
    if matched:
        return matched
    
    # Decode Google escape: compare name stem without extension
    decoded_variants = _decode_google_escape(expected_name, trailing_dots)
    for variant in decoded_variants:
        matched = [c for c in candidates if c.with_suffix('').name.upper() == variant.upper() and c.suffix.lower() in SUPPORTED_EXTENSIONS]
        if matched:
            return matched
    
    return None


def fill_exif(image_path, meta, dry_run=False):
    return fill_exiftool(image_path, meta, dry_run=dry_run)


def process_directory(directory, recursive=False, dry_run=False):
    dir_path = Path(directory)
    if recursive:
        json_files = sorted(dir_path.rglob("*.json"))
    else:
        json_files = sorted(dir_path.glob("*.json"))

    results = []
    skip_reasons = []
    for json_file in json_files:
        if ".supplemental-metadata" not in json_file.name:
            continue
        expected_name = _get_expected_image_name(json_file.stem)
        trailing_dots = _get_trailing_dot_count(json_file.stem)
        matched = _find_matching_image(json_file, expected_name, trailing_dots)
        if not matched and '.' not in expected_name:
            candidates = list(json_file.parent.iterdir())
            for ext in SUPPORTED_EXTENSIONS:
                alt_name = f"{expected_name}{ext}"
                alt_matched = [c for c in candidates if c.name.upper() == alt_name.upper()]
                if alt_matched:
                    matched = alt_matched
                    break
        if not matched:
            rel_path = json_file.relative_to(dir_path)
            print(f"[SKIP] No matching image for {rel_path}")
            skip_reasons.append(str(rel_path))
            continue

        image_path = str(matched[0])
        with open(json_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        written, skipped = fill_exif(image_path, meta, dry_run=dry_run)

        prefix = "[DRY RUN] " if dry_run else ""
        status = "OK" if written else "ALL EXISTING"
        print(f"{prefix}[{status}] {image_path}")
        for w in written:
            print(f"  + {w}")
        for s in skipped:
            print(f"  ~ skip {s}")
        results.append({
            "file": image_path,
            "written": written,
            "skipped": skipped,
        })

    return results, skip_reasons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="Directory to process")
    parser.add_argument("-r", "--recursive", action="store_true", help="Process subdirectories recursively")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be written without modifying files")
    parser.add_argument("--prune-json", action="store_true", help="Delete JSON files that failed to match a media file")
    import platform
    exe_name = os.path.basename(sys.executable) if hasattr(sys, 'executable') else ''
    plat = f"{platform.system()} {platform.machine()}"
    if getattr(sys, '_MEIPASS', None):
        plat += " (bundled)"
    parser.add_argument("--version", action="version", version=f"GooglePhotos Takeout Metadata Fixer: {__version__} [{plat}]")
    args = parser.parse_args()

    directory = args.directory
    if not os.path.isdir(directory):
        print(f"Error: {directory} is not a directory")
        sys.exit(1)

    results, skip_reasons = process_directory(directory, recursive=args.recursive, dry_run=args.dry_run)
    
    pruned = []
    if args.prune_json:
        for rel in skip_reasons:
            json_path = Path(directory) / rel
            if json_path.exists():
                if not args.dry_run:
                    json_path.unlink()
                pruned.append(rel)

    total_written = sum(len(r["written"]) for r in results)
    total_skipped = sum(len(r["skipped"]) for r in results)
    print(f"\nDone: {len(results)} files processed, {total_written} tags written, {total_skipped} tags skipped")
    if pruned:
        print(f"Pruned {len(pruned)} unmatched JSON file(s):")
        for p in pruned:
            print(f"  - {p}")

    if skip_reasons:
        print("\n--- Skipped Files ---")
        for path in skip_reasons:
            print(f"  ! {path}")


if __name__ == "__main__":
    main()
