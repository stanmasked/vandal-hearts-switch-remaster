#!/usr/bin/env python3
"""Adversarial Stage367 artifact metadata, job and log validation."""
from __future__ import annotations
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audit_stage367_sdl2_original_artifact as m


def fixture(root: Path):
    a = root / "source"
    a.mkdir()
    (a / m.RAW).write_text(
        ":: Synchronizing package databases...\n"
        "curl: (22) The requested URL returned error: 403\n"
        "error: failed to synchronize all databases (error invoking external downloader)\n"
    )
    diagnosis = {
        "result": "OPTIONAL_DEPENDENCY_NOT_INSTALLED",
        "failure_code": "EXTERNAL_DEVKITPRO_MIRROR_HTTP_403",
        "package": "switch-sdl2",
        "compile_performed": False,
        "dependency_accepted": False,
        "hardware_status": "HARDWARE NOT TESTED",
        "recommended_action": "Keep this job failed: external package mirror unavailable.",
    }
    (a / m.REPORT).write_text(
        json.dumps(diagnosis) +
        "\n::error title=Optional Switch dependency unavailable::HTTP 403\n")
    meta = {"id": m.ARTIFACT_ID, "name": m.ARTIFACT_NAME,
            "digest": m.ARTIFACT_DIGEST, "expired": False,
            "size_in_bytes": 905,
            "workflow_run": {"id": m.RUN_ID, "head_sha": m.HEAD_SHA,
                             "head_branch": "audio/stage322-rolling-playbuffer-history"}}
    job = {"id": m.JOB_ID, "run_id": m.RUN_ID, "conclusion": "failure",
           "name": "Build and validate Switch SDL2 music audio NRO",
           "steps": [
              {"name": "Install Nintendo Switch SDL2 development libraries",
               "conclusion": "failure"},
              {"name": "Preserve Stage366 SDL2 install evidence even when dependency fails",
               "conclusion": "success"},
              {"name": "Compile and inspect music NRO", "conclusion": "skipped"},
              {"name": "Run synthetic native music tests", "conclusion": "skipped"},
              {"name": "Upload synthetic/local-resource audio NRO",
               "conclusion": "skipped"}]}
    return a, meta, job


class Stage367Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root, self.meta, self.job = fixture(Path(self.temp.name))

    def test_positive_is_explicitly_failed_sdl2(self):
        r = m.audit(self.root, self.meta, self.job)
        self.assertEqual(r["result"], m.VERDICT)
        self.assertTrue(r["github_job_still_failed"])
        self.assertFalse(r["sdl2_nro_produced"])

    def test_changed_artifact_digest_or_identity_rejected(self):
        for field, value in (("id", m.ARTIFACT_ID + 1),
                             ("digest", "sha256:" + "0" * 64),
                             ("expired", True),
                             ("size_in_bytes", 0)):
            with self.subTest(field=field):
                x = copy.deepcopy(self.meta)
                x[field] = value
                with self.assertRaises(ValueError):
                    m.audit(self.root, x, self.job)

    def test_replaced_run_and_head_sha_rejected(self):
        for field, value in (("id", m.RUN_ID + 1), ("head_sha", "0" * 40)):
            with self.subTest(field=field):
                x = copy.deepcopy(self.meta)
                x["workflow_run"][field] = value
                with self.assertRaises(ValueError):
                    m.audit(self.root, x, self.job)

    def test_green_ci_and_compiled_sdl2_claim_rejected(self):
        for field, value in (("conclusion", "success"), ("id", m.JOB_ID + 1)):
            with self.subTest(field=field):
                job = copy.deepcopy(self.job)
                job[field] = value
                with self.assertRaises(ValueError):
                    m.audit(self.root, self.meta, job)
        job = copy.deepcopy(self.job)
        job["steps"][2]["conclusion"] = "success"
        with self.assertRaises(ValueError):
            m.audit(self.root, self.meta, job)

    def test_tampered_log_and_false_classifier_rejected(self):
        logfile = self.root / m.RAW
        original = logfile.read_text()
        logfile.write_text("everything built successfully\n")
        with self.assertRaises(ValueError):
            m.audit(self.root, self.meta, self.job)
        logfile.write_text(original)
        diag = self.root / m.REPORT
        diag.write_text(diag.read_text().replace(
            '"compile_performed": false', '"compile_performed": true'))
        with self.assertRaises(ValueError):
            m.audit(self.root, self.meta, self.job)

    def test_extra_file_missing_file_and_link_rejected(self):
        extra = self.root / "unexpected.bin"
        extra.write_bytes(b"anything")
        with self.assertRaises(ValueError):
            m.audit(self.root, self.meta, self.job)
        extra.unlink()
        raw = self.root / m.RAW
        raw.unlink()
        with self.assertRaises(ValueError):
            m.audit(self.root, self.meta, self.job)
        raw.symlink_to(self.root / m.REPORT)
        with self.assertRaises(ValueError):
            m.audit(self.root, self.meta, self.job)


if __name__ == "__main__":
    unittest.main()
