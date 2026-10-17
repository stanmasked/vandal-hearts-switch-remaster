"""Native ELF process-image gate using an actually compiled Linux test executable.

The binary copies only synthetic fixture snapshots; it is NOT the retail game
and does not prove instrumentation or authentic provenance of the GPU logs.
"""
import json
import os
import subprocess
import unittest
from unittest.mock import patch

import test_map02_launch_two_word_process_integration as fixture_module
from tools.run_map02_private_native_capture import capture
from tools.audit_map02_launch_two_word_binding import audit_launch_two_word
from tools.verify_map02_private_capture_receipt import replay_receipt

NATIVE_EMITTER = r'''
#define _POSIX_C_SOURCE 200809L
#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>

static int copy_file(const char *src, const char *dest) {
    FILE *a = fopen(src, "rb");
    if (!a) return 1;
    FILE *b = fopen(dest, "wb");
    if (!b) { fclose(a); return 2; }
    unsigned char buf[32768];
    size_t n;
    int failed = 0;
    while ((n = fread(buf, 1, sizeof(buf), a)) > 0)
        if (fwrite(buf, 1, n, b) != n) { failed = 3; break; }
    if (ferror(a)) failed = 4;
    if (fclose(a)) failed = 5;
    if (fclose(b)) failed = 6;
    return failed;
}
int main(int argc, char **argv) {
    if (argc != 2) return 10;
    const char *output = getenv("VH_MAP02_GPU_CAPTURE_DIR");
    const char *frame = getenv("VH_MAP02_GPU_CAPTURE_FRAME");
    if (!output || !frame) return 11;
    DIR *directory = opendir(argv[1]);
    if (!directory) return 12;
    struct dirent *entry;
    while ((entry = readdir(directory))) {
        if (entry->d_name[0] == '.') continue;
        char from[4096], to[4096];
        if (snprintf(from, sizeof(from), "%s/%s", argv[1], entry->d_name) >= (int)sizeof(from)
            || snprintf(to, sizeof(to), "%s/%s", output, entry->d_name) >= (int)sizeof(to)) {
            closedir(directory); return 13;
        }
        struct stat info;
        if (lstat(from, &info) || !S_ISREG(info.st_mode) || copy_file(from, to)) {
            closedir(directory); return 14;
        }
    }
    closedir(directory);
    char dda[4096];
    if (snprintf(dda, sizeof(dda), "%s/dda-native-spans.jsonl", output) >= (int)sizeof(dda))
        return 15;
    FILE *log = fopen(dda, "wb");
    if (!log) return 16;
    if (fprintf(log, "{\"stage\":\"native_dda_span\",\"step\":0,\"frame\":%s,"
        "\"primitive_ordinal\":1,\"primitive_type\":2,\"y\":30,"
        "\"x_start\":30,\"x_bound\":35,\"clip_l\":20,\"clip_r\":45,"
        "\"clip_t\":25,\"clip_b\":40}\n", frame) < 0) {
        fclose(log); return 17;
    }
    if (fclose(log)) return 18;
    /* Keep procfs /proc/PID/exe observable while the parent launches. */
    struct timespec delay = {0, 400000000};
    nanosleep(&delay, NULL);
    return 0;
}
'''


