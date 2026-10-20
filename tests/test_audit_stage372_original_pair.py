#!/usr/bin/env python3
"""Synthetic fail-closed Stage372 replay controls (not new NeXium runs)."""
import copy
import hashlib
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audit_stage372_original_pair as a


def chunk(kind, contents):
    return struct.pack(">I", len(contents)) + kind + contents + struct.pack(">I", zlib.crc32(kind + contents))


def png(tag):
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 1280, 720, 8, 2, 0, 0, 0)) +
            chunk(b"tEXt", b"tag\x00" + tag.encode("ascii")) +
            chunk(b"IDAT", zlib.compress((b"\x00" + b"\x00" * (1280 * 3)) * 720)) +
            chunk(b"IEND", b""))


def source_csv(kind, tag):
    rows = {
        "reason": [1, 7, 1, 1, 1, 2235 if tag == "a" else 2672,
                   2235 if tag == "a" else 2672, 0],
        "result": [1, 1, 0, 7],
        "descriptor": [1, 1, 0, 1, 1, 1, 7, 1],
    }[kind]
    return ("scope,value\n" + "".join(f"{key},{value}\n" for key, value in zip(a.LABELS[kind], rows))).encode()


def fixture(root):
    archive = root / "original"
    archive.mkdir()
    source_sha, optical_sha, caps = {}, {}, []
    for tag, dwell in (("a", 6), ("b", 12)):
        d = archive / "stage371-originals" / tag
        d.mkdir(parents=True)
        digests = {}
        for kind, name in a.SOURCE_FILES.items():
            raw = source_csv(kind, tag)
            (d / name).write_bytes(raw)
            digests[kind] = hashlib.sha256(raw).hexdigest()
        source_sha[tag] = digests
        original_png = png(tag)
        (d / "scene-optical-trace.png").write_bytes(original_png)
        optical_sha[tag] = hashlib.sha256(original_png).hexdigest()
        optional = {}
        for name in a.OPTIONAL:
            raw = b"scope,value\nsoftware_only,1\n"
            (d / name).write_bytes(raw)
            optional[name] = {"present": True, "parsed": False,
                              "sha256": hashlib.sha256(raw).hexdigest()}
        caps.append({
            "capture_tag": tag, "exit_dwell_seconds": dwell,
            "guest_source_run_id": a.RUN_ID,
            "source_guest_sd_root": f"/tmp/vh-nexium-stage266-{a.RUN_ID}-{tag}",
            "source_guest_csv_sha256": digests,
            "optional_original_telemetry": optional,
            "original_optical_frame_sha256": optical_sha[tag],
            "source_guest_reason_code": 7, "original_service_result": 0,
            "reported_return_count": 1,
            "reported_pointer_present": True,
            "reported_pointer_matches_submitted": True,
            "optical_content_independently_decoded": False,
            "original_guest_speaker_audio_observed": False,
            "supplemental_telemetry_interpreted_as_exit_queue": False,
        })
    report = {
        "schema": "vh-stage371-two-isolated-neXium-exit-sessions/v1",
        "result": "STAGE371_TWO_SEPARATE_GUEST_WAIT_TUPLES_FROM_SAME_NRO_RECORDED",
        "source_git_sha": a.MERGE_SHA,
        "source_run_id": a.RUN_ID,
        "source_run_attempt": 1,
        "single_verified_nro_sha256": a.NRO_SHA,
        "two_isolated_original_guest_roots": True,
        "two_original_guest_source_families_reopened": True,
        "old_0xEA01_root_cause_proven": False,
        "two_dwell_observations_are_not_a_controlled_causal_pair": True,
        "direct_exit_queue_depth_measured": False,
        "physical_nintendo_switch_audio_tested": False,
        "captures": caps,
    }
    preflight = {
        "result": "SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED",
        "git_sha": a.MERGE_SHA,
        "run_id": a.RUN_ID,
        "run_attempt": 1,
        "nro_sha256": a.NRO_SHA,
        "nro_bytes": 299064,
        "hardware_status": "HARDWARE NOT TESTED",
    }
    (archive / "stage371-two-authentic-guest-exits.json").write_text(json.dumps(report))
    (archive / "stage371-nro-preflight.json").write_text(json.dumps(preflight))
    run = {"id": a.RUN_ID, "status": "completed", "conclusion": "success",
           "event": "pull_request", "repository": {"full_name": a.REPO},
           "head_sha": a.HEAD_SHA, "run_attempt": 1}
    jobs = {"jobs": [
        {"name": name, "run_id": a.RUN_ID, "status": "completed", "conclusion": "success",
         "steps": [{"name": step, "conclusion": "success"} for step in a.REQUIRED_STEPS]}
        for name in (
            "Validate Stage371 isolated-source invariants before building NRO",
            "Build one original libnx NRO without SDL2",
            "Run two separate NeXium guest exits and audit original CSV files",
        )
    ]}
    artifact = {"id": a.ARTIFACT_ID, "name": a.ARTIFACT_NAME,
                "expired": False, "size_in_bytes": 101329, "digest": a.ARCHIVE_DIGEST,
                "workflow_run": {"id": a.RUN_ID, "head_sha": a.HEAD_SHA}}
    merge = {"sha": a.MERGE_SHA,
             "parents": [{"sha": "61143dcf3517f1f3ea60bcc5acb8aa9c803ede3c"},
                         {"sha": a.HEAD_SHA}]}
    return archive, run, jobs, artifact, merge, source_sha, optical_sha


