"""Test package initializer.

Ensure the repository root is on sys.path so test modules can import the application
packages (for example, `service`), regardless of the current working directory used by
test runners or IDE test runners.
"""

import os
import sys

# Insert repository root (parent of this tests package) at the front of sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
