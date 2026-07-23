#!/usr/bin/env python3
"""Fill Exif metadata from Google Photos supplemental-metadata.json files."""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

import piexif

from exiftool_wrapper import write_metadata as fill_exiftool
from version import __version__

# Formats handled by piexif (JPEG/TIFF-based)
PIEXIF_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".cr2"}

# Formats handled by exiftool (HEIC/HEIF/MOV/MP4/MPG)
EXIFTOOL_EXTENSIONS = {".heic", ".heif", ".mov", ".mp4", ".gif", ".mpg"}

SUPPORTED_EXTENSIONS = PIEXIF_EXTENSIONS | EXIFTOOL_EXTENSIONS


def decimal_to_dms(value):
    abs_value = abs(value)
    degrees = int(abs_value)
    minutes_full = (abs_value - degrees) * 60
    minutes = int(minutes_full)
    seconds = round((minutes_full - minutes) * 60, 3)
    if seconds >= 60:
        seconds -= 60
        minutes += 1
    return [
        Fraction(seconds).limit_denominator(1000),
        Fraction(minutes).limit_denominator(1000),
        Fraction(degrees).limit_denominator(1000),
    ]


def dms_to_exif(dms):
    return tuple(
        (int(frac.numerator), int(frac.denominator)) for frac in dms
    )


def timestamp_to_datetime(timestamp_str):
    ts = int(timestamp_str)
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y:%m:%d %H:%M:%S")


def timestamp_to_setfile_date(timestamp_str):
    """Convert Unix timestamp to SetFile-compatible date format (mm/dd/yyyy hh:mm:ss AM/PM)."""
    ts = int(timestamp_str)
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    # Convert to local timezone for SetFile
    dt_local = dt.astimezone()
    return dt_local.strftime("%m/%d/%Y %I:%M:%S %p")


def get_existing_exif(image_path):
    try:
        return piexif.load(str(image_path))
    except Exception:
        return {'Exif': {}, 'GPS': {}, 'Image': {}}


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


def set_ifd_tag(exif_dict, ifd_name, tag, value):
    if ifd_name not in exif_dict or exif_dict[ifd_name] is None:
        exif_dict[ifd_name] = {}
    exif_dict[ifd_name][tag] = value


def has_tag(exif_dict, ifd_name, tag):
    ifd = exif_dict.get(ifd_name)
    return bool(ifd and tag in ifd)