class Stage372Tests(unittest.TestCase):
    def setUp(self):
        self.hold = tempfile.TemporaryDirectory()
        self.addCleanup(self.hold.cleanup)
        self.root = Path(self.hold.name)
        self.args = fixture(self.root)

    def verify(self, **overrides):
        values = dict(zip(("archive", "run", "jobs", "artifact", "merge",
                           "source_sha", "optical_sha"), self.args))
        values.update(overrides)
        return a.verify(**values)

    def test_two_original_synthetic_records_and_noncausal_scope(self):
        outcome = self.verify()
        self.assertEqual(outcome["result"], a.VERDICT)
        self.assertEqual([c["software_wait_result"] for c in outcome["original_runs_replayed"]], [0, 0])
        self.assertEqual([c["released_descriptors"] for c in outcome["original_runs_replayed"]], [1, 1])
        self.assertFalse(outcome["physical_switch_speaker_audio_tested"])
        self.assertFalse(outcome["historical_0xEA01_root_cause_proven"])

    def test_mismatched_github_run_and_artifact_identity_rejected(self):
        for key, replacement in (("status", "queued"), ("conclusion", "failure"),
                                 ("head_sha", "0" * 40), ("run_attempt", 2)):
            run = copy.deepcopy(self.args[1]); run[key] = replacement
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.verify(run=run)
        for key, replacement in (("id", 0), ("digest", "sha256:" + "0" * 64),
                                 ("name", "forged"), ("expired", True)):
            artifact = copy.deepcopy(self.args[3]); artifact[key] = replacement
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.verify(artifact=artifact)

    def test_reordered_merge_parents_and_failed_original_step_rejected(self):
        merge = copy.deepcopy(self.args[4]); merge["parents"].reverse()
        with self.assertRaises(ValueError): self.verify(merge=merge)
        jobs = copy.deepcopy(self.args[2]); jobs["jobs"][2]["steps"][1]["conclusion"] = "failure"
        with self.assertRaises(ValueError): self.verify(jobs=jobs)

    def test_original_csv_corruption_and_duplicate_family_rejected(self):
        root = self.args[0] / "stage371-originals" / "b"
        csv = root / a.SOURCE_FILES["descriptor"]
        blob = csv.read_bytes()
        csv.write_bytes(blob.replace(b"released_count_reported,1", b"released_count_reported,0"))
        with self.assertRaises(ValueError): self.verify()
        csv.write_bytes(blob)
        (root / "audio-exit-tail-reason-001.csv").write_bytes(b"fake")
        with self.assertRaises(ValueError): self.verify()

    def test_original_optical_crc_and_source_hash_rejected(self):
        image = self.args[0] / "stage371-originals" / "a" / "scene-optical-trace.png"
        orig = image.read_bytes()
        image.write_bytes(orig[:-12])
        with self.assertRaises(ValueError): self.verify()
        image.write_bytes(orig)
        pins = copy.deepcopy(self.args[6]); pins["a"] = "0" * 64
        with self.assertRaises(ValueError): self.verify(optical_sha=pins)

    def test_forged_original_report_and_preflight_rejected(self):
        archive = self.args[0]
        path = archive / "stage371-two-authentic-guest-exits.json"
        original = path.read_text(); data = json.loads(original)
        data["captures"][1]["original_service_result"] = 0xEA01
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError): self.verify()
        path.write_text(original)
        preflight = archive / "stage371-nro-preflight.json"
        data = json.loads(preflight.read_text()); data["nro_sha256"] = "0" * 64
        preflight.write_text(json.dumps(data))
        with self.assertRaises(ValueError): self.verify()


if __name__ == "__main__":
    unittest.main()
