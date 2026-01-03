import sys
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from etl_core.database.client import DatabaseClient


class FakeCursor:
    def __init__(self, rows: List[Dict[str, Any]]):
        self._rows = rows
        self.closed = False

    def execute(self, sql, params=None):
        # simulate simple behavior, nothing to do
        pass

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True


class FakeConn:
    def __init__(self, rows: List[Dict[str, Any]]):
        self._rows = rows
        self.autocommit = False
        self.closed = False
        self.last_cursor_factory = None

    def cursor(self, cursor_factory=None):
        # record the provided cursor_factory for inspection in tests
        self.last_cursor_factory = cursor_factory
        # ignore cursor_factory in tests for returning a cursor object
        return FakeCursor(self._rows)

    def close(self):
        self.closed = True


class DatabaseClientTests(unittest.TestCase):
    def test_execute_query_returns_rows(self):
        rows = [{"a": 1}, {"a": 2}]
        fake_conn = FakeConn(rows)
        client = DatabaseClient(connection=fake_conn)
        result = client.execute_query("select 1", [])
        self.assertEqual(result, rows)

    def test_close_closes_connection(self):
        rows = []
        fake_conn = FakeConn(rows)
        client = DatabaseClient(connection=fake_conn)
        client.close()
        self.assertTrue(fake_conn.closed)

    def test_execute_query_uses_cursor_factory(self):
        # Inject a fake psycopg2.extras module so the import inside execute_query succeeds
        rows = [{"x": "y"}]
        fake_conn = FakeConn(rows)
        client = DatabaseClient(connection=fake_conn)

        fake_extras = MagicMock()
        fake_extras.RealDictCursor = lambda *a, **k: object()

        with patch.dict(sys.modules, {"psycopg2": MagicMock(), "psycopg2.extras": fake_extras}):
            result = client.execute_query("select x", [])

        self.assertEqual(result, rows)
        # ensure the cursor_factory was passed through
        self.assertIsNotNone(fake_conn.last_cursor_factory)

    def test_missing_psycopg2_raises_runtime_error(self):
        # Simulate missing psycopg2 by patching _ensure_connection to raise RuntimeError
        client = DatabaseClient(connection=None)
        with patch.object(DatabaseClient, '_ensure_connection', side_effect=RuntimeError("psycopg2 is required")):
            with self.assertRaises(RuntimeError):
                client.execute_query("select 1")


if __name__ == "__main__":
    unittest.main()