def fill_exif(image_path, meta, dry_run=False):
    ext = Path(image_path).suffix.lower()
    if ext in EXIFTOOL_EXTENSIONS:
        return fill_exiftool(image_path, meta, dry_run=dry_run)

    exif_dict = get_existing_exif(image_path)
    written = []
    skipped = []

    # --- DateTimeOriginal (from photoTakenTime) ---
    phototaken = meta.get("photoTakenTime")
    if phototaken and "timestamp" in phototaken:
        dt_str = timestamp_to_datetime(phototaken["timestamp"])
        if has_tag(exif_dict, "Exif", piexif.ExifIFD.DateTimeOriginal):
            skipped.append("DateTimeOriginal")
        else:
            set_ifd_tag(exif_dict, "Exif", piexif.ExifIFD.DateTimeOriginal, dt_str.encode("ascii"))
            written.append(f"DateTimeOriginal={dt_str}")

    # --- DateTimeDigitized (from creationTime) ---
    creation_time = meta.get("creationTime")
    if creation_time and "timestamp" in creation_time:
        dt_str = timestamp_to_datetime(creation_time["timestamp"])
        if has_tag(exif_dict, "Exif", piexif.ExifIFD.DateTimeDigitized):
            skipped.append("DateTimeDigitized")
        else:
            set_ifd_tag(exif_dict, "Exif", piexif.ExifIFD.DateTimeDigitized, dt_str.encode("ascii"))
            written.append(f"DateTimeDigitized={dt_str}")

    # --- DateTime (prefer photoTakenTime, fall back to creationTime) ---
    datetime_source = meta.get("photoTakenTime") or creation_time
    if datetime_source and "timestamp" in datetime_source:
        dt_str = timestamp_to_datetime(datetime_source["timestamp"])
        if has_tag(exif_dict, "Image", piexif.ImageIFD.DateTime):
            skipped.append("DateTime")
        else:
            set_ifd_tag(exif_dict, "Image", piexif.ImageIFD.DateTime, dt_str.encode("ascii"))
            written.append(f"DateTime={dt_str}")

    # --- GPS ---
    geo = meta.get("geoData", {})
    lat = geo.get("latitude")
    lng = geo.get("longitude")
    alt = geo.get("altitude")

    if lat and lat != 0.0:
        if has_tag(exif_dict, "GPS", piexif.GPSIFD.GPSLatitude):
            skipped.append("GPSLatitude")
        else:
            dms = decimal_to_dms(lat)
            ref = b"N" if lat >= 0 else b"S"
            set_ifd_tag(exif_dict, "GPS", piexif.GPSIFD.GPSLatitudeRef, ref)
            set_ifd_tag(exif_dict, "GPS", piexif.GPSIFD.GPSLatitude, dms_to_exif(dms))
            written.append(f"GPSLatitude={lat}")

        if has_tag(exif_dict, "GPS", piexif.GPSIFD.GPSLongitude):
            skipped.append("GPSLongitude")
        else:
            dms = decimal_to_dms(lng)
            ref = b"E" if lng >= 0 else b"W"
            set_ifd_tag(exif_dict, "GPS", piexif.GPSIFD.GPSLongitudeRef, ref)
            set_ifd_tag(exif_dict, "GPS", piexif.GPSIFD.GPSLongitude, dms_to_exif(dms))
            written.append(f"GPSLongitude={lng}")

    if alt and alt != 0.0:
        if has_tag(exif_dict, "GPS", piexif.GPSIFD.GPSAltitude):
            skipped.append("GPSAltitude")
        else:
            if alt >= 0:
                set_ifd_tag(exif_dict, "GPS", piexif.GPSIFD.GPSAltitudeRef, b"\x00\x00")
                set_ifd_tag(
                    exif_dict, "GPS", piexif.GPSIFD.GPSAltitude,
                    ((int(alt * 100), 100),)
                )
            else:
                set_ifd_tag(exif_dict, "GPS", piexif.GPSIFD.GPSAltitudeRef, b"\x01\x00")
                set_ifd_tag(
                    exif_dict, "GPS", piexif.GPSIFD.GPSAltitude,
                    ((int(abs(alt) * 100), 100),)
                )
            written.append(f"GPSAltitude={alt}")

    # --- ImageDescription ---
    description = meta.get("description")
    if description:
        if has_tag(exif_dict, "Image", piexif.ImageIFD.ImageDescription):
            skipped.append("ImageDescription")
        else:
            set_ifd_tag(
                exif_dict, "Image", piexif.ImageIFD.ImageDescription,
                description.encode("utf-8")
            )
            written.append(f"ImageDescription={description}")

    if written and not dry_run:
        new_exif_bytes = piexif.dump(exif_dict)
        piexif.insert(new_exif_bytes, image_path)

    # --- Filesystem CreationDate (from photoTakenTime or photoCreationTime) ---
    fs_creation = meta.get("photoTakenTime") or meta.get("photoCreationTime")
    if fs_creation and "timestamp" in fs_creation and not dry_run:
        dt_str_setfile = timestamp_to_setfile_date(fs_creation["timestamp"])
        try:
            import subprocess
            result = subprocess.run(
                ["SetFile", "-d", dt_str_setfile, str(image_path)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                written.append(f"FileCreateDate={dt_str_setfile}")
            else:
                skipped.append("FileCreateDate")
        except FileNotFoundError:
            skipped.append("FileCreateDate")
        except Exception:
            skipped.append("FileCreateDate")

    return written, skipped


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
        print(f"{prefix}[{status}] {os.path.basename(image_path)}")
        for w in written:
            print(f"  + {w}")
        for s in skipped:
            print(f"  ~ skip {s}")
        results.append({
            "file": os.path.basename(image_path),
            "written": written,
            "skipped": skipped,
        })

    return results, skip_reasons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="Directory to process")
    parser.add_argument("-r", "--recursive", action="store_true", help="Process subdirectories recursively")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be written without modifying files")
    parser.add_argument("--version", action="version", version=f"GooglePhotos Takeout Metadata Fixer: {__version__}")
    args = parser.parse_args()

    directory = args.directory
    if not os.path.isdir(directory):
        print(f"Error: {directory} is not a directory")
        sys.exit(1)

    results, skip_reasons = process_directory(directory, recursive=args.recursive, dry_run=args.dry_run)
    total_written = sum(len(r["written"]) for r in results)
    total_skipped = sum(len(r["skipped"]) for r in results)
    print(f"\nDone: {len(results)} files processed, {total_written} tags written, {total_skipped} tags skipped")

    if skip_reasons:
        print("\n--- Skipped Files ---")
        for path in skip_reasons:
            print(f"  ! {path}")


if __name__ == "__main__":
    main()
