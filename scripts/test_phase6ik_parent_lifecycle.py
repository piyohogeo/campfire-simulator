from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from phase6ik_parent_lifecycle_boundary import ORDER, append_marker, produce_runner_evidence, read_jsonl, validate_markers, validate_runner_evidence


class Phase6IkBoundaryTest(unittest.TestCase):
    def test_complete_marker_sequence_and_runner_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "markers.jsonl"
            actors = {step: ("outer_guard" if step.startswith("outer_guard") or step.startswith("guard_result") or step.startswith("canonical_") else "child_kit" if step in ("kit_app_ready","operation_complete","shutdown_complete") else "parent_powershell") for step in ORDER}
            identities = {"outer_guard":(1,1.0),"parent_powershell":(2,2.0),"child_kit":(3,3.0)}
            elapsed = {key:0.0 for key in identities}
            for step in ORDER:
                actor=actors[step]; elapsed[actor]+=1
                append_marker(path,"attempt",step,actor=actor,pid=identities[actor][0],creation_time_utc_epoch=identities[actor][1],monotonic_elapsed_seconds=elapsed[actor])
            rows=read_jsonl(path)
            self.assertTrue(validate_markers(rows,"attempt")["accepted"])
            runner=produce_runner_evidence(attempt_id="attempt",parent_identity={"pid":2,"creation_time_utc_epoch":2.0},child_identity={"pid":3,"creation_time_utc_epoch":3.0},process_exit_code=0,shutdown_monitor={})
            self.assertTrue(validate_runner_evidence(runner,rows,"attempt")["accepted"])
            changed=copy.deepcopy(rows); changed[-1]["pid"]=99
            self.assertFalse(validate_markers(changed,"attempt")["accepted"])


if __name__ == "__main__":
    unittest.main()
