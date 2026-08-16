from __future__ import annotations

import unittest

from phase6in_post_shutdown_boundary import NORMAL_EXIT_MAX_SECONDS, SCHEDULE_SECONDS, classify


class Phase6InBoundaryTests(unittest.TestCase):
    def test_schedule_is_fixed_and_bounded(self):
        self.assertEqual(SCHEDULE_SECONDS, (0.0, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0))

    def test_normal_and_delayed_are_separate(self):
        common = dict(operation_valid=True, monitor_valid=True, identity_reuse=False, exit_observed=True,
                      exit_code=0, post_shutdown_exception=False, resource_pass=True,
                      cleanup_pass=True, cleanup_assisted=False)
        self.assertEqual(classify(exit_seconds=NORMAL_EXIT_MAX_SECONDS, **common)["lifecycle"], "normal_exit")
        self.assertEqual(classify(exit_seconds=NORMAL_EXIT_MAX_SECONDS + 0.01, **common)["lifecycle"], "delayed_exit")

    def test_monitor_can_qualify_an_anomaly(self):
        value = classify(operation_valid=True, monitor_valid=True, identity_reuse=False,
                         exit_observed=False, exit_code=None, exit_seconds=None,
                         post_shutdown_exception=False, resource_pass=True,
                         cleanup_pass=True, cleanup_assisted=True)
        self.assertTrue(value["monitor_boundary_qualified"])
        self.assertEqual(value["lifecycle"], "post_shutdown_timeout")


if __name__ == "__main__":
    unittest.main()
