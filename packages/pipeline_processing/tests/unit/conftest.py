import sys
from unittest.mock import MagicMock

# Create a shared mock for botocore.exceptions
mock_botocore_exceptions = MagicMock()


class MockClientError(Exception):
    def __init__(self, response, operation_name):
        self.response = response
        self.operation_name = operation_name


class MockNoCredentialsError(Exception):
    pass


mock_botocore_exceptions.ClientError = MockClientError
mock_botocore_exceptions.NoCredentialsError = MockNoCredentialsError


def setup_mocks():
    for module in ['django', 'django.db', 'django.conf', 'django_core', 'django_core.settings',
                   'django_core.settings.base', 'botocore', 'boto3']:
        if module not in sys.modules:
            sys.modules[module] = MagicMock()

    sys.modules['botocore.exceptions'] = mock_botocore_exceptions
