"""Use real native GNU cc/ar/ld to audit byte-identical X11 archive replay."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.check_map02_private_incremental_link import OUTPUT
from tools.check_map02_public_x11_after_sdl2 import (
    measure_x11_after_sdl2,
)
from tools.verify_map02_public_x11_native_replay import (
    SCHEMA, verify_x11_native_replay,
)


class PublicX11NativeReplayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="map02-x11-byte-replay-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sdl2 = self.compile(
            "already-sdl2-linked",
            "extern int x11_needed(void); extern int missing(void);\n"
            "int root(void) {return x11_needed()+missing();}\n")
        self.sdl2.chmod(0o600)
        member = self.compile(
            "actual-x11-member",
            "extern int extra(void); int x11_needed(void) {return extra();}\n")
        self.archive = self.root / "native-real-x11.a"
        subprocess.run(["ar", "rcs", str(self.archive), str(member)],
                       check=True, capture_output=True, timeout=30)
        self.target = self.root / "original-link"
        self.report = measure_x11_after_sdl2(
            self.sdl2, self.archive, self.target, expected_sdl2_undefined=2)
        self.json_file = self.root / "x11-aggregate.json"
        self.json_file.write_text(json.dumps(self.report), encoding="utf-8")
        self.manifest = self.target / "after-sdl2-unresolved.private.json"
        self.candidate = self.target / "x11-system-candidate.a"
        self.linked = self.target / "linked" / OUTPUT

    def compile(self, name, code):
        source = self.root / (name + ".c")
        source.write_text(code, encoding="utf-8")
        dest = self.root / (name + ".o")
        subprocess.run(
            ["cc", "-std=c99", "-c", str(source), "-o", str(dest)],
            check=True, capture_output=True, timeout=30)
        return dest

    def check(self, replay, *, linked=None, saved=None, **kwargs):
        return verify_x11_native_replay(
            self.manifest, self.sdl2, self.candidate,
            linked or self.linked, saved or self.json_file, replay,
            expected_sdl2_strong=2, expected_final_strong=2, **kwargs)

    def test_second_real_gnu_ld_r_is_byte_identical(self):
        replay = self.root / "fresh-native-link"
        output = self.check(replay)
        self.assertEqual(output["schema"], SCHEMA)
        self.assertEqual(output["sdl2_stage_initial_strong_undefined"], 2)
        self.assertEqual(output["x11_resolved_original_stage_imports"], 1)
        self.assertEqual(output["x11_new_imports"], 1)
        self.assertEqual(output["final_strong_undefined"], 2)
        self.assertTrue(output["saved_x11_recount_verified"])
        self.assertTrue(output["independent_native_x11_relink_executed"])
        self.assertTrue(output["byte_identical_x11_relink_verified"])
        self.assertFalse(output["retail_assets_linked"])
        self.assertFalse(output["fully_linked_game_executable"])
        self.assertFalse(output["authentic_map02_execution_proven"])
        output_elf = replay / OUTPUT
        self.assertEqual(hashlib.sha256(output_elf.read_bytes()).hexdigest(),
                         hashlib.sha256(self.linked.read_bytes()).hexdigest())
        self.assertEqual(replay.stat().st_mode & 0o777, 0o700)
        self.assertEqual(output_elf.stat().st_mode & 0o777, 0o600)
        for symbol in ("x11_needed", "missing", "extra", str(self.sdl2)):
            self.assertNotIn(symbol, json.dumps(output))

    def test_forged_x11_elf_self_consistent_report_fails_real_replay(self):
        extra = self.compile(
            "unrelated-after-link",
            "int extra_definition_unrelated_to_imports(void) {return 23;}\n")
        new_elf = self.root / "different-but-valid-linked.o"
        subprocess.run(
            ["ld", "-r", str(self.linked), str(extra), "-o", str(new_elf)],
            check=True, capture_output=True, timeout=30)
        new_elf.chmod(0o600)
        data = dict(self.report)
        data["output_x11_partial_sha256"] = hashlib.sha256(
            new_elf.read_bytes()).hexdigest()
        changed = self.root / "forged-but-consistent-aggregate.json"
        changed.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "independent GNU relink differs"):
            self.check(self.root / "forged-link-replay", linked=new_elf,
                       saved=changed)

    def test_changed_count_and_false_game_claim_rejected_before_link(self):
        for key, value in (
            ("original_after_sdl2_imports_resolved", 0),
            ("fully_linked_game_executable", True),
            ("input_sdl2_partial_sha256", "0"*64),
        ):
            with self.subTest(key=key):
                bad = dict(self.report)
                bad[key] = value
                aggregate = self.root / (key + ".json")
                aggregate.write_text(json.dumps(bad), encoding="utf-8")
                output = self.root / ("refused-" + key)
                with self.assertRaisesRegex(
                        ValueError, "recount differs|schema invalid|hashes differ"):
                    self.check(output, saved=aggregate)
                self.assertFalse(output.exists())

    def test_symlink_report_and_existing_replay_directory_rejected(self):
        alias = self.root / "report-alias.json"
        alias.symlink_to(self.json_file)
        with self.assertRaisesRegex(ValueError, "report inaccessible"):
            self.check(self.root / "report-symlink-output", saved=alias)
        output = self.root / "already-existing-output"
        output.mkdir()
        marker = output / "marker"
        marker.write_text("unchanged", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.check(output)
        self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged")

    def test_wrong_expected_baseline_fails_without_output(self):
        output = self.root / "wrong-count"
        with self.assertRaisesRegex(ValueError, "expected import totals invalid"):
            self.check(output, expected_sdl2_strong=True)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
