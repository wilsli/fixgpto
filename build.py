#!/usr/bin/env python3
"""Build script for fixgpto single-file executable."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def check_prerequisites():
    """Check if PyInstaller is installed."""
    try:
        import PyInstaller
        print(f"✓ PyInstaller {PyInstaller.__version__} found")
    except ImportError:
        print("✗ PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("✓ PyInstaller installed")


def build_executable():
    """Build the executable using PyInstaller."""
    project_root = Path(__file__).parent
    
    # Clean previous build
    for dir_name in ['build', 'dist']:
        dir_path = project_root / dir_name
        if dir_path.exists():
            print(f"Cleaning {dir_name}/...")
            shutil.rmtree(dir_path)
    
    # Remove old executable
    dist_dir = project_root / 'dist'
    if dist_dir.exists():
        for item in dist_dir.iterdir():
            if item.is_file():
                print(f"Removing old executable: {item.name}")
                item.unlink()
    
    # Run PyInstaller via spec file
    print("\nBuilding executable...")
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--noconfirm',
        'build.spec'
    ]
    
    subprocess.check_call(cmd, cwd=str(project_root))
    
    # Verify output
    exe_path = project_root / 'dist' / 'fixgpto'
    if sys.platform == 'win32':
        exe_path = project_root / 'dist' / 'fixgpto.exe'
    
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n✓ Build successful!")
        print(f"  Executable: {exe_path}")
        print(f"  Size: {size_mb:.1f} MB")
        return True
    else:
        print("\n✗ Build failed - executable not found")
        return False


def test_executable():
    """Test the built executable with sample data."""
    project_root = Path(__file__).parent
    exe_path = project_root / 'dist' / 'fixgpto'
    
    if sys.platform == 'win32':
        exe_path = project_root / 'dist' / 'fixgpto.exe'
    
    if not exe_path.exists():
        print("Executable not found. Run build first.")
        return False
    
    print(f"\nTesting executable with sample data...")
    cmd = [str(exe_path), str(project_root / 'sample')]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        print(result.stdout)
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print("Test timed out")
        return False


if __name__ == '__main__':
    print("=" * 60)
    print("fixgpto Build Script")
    print("=" * 60)
    
    check_prerequisites()
    
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        success = test_executable()
    elif len(sys.argv) > 1 and sys.argv[1] == 'build':
        success = build_executable()
    else:
        print("\nBuilding and testing...")
        success = build_executable()
        if success:
            test_executable()
    
    sys.exit(0 if success else 1)
