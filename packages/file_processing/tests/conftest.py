"""Pytest configuration to expose repository modules on sys.path."""
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[3]
PACKAGES_DIR = BASE_DIR / "packages"
SRC_ROOT = Path(__file__).resolve().parents[1] / "src"

for path in (SRC_ROOT, PACKAGES_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
