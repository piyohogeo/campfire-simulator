from __future__ import annotations

import unittest

from phase6io_executable_identity import normalize_path_text, same_file


class Phase6IoPathIdentityTests(unittest.TestCase):
    def test_extended_prefix_and_case_normalize(self):
        plain = r"C:\Example\Kit.exe"
        self.assertEqual(normalize_path_text(plain), normalize_path_text(r"\\?\c:\EXAMPLE\kit.exe"))

    def test_same_file_requires_all_canonical_fields(self):
        value = {"canonical_path": "x", "volume_serial": 1, "file_index": 2, "file_size_bytes": 3, "sha256": "A"}
        self.assertTrue(same_file(value, dict(value)))
        changed = dict(value); changed["file_index"] = 4
        self.assertFalse(same_file(value, changed))


if __name__ == "__main__":
    unittest.main()
