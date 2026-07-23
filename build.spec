# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for fixgpto."""

block_cipher = None

a = Analysis(
    ['exif.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('bundled_exiftool/exiftool', 'bundled_exiftool'),
        ('bundled_exiftool/lib', 'bundled_exiftool/lib'),
        ('bundled_exiftool/config_files', 'bundled_exiftool/config_files'),
        ('bundled_exiftool/fmt_files', 'bundled_exiftool/fmt_files'),
        ('bundled_exiftool/arg_files', 'bundled_exiftool/arg_files'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['runtime_hook.py'],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='gphoto_takeout_meta_fix',
    onefile=True,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
