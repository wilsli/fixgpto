#!/usr/bin/env python3
"""Runtime hook: ensure bundled exiftool has execute permission."""

import os
import stat


def _fix_exiftool_permissions():
    # Find the extracted bundle root
    if hasattr(__import__('sys'), '_MEIPASS'):
        base = __import__('sys')._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    exiftool_path = os.path.join(base, 'bundled_exiftool', 'exiftool')

    if os.path.exists(exiftool_path):
        try:
            current = os.stat(exiftool_path).st_mode
            os.chmod(exiftool_path, current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception as e:
            pass

    # Also fix lib/Image/ExifTool/exiftool.pl if present
    pl_path = os.path.join(base, 'bundled_exiftool', 'lib', 'Image', 'ExifTool', 'exiftool.pl')
    if os.path.exists(pl_path):
        try:
            current = os.stat(pl_path).st_mode
            os.chmod(pl_path, current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception as e:
            pass


_fix_exiftool_permissions()
