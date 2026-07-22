#!/usr/bin/env python3
"""ExifTool wrapper for HEIC/MOV/MP4 metadata operations."""

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def get_exiftool_path():
    """Find the bundled exiftool executable."""
    candidates = [
        Path(__file__).parent / "bundled_exiftool" / "exiftool",
        Path(__file__).parent / "exiftool",
        shutil.which("exiftool"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return str(path)
    return None


def run_exiftool(args, input_data=None):
    """Run exiftool with the given arguments and return stdout."""
    exiftool_path = get_exiftool_path()
    if not exiftool_path:
        raise RuntimeError(
            "exiftool not found. Bundle it under bundled_exiftool/ or install it."
        )

    cmd = [exiftool_path] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            input=input_data,
        )
        if result.returncode != 0 and not result.stdout.strip():
            raise RuntimeError(f"exiftool error: {result.stderr.strip()}")
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise RuntimeError("exiftool command timed out")


def read_metadata(image_path):
    """Read all metadata from a file using exiftool in JSON format."""
    output = run_exiftool(["-j", "-all", str(image_path)])
    if not output:
        return {}
    data = json.loads(output)
    if isinstance(data, list) and len(data) > 0:
        return data[0]
    return data


def has_tag(metadata, *tag_names):
    """Check if any of the given tag names exist in metadata (case-insensitive)."""
    lower_tags = {t.lower(): t for t in tag_names}
    for key in metadata:
        if key.lower() in lower_tags:
            return lower_tags[key.lower()]
    return None


def timestamp_to_datetime(timestamp_str):
    """Convert Unix timestamp to exiftool datetime format."""
    ts = int(timestamp_str)
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y:%m:%d %H:%M:%S")


def decimal_to_dms(value):
    """Convert decimal degrees to [seconds, minutes, degrees] list."""
    abs_value = abs(value)
    degrees = int(abs_value)
    minutes_full = (abs_value - degrees) * 60
    minutes = int(minutes_full)
    seconds = round((minutes_full - minutes) * 60, 3)
    if seconds >= 60:
        seconds -= 60
        minutes += 1
    return [seconds, minutes, degrees]


def write_metadata(image_path, meta, dry_run=False):
    """Write Google Photos metadata to a file using exiftool.

    For HEIC/HEIF, writes EXIF group tags (DateTimeOriginal, GPSLatitude, etc.).
    For MOV/MP4, writes QuickTime group tags (CreateDate, MediaCreateDate, etc.)
    plus EXIF GPS tags where applicable.
    """
    written = []
    skipped = []
    tags = []

    existing = read_metadata(image_path)

    # --- DateTimeOriginal / DateTimeDigitized ---
    time_source = meta.get("photoTakenTime") or meta.get("creationTime")
    if time_source and "timestamp" in time_source:
        dt_str = timestamp_to_datetime(time_source["timestamp"])

        if has_tag(existing, "DateTimeOriginal"):
            skipped.append("DateTimeOriginal")
        else:
            tags.extend(["-DateTimeOriginal=" + dt_str])
            written.append("DateTimeOriginal=" + dt_str)

        if has_tag(existing, "DateTimeDigitized"):
            skipped.append("DateTimeDigitized")
        else:
            tags.extend(["-DateTimeDigitized=" + dt_str])
            written.append("DateTimeDigitized=" + dt_str)

        # Also set QuickTime creation date for video formats
        if has_tag(existing, "CreateDate"):
            skipped.append("CreateDate")
        else:
            tags.extend(["-CreateDate=" + dt_str])
            written.append("CreateDate=" + dt_str)

        if has_tag(existing, "MediaCreateDate"):
            skipped.append("MediaCreateDate")
        else:
            tags.extend(["-MediaCreateDate=" + dt_str])
            written.append("MediaCreateDate=" + dt_str)

    # --- DateTime (from creationTime) ---
    creation_time = meta.get("creationTime")
    if creation_time and "timestamp" in creation_time:
        dt_str = timestamp_to_datetime(creation_time["timestamp"])

        if has_tag(existing, "DateTime"):
            skipped.append("DateTime")
        else:
            tags.extend(["-DateTime=" + dt_str])
            written.append("DateTime=" + dt_str)

        if has_tag(existing, "ModifyDate"):
            skipped.append("ModifyDate")
        else:
            tags.extend(["-ModifyDate=" + dt_str])
            written.append("ModifyDate=" + dt_str)

        if has_tag(existing, "MediaModifyDate"):
            skipped.append("MediaModifyDate")
        else:
            tags.extend(["-MediaModifyDate=" + dt_str])
            written.append("MediaModifyDate=" + dt_str)

    # --- GPS ---
    geo = meta.get("geoData", {})
    lat = geo.get("latitude")
    lng = geo.get("longitude")
    alt = geo.get("altitude")

    if lat and lat != 0.0:
        if has_tag(existing, "GPSLatitude"):
            skipped.append("GPSLatitude")
        else:
            dms = decimal_to_dms(lat)
            ref = "N" if lat >= 0 else "S"
            tags.extend([f"-GPSLatitudeRef={ref}", f"-GPSLatitude={dms}"])
            written.append(f"GPSLatitude={lat}")

        if has_tag(existing, "GPSLongitude"):
            skipped.append("GPSLongitude")
        else:
            dms = decimal_to_dms(lng)
            ref = "E" if lng >= 0 else "W"
            tags.extend([f"-GPSLongitudeRef={ref}", f"-GPSLongitude={dms}"])
            written.append(f"GPSLongitude={lng}")

    if alt and alt != 0.0:
        if has_tag(existing, "GPSAltitude"):
            skipped.append("GPSAltitude")
        else:
            if alt >= 0:
                tags.extend(["-GPSAltitudeRef=0", f"-GPSAltitude={int(alt * 100)}/100"])
            else:
                tags.extend(["-GPSAltitudeRef=1", f"-GPSAltitude={int(abs(alt) * 100)}/100"])
            written.append(f"GPSAltitude={alt}")

    # --- ImageDescription ---
    description = meta.get("description")
    if description:
        if has_tag(existing, "ImageDescription"):
            skipped.append("ImageDescription")
        else:
            tags.extend(["-ImageDescription=" + description])
            written.append(f"ImageDescription={description}")

    if written and not dry_run:
        run_exiftool(tags + ["-overwrite_original", str(image_path)])

    return written, skipped
