# Fix: FileCreateDate error on Linux

## Problem
exiftool throws "Warning: This tag is Windows/Mac only" when trying to set `FileCreateDate` on Linux, causing the entire metadata write to fail with `RuntimeError`.

## Root Cause
`exiftool_wrapper.py:172` unconditionally adds `-FileCreateDate=<value>` to exiftool tags, but this tag is only supported on Windows and macOS.

## Plan
1. In `exiftool_wrapper.py`, add `import platform` at the top
2. Wrap the FileCreateDate block (lines 165-173) in a check: only write if `platform.system()` is 'Windows' or 'Darwin'
3. Same for `write_file_created_date()` function (line 223+) — return early as skipped on non-Windows/Mac platforms
