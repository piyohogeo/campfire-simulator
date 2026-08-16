from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from phase6im_process_identity import (
    ProcessIdentityError,
    WindowsProcessApi,
    capture_process_identity,
    combine_filetime,
    produce_helper_report,
)


class Phase6ImIdentityTests(unittest.TestCase):
    def test_real_current_process_handle_is_closed(self):
        api = WindowsProcessApi()
        value = capture_process_identity(os.getpid(), expected_path=Path(r"C:\Python38\python.exe"), api=api)
        self.assertTrue(value["close_handle_success"])
        self.assertEqual(api.tracker()["open_handle_residual_count"], 0)

    def test_producer_repeats_exact_identity(self):
        value = produce_helper_report(attempt_id="unit", pid=os.getpid(), expected_path=Path(r"C:\Python38\python.exe"))
        self.assertTrue(value["identity_stable"])
        self.assertEqual(value["handle_tracker_final"]["open_calls"], 2)
        self.assertEqual(value["handle_tracker_final"]["close_calls"], 2)

    def test_filetime_combination_is_64_bit(self):
        self.assertEqual(combine_filetime(0x12345678, 0x9ABCDEF0), 0x123456789ABCDEF0)

    def test_pid_zero_is_rejected(self):
        with self.assertRaisesRegex(ProcessIdentityError, "pid_invalid"):
            capture_process_identity(0)


if __name__ == "__main__":
    unittest.main()

