"""Pytest configuration for the test suite.

Ensure the repository root is on sys.path so application packages (like `service`)
can be imported regardless of how pytest is invoked by IDEs or CI.
"""

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
