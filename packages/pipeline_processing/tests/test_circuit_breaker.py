import time
import logging
import unittest

from etl_core.support.circuit_breaker import CircuitBreaker


class TestCircuitBreaker(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger("test")
        # reduce verbosity
        self.logger.disabled = True

    def test_record_failure_and_activation_and_cooldown(self):
        cb = CircuitBreaker(max_failures=3, cooldown_seconds=1, logger=self.logger)
        self.assertFalse(cb.is_active())
        cb.record_failure()
        self.assertFalse(cb.is_active())
        cb.record_failure()
        self.assertFalse(cb.is_active())
        cb.record_failure()  # 3rd failure -> activate
        self.assertTrue(cb.is_active())
        # wait past cooldown
        time.sleep(1.2)
        self.assertFalse(cb.is_active())

    def test_record_success_resets(self):
        cb = CircuitBreaker(max_failures=2, cooldown_seconds=10, logger=self.logger)
        cb.record_failure()
        cb.record_failure()
        self.assertTrue(cb.active)
        cb.record_success()
        self.assertFalse(cb.active)
        self.assertEqual(cb.consecutive_failures, 0)


if __name__ == "__main__":
    unittest.main()