class NativeElfProcessImageTests(unittest.TestCase):
    def setUp(self):
        if os.name != "posix":
            self.skipTest("Linux-only pinned ELF feature")
        host = fixture_module.SpawnedTwoWordCrossAuditTests(
            methodName="test_actual_subprocess_two_verifiers_and_stable_receipt_agree")
        host.setUp()
        self.addCleanup(host.doCleanups)
        self.host = host

    def build_elf(self, code=NATIVE_EMITTER):
        result = subprocess.run(
            ["gcc", "-std=c11", "-O0", "-Wall", "-Wextra", "-Werror",
             "-x", "c", "-", "-o", str(self.host.executable)],
            input=code, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.host.executable.chmod(0o700)
        with self.host.executable.open("rb") as f:
            self.assertEqual(f.read(4), b"\x7fELF")

    def run_capture(self, *, strict=True):
        return capture(
            self.host.executable, self.host.preflight, self.host.receipt,
            game_args=(str(self.host.template),), environ=self.host.env,
            timeout=10, require_native_elf_image=strict,
        )

    def test_compiled_native_elf_is_verified_and_binds_two_word_gpu(self):
        self.build_elf()
        result = self.run_capture()
        self.assertTrue(result["native_elf_image_required"])
        self.assertTrue(result["native_elf_image_observed"])
        self.assertTrue(result["process_started"])
        self.assertEqual(result["process_exit_code"], 0)
        self.assertTrue(result["capture_verified"])
        self.assertEqual(result["schema"], "map02_private_native_process_receipt_v2")
        checked = replay_receipt(
            self.host.native, receipt_file=self.host.receipt,
            preflight_report=self.host.preflight, executable=self.host.executable)
        self.assertTrue(checked["raw_evidence_matches_original_receipt"])
        joined = audit_launch_two_word(
            self.host.native, self.host.source, launch_receipt=self.host.receipt,
            preflight_report=self.host.preflight, executable=self.host.executable,
            require_native_elf_image=True)
        self.assertTrue(joined["same_native_gpu_log_sha256_verified"])
        self.assertTrue(joined["native_elf_process_image_observed"])
        self.assertTrue(joined["native_elf_image_required_for_join"])
        self.assertEqual(joined["source_keyed_ft4_draws_checked"], 2)
        self.assertFalse(joined["native_process_to_log_causality_authenticated"])
        self.assertFalse(joined["retail_map02_gameplay_authenticated"])
        self.assertFalse(joined["hd_replacement_authorized"])
        public = json.dumps(result)
        self.assertNotIn(str(self.host.template), public)
        self.assertNotIn(str(self.host.native), public)

    def test_script_is_rejected_before_process_execution(self):
        result = self.run_capture()
        self.assertFalse(result["process_started"])
        self.assertFalse(result["capture_verified"])
        self.assertFalse(result["native_elf_image_observed"])
        self.assertEqual(result["failure_category"], "native_elf_required")
        self.assertEqual(list(self.host.native.iterdir()), [])
        with self.assertRaises(ValueError):
            replay_receipt(
                self.host.native, receipt_file=self.host.receipt,
                preflight_report=self.host.preflight,
                executable=self.host.executable)

    def test_legacy_synthetic_process_is_rejected_by_strict_join(self):
        # A complete synthetic v1 capture remains valid for legacy audits,
        # but cannot satisfy the native Linux ELF process gate.
        ordinary = self.host.spawn()
        self.assertTrue(ordinary["capture_verified"])
        self.assertTrue(self.host.cross_audit()["same_native_gpu_log_sha256_verified"])
        with self.assertRaisesRegex(ValueError, "native ELF image observation required"):
            audit_launch_two_word(
                self.host.native, self.host.source, launch_receipt=self.host.receipt,
                preflight_report=self.host.preflight, executable=self.host.executable,
                require_native_elf_image=True)

    def test_observation_failure_is_not_promoted_to_verified_capture(self):
        self.build_elf()
        with patch("tools.run_map02_private_native_capture.observe_live_elf_image",
                   side_effect=ValueError("unavailable kernel image")):
            result = self.run_capture()
        self.assertTrue(result["process_started"])
        self.assertEqual(result["process_exit_code"], 0)
        self.assertFalse(result["native_elf_image_observed"])
        self.assertFalse(result["capture_verified"])
        self.assertEqual(result["failure_category"], "native_elf_image_unverified")
        with self.assertRaises(ValueError):
            replay_receipt(
                self.host.native, receipt_file=self.host.receipt,
                preflight_report=self.host.preflight,
                executable=self.host.executable)

    def test_forged_observation_false_is_rejected_during_replay(self):
        self.build_elf()
        result = self.run_capture()
        self.assertTrue(result["capture_verified"])
        forged = json.loads(self.host.receipt.read_bytes())
        forged["native_elf_image_observed"] = False
        self.host.receipt.write_text(json.dumps(forged), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "native ELF image"):
            replay_receipt(
                self.host.native, receipt_file=self.host.receipt,
                preflight_report=self.host.preflight,
                executable=self.host.executable)


if __name__ == "__main__":
    unittest.main()
