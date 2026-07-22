#!/usr/bin/env python3
"""Fill Exif metadata from Google Photos supplemental-metadata.json files."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

import piexif

from exiftool_wrapper import write_metadata as fill_exiftool

# Formats handled by piexif (JPEG/TIFF-based)
PIEXIF_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff"}

# Formats handled by exiftool (HEIC/HEIF/MOV/MP4)
EXIFTOOL_EXTENSIONS = {".heic", ".heif", ".mov", ".mp4", ".gif"}

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


def get_existing_exif(image_path):
    try:
        return piexif.load(str(image_path))
    except Exception:
        return {'Exif': {}, 'GPS': {}, 'Image': {}}


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

    # --- DateTimeOriginal / DateTimeDigitized ---
    time_source = meta.get("photoTakenTime") or meta.get("creationTime")
    if time_source and "timestamp" in time_source:
        dt_str = timestamp_to_datetime(time_source["timestamp"])
        for tag_name, tag_id in [
            ("DateTimeOriginal", piexif.ExifIFD.DateTimeOriginal),
            ("DateTimeDigitized", piexif.ExifIFD.DateTimeDigitized),
        ]:
            if has_tag(exif_dict, "Exif", tag_id):
                skipped.append(tag_name)
            else:
                set_ifd_tag(exif_dict, "Exif", tag_id, dt_str.encode("ascii"))
                written.append(f"{tag_name}={dt_str}")

    # --- DateTime ---
    creation_time = meta.get("creationTime")
    if creation_time and "timestamp" in creation_time:
        dt_str = timestamp_to_datetime(creation_time["timestamp"])
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

    return written, skipped


def process_directory(directory, recursive=False, dry_run=False):
    dir_path = Path(directory)
    if recursive:
        json_files = sorted(dir_path.rglob("*.supplemental-metadata.json"))
    else:
        json_files = sorted(dir_path.glob("*.supplemental-metadata.json"))

    results = []
    for json_file in json_files:
        base_name = json_file.stem.replace(".supplemental-metadata", "")
        candidates = list(json_file.parent.iterdir())
        matched = [c for c in candidates if c.name.upper() == base_name.upper() and c.suffix.lower() in SUPPORTED_EXTENSIONS]
        if not matched:
            print(f"[SKIP] No matching image for {json_file.relative_to(dir_path)}")
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

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="Directory to process")
    parser.add_argument("-r", "--recursive", action="store_true", help="Process subdirectories recursively")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be written without modifying files")
    args = parser.parse_args()

    directory = args.directory
    if not os.path.isdir(directory):
        print(f"Error: {directory} is not a directory")
        sys.exit(1)

    results = process_directory(directory, recursive=args.recursive, dry_run=args.dry_run)
    total_written = sum(len(r["written"]) for r in results)
    total_skipped = sum(len(r["skipped"]) for r in results)
    print(f"\nDone: {len(results)} files processed, {total_written} tags written, {total_skipped} tags skipped")


if __name__ == "__main__":
    main()
