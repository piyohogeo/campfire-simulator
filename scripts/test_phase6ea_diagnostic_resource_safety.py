from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from ctypes import wintypes
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
CAPTURE = ROOT / "scripts" / "capture_phase6ea_hang_diagnostics.ps1"
WCT = ROOT / "scripts" / "phase6ea_wct_helper.py"
FIXTURE = ROOT / "scripts" / "phase6ea_resource_safety_fixture.ps1"
COMMON = ROOT / "scripts" / "phase6ea_diagnostic_common.ps1"


def _args(script: Path, *arguments: object) -> list[str]:
    return [str(POWERSHELL), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), *(str(item) for item in arguments)]


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    subprocess.run(
        ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=10,
    )
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _run(
    arguments: list[str],
    *,
    timeout: float = 30,
    check: bool = False,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        arguments,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)
        raise
    completed = subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)
    if check:
        completed.check_returncode()
    return completed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def _private_bytes(pid: int) -> int:
    handle = ctypes.windll.kernel32.OpenProcess(0x1000 | 0x0400, False, pid)
    if not handle:
        return 0
    try:
        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(counters)
        if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return 0
        return int(counters.PrivateUsage)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


class Phase6EaResourceSafety(unittest.TestCase):
    def setUp(self) -> None:
        self._test_started = time.perf_counter()

    def tearDown(self) -> None:
        print(f"TEST_TIMING {self.id()} {time.perf_counter() - self._test_started:.3f}s", file=sys.stderr, flush=True)

    def test_full_128_character_wct_name_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as temp:
            output = Path(temp) / "wct.json"
            markers = Path(temp) / "markers.log"
            _run(
                [
                    sys.executable,
                    str(WCT),
                    "--output-path",
                    str(output),
                    "--object-name-boundary-fixture",
                    "--durable-marker-path",
                    str(markers),
                ],
                check=True,
                timeout=30,
            )
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["length"], 128)
            self.assertEqual(report["value"], "X" * 128)
            self.assertEqual(report["constants"]["object_name_characters"], 128)
            marker_text = markers.read_text(encoding="utf-8")
            self.assertIn("dynamic_add_type_not_used", marker_text)
            self.assertIn("read_bounded_object_name_complete", marker_text)
            self.assertIn("python_process_exit_imminent", marker_text)

    def test_wct_timeout_leaves_no_helper_process(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as temp:
            _run(_args(FIXTURE, "-Mode", "wct_timeout", "-OutputDir", temp), check=True, timeout=30)
            report = json.loads((Path(temp) / "fixture_result.json").read_text(encoding="utf-8"))
            self.assertTrue(report["timed_out"])
            self.assertTrue(report["process_absent"])
            self.assertTrue(Path(report["stdout_path"]).is_file())
            self.assertTrue(Path(report["stderr_path"]).is_file())
            print(
                f"RESOURCE_METRIC wct_timeout_helper_pid={report['pid']} "
                f"process_absent={report['process_absent']}",
                file=sys.stderr,
                flush=True,
            )

    def test_duplicate_capture_is_rejected_and_stale_lock_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as temp:
            root = Path(temp)
            canonical = root / "capture"
            holder_dir = root / "holder"
            holder = subprocess.Popen(_args(FIXTURE, "-Mode", "lock_hold", "-OutputDir", holder_dir, "-CanonicalCapturePath", canonical, "-HoldSeconds", "5"), text=True)
            try:
                for _ in range(50):
                    if (holder_dir / "lock_acquired.txt").is_file():
                        break
                    time.sleep(0.1)
                duplicate = _run(
                    _args(FIXTURE, "-Mode", "lock_once", "-OutputDir", root / "duplicate", "-CanonicalCapturePath", canonical),
                    capture_output=True,
                    timeout=30,
                )
                self.assertNotEqual(duplicate.returncode, 0)
                self.assertIn("Duplicate Phase 6EA capture", duplicate.stderr)
                holder.wait(timeout=30)
            finally:
                _kill_process_tree(holder)

            lock = Path(f"{canonical}.capture.lock")
            lock.write_text(json.dumps({"owner_pid": 2147483647, "owner_start_time_utc": "2000-01-01T00:00:00Z"}), encoding="utf-8")
            _run(_args(FIXTURE, "-Mode", "lock_once", "-OutputDir", root / "stale", "-CanonicalCapturePath", canonical), check=True, timeout=30)
            self.assertFalse(lock.exists())

    def test_existing_dump_mode_needs_no_pid_and_preserves_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as temp:
            root = Path(temp)
            dump = root / "existing.dmp"
            dump.write_bytes(b"MDMP" + bytes(range(64)))
            before = _sha256(dump)
            output = root / "metadata"
            _run(_args(CAPTURE, "-ExistingDumpPath", dump, "-ExpectedExistingDumpSha256", before, "-OutputDir", output), check=True, timeout=30)
            report = json.loads((output / "hang_diagnostics.json").read_text(encoding="utf-8"))
            self.assertFalse(report["live_process_accessed"])
            self.assertFalse(report["wct_invoked"])
            self.assertFalse(report["stop_process_invoked"])
            self.assertEqual(_sha256(dump), before)

    def test_sparse_hash_has_bounded_private_memory(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as temp:
            root = Path(temp)
            dump = root / "sparse.dmp"
            with dump.open("wb") as stream:
                stream.write(b"MDMP")
                stream.seek(128 * 1024 * 1024 - 1)
                stream.write(b"\0")
            process = subprocess.Popen(_args(CAPTURE, "-ExistingDumpPath", dump, "-ComputeExistingDumpHash", "-OutputDir", root / "metadata"))
            peak = 0
            deadline = time.monotonic() + 30
            try:
                while process.poll() is None:
                    if time.monotonic() >= deadline:
                        raise subprocess.TimeoutExpired(process.args, 30)
                    peak = max(peak, _private_bytes(process.pid))
                    time.sleep(0.02)
            finally:
                _kill_process_tree(process)
            self.assertEqual(process.returncode, 0)
            self.assertLess(peak, 256 * 1024 * 1024)
            print(f"RESOURCE_METRIC sparse_hash_peak_private_bytes={peak}", file=sys.stderr, flush=True)
            report = json.loads((root / "metadata" / "hang_diagnostics.json").read_text(encoding="utf-8"))
            self.assertEqual(report["dump"]["hash_buffer_bytes"], 1024 * 1024)

    def test_dump_timeout_removes_partial_and_keeps_completed_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as temp:
            root = Path(temp)
            source = root / "source.dmp"
            source.write_bytes(b"MDMP" + os.urandom(2 * 1024 * 1024))
            final = root / "new.dmp"
            _run(_args(FIXTURE, "-Mode", "dump_timeout", "-OutputDir", root / "guard", "-SourcePath", source, "-FinalDumpPath", final), check=True, timeout=30)
            report = json.loads((root / "guard" / "fixture_result.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertTrue(report["partial_removed"])
            self.assertFalse(final.exists())

            completed = root / "completed.dmp"
            completed.write_bytes(b"MDMP" + b"unchanged")
            before = completed.read_bytes()
            failure = _run(_args(CAPTURE, "-ExistingDumpPath", completed, "-ExpectedExistingDumpSha256", "0" * 64, "-OutputDir", root / "bad-metadata"), timeout=30)
            self.assertNotEqual(failure.returncode, 0)
            self.assertEqual(completed.read_bytes(), before)

    def test_large_file_and_external_output_contract_is_streaming(self) -> None:
        capture = CAPTURE.read_text(encoding="utf-8")
        common = COMMON.read_text(encoding="utf-8")
        combined = capture + common
        self.assertNotIn("ReadAllBytes", combined)
        self.assertNotIn("ReadAllText", combined)
        self.assertNotIn("ReadToEnd", combined)
        self.assertIn("RedirectStandardOutput", common)
        self.assertIn("RedirectStandardError", common)
        self.assertIn("FileOptions.SequentialScan", common)
        self.assertIn("$nativeProcessHandle = $process.Handle", common)
        self.assertIn("ReadExitCode", common)


if __name__ == "__main__":
    unittest.main()
