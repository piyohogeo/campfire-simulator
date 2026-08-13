import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

try:
    from scripts.phase6fk_pointer_evidence import pointer_evidence_from_boundary
except ModuleNotFoundError:
    from phase6fk_pointer_evidence import pointer_evidence_from_boundary


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts" / "phase6fk_pointer_complete_contract.json"


def metadata(value):
    interface = value.__array_interface__
    return {
        "identity": id(value),
        "shape": list(value.shape),
        "dtype": str(value.dtype),
        "strides": list(value.strides),
        "size": int(value.size),
        "nbytes": int(value.nbytes),
        "data_pointer": interface["data"][0],
    }


def boundary(source, converted, *, source_pointer=None, converted_pointer=None):
    source_meta = metadata(source)
    converted_meta = metadata(converted)
    if source_pointer is None:
        source_pointer = source_meta["data_pointer"]
    if converted_pointer is None:
        converted_pointer = converted_meta["data_pointer"]
    return {
        "fuel_source": source_meta,
        "fuel_array": converted_meta,
        "observable_copy_contract": {
            "source_data_pointer": source_pointer,
            "converted_data_pointer": converted_pointer,
            "same_data_pointer": source_pointer == converted_pointer,
            "same_identity": source is converted,
            "shares_memory": bool(np.shares_memory(source, converted)),
        },
        "weak_reference_alive_after_scope_count": 0,
        "converted_weak_reference_alive_immediately_after_release": False,
    }


class Phase6FkPointerComplete(unittest.TestCase):
    def test_positive_same_object_pointer_contract(self):
        source = np.arange(32, dtype=np.uint32)
        converted = np.asarray(source)
        evidence = pointer_evidence_from_boundary(boundary(source, converted))
        self.assertTrue(evidence["complete"])
        self.assertGreater(evidence["source_data_pointer"], 0)
        self.assertEqual(evidence["source_data_pointer"], evidence["converted_data_pointer"])

    def test_independent_copy_pointer_mismatch_fails(self):
        source = np.arange(32, dtype=np.uint32)
        converted = source.copy()
        evidence = pointer_evidence_from_boundary(boundary(source, converted))
        self.assertFalse(evidence["complete"])
        self.assertIn("source_converted_data_pointer_mismatch", evidence["failures"])

    def test_missing_zero_negative_and_wrong_type_pointers_fail(self):
        source = np.arange(8, dtype=np.uint32)
        for field, failure in (
            ("source_data_pointer", "source_data_pointer_not_positive_integer"),
            ("converted_data_pointer", "converted_data_pointer_not_positive_integer"),
        ):
            for bad in (None, 0, -1, "123", True, 1.5):
                with self.subTest(field=field, pointer=bad):
                    item = boundary(source, source)
                    item["observable_copy_contract"][field] = bad
                    evidence = pointer_evidence_from_boundary(item)
                    self.assertFalse(evidence["complete"])
                    self.assertIn(failure, evidence["failures"])

    def test_identity_or_shares_memory_without_pointers_is_insufficient(self):
        source = np.arange(8, dtype=np.uint32)
        item = boundary(source, source)
        item["observable_copy_contract"].pop("source_data_pointer")
        item["observable_copy_contract"].pop("converted_data_pointer")
        evidence = pointer_evidence_from_boundary(item)
        self.assertTrue(evidence["same_python_identity"])
        self.assertTrue(evidence["shares_memory"])
        self.assertFalse(evidence["complete"])

    def test_raw_boundary_propagates_to_final_summary(self):
        source = np.arange(8, dtype=np.uint32)
        evidence = pointer_evidence_from_boundary(boundary(source, source))
        serialized = json.loads(json.dumps(evidence))
        self.assertEqual(serialized["source_data_pointer"], source.__array_interface__["data"][0])
        self.assertEqual(serialized["converted_data_pointer"], source.__array_interface__["data"][0])
        probe = (ROOT / "scripts" / "probe_phase6ep_point_collision_coexistence.py").read_text(encoding="utf-8")
        self.assertIn('source_data_pointer=source_metadata["data_pointer"]', probe)
        self.assertIn('converted_data_pointer=fuel_array["data_pointer"]', probe)

    def test_contract_and_runner_are_fail_closed(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["balanced_order"], [
            ["A_control", "B_readback", "C_fuel_alias"],
            ["B_readback", "C_fuel_alias", "A_control"],
            ["C_fuel_alias", "A_control", "B_readback"],
        ])
        self.assertEqual(contract["population"]["maximum_launches"], 11)
        self.assertEqual(contract["population"]["startup_prerequisite_replacement_budget"], 2)
        self.assertIn("pointer_evidence_failure", contract["nonreplaceable"])
        analyzer = (ROOT / "scripts" / "analyze_phase6fj_balanced_single_readback.py").read_text(encoding="utf-8")
        runner = (ROOT / "scripts" / "run_phase6fj_balanced_single_readback.ps1").read_text(encoding="utf-8")
        self.assertIn('operation.extend(f"c_pointer:{failure}"', analyzer)
        self.assertIn('$classification -eq "startup_prerequisite_failure"', runner)
        self.assertIn('captured nonreplaceable $classification', runner)


if __name__ == "__main__":
    unittest.main()
