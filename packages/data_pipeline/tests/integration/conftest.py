"""
Conftest for integration tests: automatically mark all tests under this package as integration tests.
"""

import pytest

pytestmark = pytest.mark.integration
