"""Negative controls for the stage-270 multi-run NeXium audit."""
import csv
import hashlib
import io
import json
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_nexium_audout_queue import HEADER, parse_telemetry
from audit_nexium_audout_repeatability import MEMBERS, compare, RepeatabilityError

SAME_NRO = "a5" * 32


def fixture(path: Path, run_id: int, *, samples: int = 36, nro: str = SAME_NRO,
            corrupt: str = ""):
    windows = []
    for second in range(53):
        # Number of observations at multiples of 16 across the entire run.
        probe = ((second+1)*samples+15)//16 - (second*samples+15)//16
        windows.append(["SECOND", second, samples, samples, 0, 52000,
                        probe, 0, 0, 0, 0, 0])
    attempts = 53*samples
    probes = (attempts+15)//16
    total = ["TOTAL", -1, attempts, attempts, 0, 52000,
             probes, 0, 0, 0, 0, 0]
    text = io.StringIO(newline="")
    csv.writer(text, lineterminator="\n").writerows([HEADER,total,*windows])
    csv_raw = text.getvalue().encode("ascii")
    metrics = parse_telemetry(csv_raw)
    digest = hashlib.sha256(csv_raw).hexdigest()
    receipt = (f"export_status=0\npath_present=1\n"
               f"file_size={len(csv_raw)}\n").encode("ascii")
    queue = {
        **metrics,
        "sd_binding": "GUEST_ORIGINAL_AND_COPY_BYTE_IDENTICAL",
        "sd_original_sha256": digest, "sd_copy_sha256": digest,
        "sd_copy_bytes": len(csv_raw),
        "guest_export_receipt": "GUEST_WRITER_SUCCEEDED_AND_STAT_VISIBLE",
        "guest_export_receipt_sha256": hashlib.sha256(receipt).hexdigest(),
    }
    build = {
        "result": "SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED",
        "nro_sha256": nro, "git_sha": "f"*40,
        "run_id": run_id, "run_attempt": 1,
    }
    scene = {
        "result": "TEN_GUEST_SCENE_TRANSITIONS_DUAL_TRANSPORT_VERIFIED",
        "guest_nro_sha256": nro, "guest_event_rows": 53,
        "hardware_status": "HARDWARE NOT TESTED",
        "pcm_duration_seconds": 61.0,
    }
    files = {
        MEMBERS["build"]: json.dumps(build).encode("ascii"),
        MEMBERS["scene"]: json.dumps(scene).encode("ascii"),
        MEMBERS["queue"]: json.dumps(queue).encode("ascii"),
        MEMBERS["csv"]: csv_raw,
        MEMBERS["receipt"]: receipt,
    }
    if corrupt == "csv":
        files[MEMBERS["csv"]] += b"alter"
    elif corrupt == "receipt":
        files[MEMBERS["receipt"]] = b"export_status=0\npath_present=0\nfile_size=0\n"
    elif corrupt == "scene":
        scene["guest_nro_sha256"] = "b5"*32
        files[MEMBERS["scene"]] = json.dumps(scene).encode("ascii")
    elif corrupt == "queue":
        queue["failed_attempts"] = 1
        files[MEMBERS["queue"]] = json.dumps(queue).encode("ascii")
    elif corrupt == "duplicate_json":
        files[MEMBERS["scene"]] = (
            json.dumps(scene)[:-1] + ',"guest_event_rows":53}'
        ).encode("ascii")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
        if corrupt == "duplicate_file":
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr(MEMBERS["build"], files[MEMBERS["build"]])


class TestRepeatability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.a = Path(self.tmp.name) / "run1.zip"
        self.b = Path(self.tmp.name) / "run2.zip"

    def test_two_independent_runs_of_same_nro(self):
        fixture(self.a, 101)
        fixture(self.b, 102, samples=37)
        report = compare([self.a, self.b])
        self.assertEqual(report["result"],
                         "SAME_NRO_GUEST_AUDOUT_REPEATABILITY_VERIFIED")
        self.assertEqual(report["attempts_min"], 1908)
        self.assertEqual(report["attempts_max"], 1961)
        self.assertEqual(report["nro_sha256"], SAME_NRO)
        self.assertFalse(report["physical_switch_tested"])
        self.assertFalse(report["audible_underruns_measured"])
        self.assertFalse(report["independent_original_sd_reopened"])

    def test_require_different_runs(self):
        fixture(self.a, 101)
        fixture(self.b, 101)
        with self.assertRaises(RepeatabilityError):
            compare([self.a,self.b])
        with self.assertRaises(RepeatabilityError):
            compare([self.a])

    def test_reject_different_binary(self):
        fixture(self.a, 101)
        fixture(self.b, 102, nro="b5"*32)
        with self.assertRaises(RepeatabilityError):
            compare([self.a,self.b])

    def test_reject_noncomparable_attempt_counts(self):
        fixture(self.a, 101)
        fixture(self.b, 102, samples=50)
        with self.assertRaises(RepeatabilityError):
            compare([self.a,self.b])

    def test_reject_corrupted_artifacts(self):
        fixture(self.a, 101)
        for corruption in (
            "csv", "receipt", "scene", "queue", "duplicate_json",
            "duplicate_file"
        ):
            with self.subTest(corruption=corruption):
                fixture(self.b, 102, corrupt=corruption)
                with self.assertRaises(RepeatabilityError):
                    compare([self.a,self.b])


if __name__ == "__main__":
    unittest.main()
