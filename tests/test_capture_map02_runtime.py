"""Host-only tests for the opt-in local map02 runtime capture command."""
import hashlib
import json
import shutil
import subprocess
import stat
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.capture_map02_runtime import capture, sha256_file, executable_contains_marker
from tools.prepare_map02_pcport import PINNED_BLOB_SHA1, PINNED_UPSTREAM_REF


def fixture(root: Path, mode="complete", modified=False, trace_mode="legacy"):
    trace_dir = root / "prepared"
    trace_dir.mkdir()
    provenance = {
        "upstream_reference": PINNED_UPSTREAM_REF,
        "trace_mode": trace_mode,
        "allow_modified_source": modified,
        "source_files": {
            name: {
                "matches_pinned": not modified,
                "git_blob_sha1": ("0" * 40 if modified else blob),
                "sha256": hashlib.sha256(name.encode("utf-8")).hexdigest(),
            }
            for name, blob in PINNED_BLOB_SHA1.items()
        },
    }
    payloads = {
        "game_setup.trace.c": "/* generated loader trace */\n",
        "graphics.trace.c": "/* generated renderer trace */\n",
        "map02_trace.mk": "# generated diagnostic Make overlay\n",
    }
    if trace_mode == "full":
        digest = hashlib.sha256(b"synthetic map02 fixture").hexdigest()
        provenance["binary_marker"] = "VH_MAP02_TRACE_BUILD_ID:" + digest
        provenance["binary_loader_marker"] = "VH_MAP02_TRACE_LOADER_ID:" + digest
    provenance["generated_files"] = {
        name: hashlib.sha256(content.encode("utf-8")).hexdigest()
        for name, content in payloads.items()
    }
    for name, content in payloads.items():
        (trace_dir / name).write_text(content, encoding="utf-8")
    (trace_dir / "source_provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
    executable = root / "fake-pcport"
    events = [
        {"z": 8, "x": 19, "face": 0, "stage": "post_load", "gfx": 641},
        {"z": 11, "x": 11, "face": 0, "stage": "post_load", "gfx": 643},
        {"z": 8, "x": 19, "face": 0, "stage": "draw", "gfx": 641},
        {"z": 11, "x": 11, "face": 0, "stage": "draw", "gfx": 643},
    ]
    if mode == "incomplete":
        events = events[:2]
    if mode == "invalid":
        events[2]["gfx"] = 498
    if mode == "bad_stage":
        events[2]["stage"] = []
    if mode == "visit_draw_mismatch":
        # Loading and drawing both appear PRS, but the full renderer entry
        # observed DAT in the same frame/path: this must not pass unnoticed.
        events[2].update({"frame": 8, "path": "normal"})
        events.insert(2, {"z": 8, "x": 19, "face": 0,
                          "stage": "visit", "gfx": 498, "frame": 8,
                          "path": "normal", "face_count": 4})
    if mode == "empty":
        events = []
    if trace_mode == "full" and events:
        # Full C renderer emits a visit before each face's first draw.
        # Include frame and path to exercise strict capture validation.
        events = [
            events[0], events[1],
            {"z": 8, "x": 19, "face": 0, "stage": "visit", "gfx": 641,
             "frame": 8, "path": "normal", "face_count": 4},
            {**events[2], "frame": 8, "path": "normal"},
            {"z": 11, "x": 11, "face": 0, "stage": "visit", "gfx": 643,
             "frame": 8, "path": "normal", "face_count": 4},
            {**events[3], "frame": 8, "path": "normal"},
        ]
    lines = ["booting pc-port", *(json.dumps(ev) for ev in events), "normal shutdown"]
    source = "#!/usr/bin/env python3\n" + "\n".join(
        ["import sys", f"print({chr(10).join(lines)!r})",
         f"raise SystemExit({7 if mode == 'crash' else 0})"]
    ) + "\n"
    if mode == "non_utf8":
        source = source.replace(
            "import sys\n", "import sys\nsys.stdout.buffer.write(bytes((255, 254, 10)))\n", 1
        )
    if trace_mode == "full":
        compiler = shutil.which("gcc") or shutil.which("cc")
        if compiler is None:
            raise unittest.SkipTest("C compiler required for full-trace executable test")
        marker = provenance["binary_marker"]
        loader_marker = provenance["binary_loader_marker"]
        c_lines = [
            "#include <stdio.h>",
            f'__attribute__((used)) const char vh_map02_trace_build_marker[] = "{marker}";',
            f'__attribute__((used)) const char vh_map02_trace_loader_marker[] = "{loader_marker}";',
            "int main(void) {",
            *[f"puts({json.dumps(line)});" for line in lines],
            "return 0;",
            "}",
        ]
        c_source = root / "fake-pcport.c"
        c_source.write_text("\n".join(c_lines) + "\n", encoding="utf-8")
        subprocess.run([compiler, "-std=c11", str(c_source), "-o", str(executable)],
                       check=True, capture_output=True, text=True)
    else:
        executable.write_text(source, encoding="utf-8")
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable, trace_dir


class CaptureMap02RuntimeTests(unittest.TestCase):
    def test_complete_capture_writes_raw_log_jsonl_report_and_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base)
            dest = base / "run"
            self.assertEqual(capture(exe, trace_dir, dest), 0)
            report = json.loads((dest / "capture_report.json").read_text())
            self.assertEqual(report["trace_events"], 4)
            self.assertEqual(report["analysis"]["errors"], [])
            self.assertEqual(report["analysis"]["draw_overall_variant"], "PRS")
            self.assertEqual(len(report["binary_sha256"]), 64)
            self.assertIn("booting pc-port", (dest / "game_stdout.log").read_text())
            self.assertEqual(len((dest / "map02_trace.jsonl").read_text().splitlines()), 4)
            with self.assertRaisesRegex(ValueError, "already exists"):
                capture(exe, trace_dir, dest)

    def test_incomplete_and_invalid_traces_fail_but_preserve_evidence(self):
        for mode in ("incomplete", "invalid", "bad_stage", "empty"):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as folder:
                    base = Path(folder)
                    exe, trace_dir = fixture(base, mode=mode)
                    dest = base / "run"
                    self.assertEqual(capture(exe, trace_dir, dest), 2)
                    self.assertTrue((dest / "game_stdout.log").exists())
                    report = json.loads((dest / "capture_report.json").read_text())
                    self.assertTrue(report["analysis"]["errors"])

    def test_runtime_capture_detects_visit_draw_gfx_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base, mode="visit_draw_mismatch")
            output = base / "conflict-run"
            self.assertEqual(capture(exe, trace_dir, output), 2)
            report = json.loads((output / "capture_report.json").read_text())
            self.assertTrue(any("mismatch between visit and draw" in error
                                for error in report["analysis"]["errors"]))
            self.assertEqual(report["analysis"]["post_load_overall_variant"], "PRS")
            self.assertEqual(report["analysis"]["draw_overall_variant"], "PRS")
            self.assertEqual(report["analysis"]["observations"][0]
                             ["visit_draw_contexts_checked"], 1)
            self.assertEqual(len((output / "map02_trace.jsonl").read_text().splitlines()), 5)

    def test_malformed_stage_in_game_stdout_yields_report_not_exception(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base, mode="bad_stage")
            target = base / "bad-stage-run"
            self.assertEqual(capture(exe, trace_dir, target), 2)
            report = json.loads((target / "capture_report.json").read_text())
            self.assertTrue(any("invalid stage" in e for e in report["analysis"]["errors"]))
            self.assertEqual(report["trace_events"], 4)
            self.assertEqual(len((target / "map02_trace.jsonl").read_text().splitlines()), 4)

    def test_trace_jsonl_appears_while_game_is_still_running(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base)
            release = base / "release-game"
            output = base / "capture"
            events = [
                {"z": 8, "x": 19, "face": 0, "stage": "post_load", "gfx": 641},
                {"z": 11, "x": 11, "face": 0, "stage": "post_load", "gfx": 643},
                {"z": 8, "x": 19, "face": 0, "stage": "draw", "gfx": 641},
                {"z": 11, "x": 11, "face": 0, "stage": "draw", "gfx": 643},
            ]
            program = (
                "#!/usr/bin/env python3\nimport pathlib\nimport time\n"
                f"print({json.dumps(events[0])!r}, flush=True)\n"
                f"release = pathlib.Path({str(release)!r})\n"
                "for attempt in range(400):\n"
                "    if release.exists(): break\n"
                "    time.sleep(0.025)\n"
                + "".join(f"print({json.dumps(e)!r}, flush=True)\n" for e in events[1:])
            )
            exe.write_text(program, encoding="utf-8")
            result = []
            worker = threading.Thread(target=lambda: result.append(capture(exe, trace_dir, output)))
            worker.start()
            try:
                deadline = time.monotonic() + 7
                path = output / "map02_trace.jsonl"
                while time.monotonic() < deadline:
                    if path.exists() and path.read_text().count("\n") >= 1:
                        break
                    time.sleep(0.025)
                self.assertTrue(path.exists())
                self.assertEqual([json.loads(line) for line in path.read_text().splitlines()],
                                 events[:1])
                self.assertTrue(worker.is_alive(), "first trace event should be saved before game exit")
            finally:
                release.touch()
                worker.join(timeout=12)
            self.assertFalse(worker.is_alive())
            self.assertEqual(result, [0])
            path = output / "map02_trace.jsonl"
            self.assertEqual([json.loads(line) for line in path.read_text().splitlines()],
                             events)

    def test_malformed_game_line_keeps_valid_prefix_in_live_jsonl(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base)
            first = {"z": 8, "x": 19, "face": 0, "stage": "post_load", "gfx": 641}
            malformed = '{"z":8,"x":19,"face":0,"stage":"draw","gfx":'
            exe.write_text(
                "#!/usr/bin/env python3\n"
                + f"print({json.dumps(first)!r})\n"
                + f"print({malformed!r})\n", encoding="utf-8"
            )
            output = base / "run"
            self.assertEqual(capture(exe, trace_dir, output), 2)
            saved = (output / "map02_trace.jsonl").read_text().splitlines()
            self.assertEqual([json.loads(line) for line in saved], [first])
            report = json.loads((output / "capture_report.json").read_text())
            self.assertEqual(report["trace_events"], 1)
            self.assertTrue(any("malformed Map02" in error
                                for error in report["analysis"]["errors"]))
            self.assertIn(malformed, (output / "game_stdout.log").read_text())

    def test_non_utf8_game_output_is_preserved_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base, mode="non_utf8")
            dest = base / "run"
            self.assertEqual(capture(exe, trace_dir, dest), 0)
            self.assertTrue((dest / "game_stdout.log").read_bytes().startswith(bytes((255, 254, 10))))
            report = json.loads((dest / "capture_report.json").read_text())
            self.assertEqual(report["trace_events"], 4)
            self.assertEqual(report["analysis"]["errors"], [])

    def test_modified_provenance_requires_explicit_override(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base, modified=True)
            dest = base / "run"
            with self.assertRaisesRegex(ValueError, "--allow-modified-source"):
                capture(exe, trace_dir, dest)
            self.assertFalse(dest.exists())
            self.assertEqual(capture(exe, trace_dir, dest, allow_modified_source=True), 0)
            self.assertTrue(json.loads((dest / "capture_report.json").read_text())
                            ["source_provenance"]["allow_modified_source"])

    def test_wrong_revision_or_source_list_is_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base)
            provenance_path = trace_dir / "source_provenance.json"
            expected = json.loads(provenance_path.read_text())
            wrong_revision = dict(expected, upstream_reference="wrong-revision")
            provenance_path.write_text(json.dumps(wrong_revision))
            with self.assertRaisesRegex(ValueError, "pinned upstream revision"):
                capture(exe, trace_dir, base / "run")
            wrong_sources = dict(expected)
            wrong_sources["source_files"] = dict(expected["source_files"])
            wrong_sources["source_files"]["unknown.c"] = wrong_sources["source_files"].pop("src/core/graphics.c")
            provenance_path.write_text(json.dumps(wrong_sources))
            with self.assertRaisesRegex(ValueError, "three pinned files"):
                capture(exe, trace_dir, base / "run")
            self.assertFalse((base / "run").exists())

    def test_provenance_root_must_be_an_object(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base)
            (trace_dir / "source_provenance.json").write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be a JSON object"):
                capture(exe, trace_dir, base / "run")
            self.assertFalse((base / "run").exists())

    def test_source_manifest_cannot_forge_pinned_match_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base)
            manifest = trace_dir / "source_provenance.json"
            data = json.loads(manifest.read_text())
            data["source_files"]["src/core/graphics.c"]["git_blob_sha1"] = "f" * 40
            manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "matches_pinned disagrees"):
                capture(exe, trace_dir, base / "run")
            self.assertFalse((base / "run").exists())

    def test_invalid_source_hashes_and_manifest_types_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base)
            manifest = trace_dir / "source_provenance.json"
            original = json.loads(manifest.read_text())
            cases = (
                ("bad-git-id", {"source_files": {**original["source_files"],
                  "src/core/graphics.c": {**original["source_files"]["src/core/graphics.c"],
                                         "git_blob_sha1": "bad"}}}, "invalid Git blob SHA-1"),
                ("bad-sha256", {"source_files": {**original["source_files"],
                  "src/core/graphics.c": {**original["source_files"]["src/core/graphics.c"],
                                         "sha256": "invalid"}}}, "invalid source SHA-256"),
                ("false-boolean", {"allow_modified_source": "false"}, "must be a boolean"),
                ("legacy-no-generated-hashes", {"generated_files": None}, "must fingerprint generated files"),
            )
            for name, patch, error in cases:
                with self.subTest(name=name):
                    manifest.write_text(json.dumps({**original, **patch}))
                    with self.assertRaisesRegex(ValueError, error):
                        capture(exe, trace_dir, base / "run")
                    self.assertFalse((base / "run").exists())

    def test_legacy_generated_input_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base, trace_mode="legacy")
            source = trace_dir / "graphics.trace.c"
            source.write_text(source.read_text() + "tampered\n")
            with self.assertRaisesRegex(ValueError, "changed since preparation"):
                capture(exe, trace_dir, base / "run")
            self.assertFalse((base / "run").exists())

    def test_full_capture_requires_visit_before_a_draw(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, prepared = fixture(base, trace_mode="full")
            report_dir = base / "successful"
            self.assertEqual(capture(exe, prepared, report_dir), 0)
            report = json.loads((report_dir / "capture_report.json").read_text())
            self.assertEqual(report["trace_events"], 6)
            self.assertEqual(report["analysis"]["errors"], [])
            self.assertEqual(
                [r["visit_draw_contexts_checked"] for r in report["analysis"]["observations"]],
                [1, 1],
            )

    def test_full_trace_generated_inputs_are_verified_before_game_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base, trace_mode="full")
            first = base / "verified-run"
            self.assertEqual(capture(exe, trace_dir, first), 0)
            report = json.loads((first / "capture_report.json").read_text())
            self.assertEqual(report["source_provenance"]["trace_mode"], "full")
            self.assertEqual(len(report["source_provenance"]["generated_files"]), 3)

            for name in ("game_setup.trace.c", "graphics.trace.c", "map02_trace.mk"):
                with self.subTest(filename=name):
                    path = trace_dir / name
                    original = path.read_bytes()
                    path.write_bytes(original + b"altered")
                    target = base / ("tampered-" + name)
                    with self.assertRaisesRegex(ValueError, "changed since preparation"):
                        capture(exe, trace_dir, target)
                    self.assertFalse(target.exists())
                    path.write_bytes(original)

    def test_full_trace_missing_or_invalid_fingerprints_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base, trace_mode="full")
            manifest_path = trace_dir / "source_provenance.json"
            original = json.loads(manifest_path.read_text())
            cases = [
                (dict(original, generated_files=None), "must fingerprint"),
                (dict(original, generated_files={}), "three diagnostic build inputs"),
                (dict(original, generated_files={**original["generated_files"],
                       "graphics.trace.c": "zz"}), "invalid generated source SHA-256"),
            ]
            for case, error in cases:
                with self.subTest(error=error):
                    manifest_path.write_text(json.dumps(case))
                    with self.assertRaisesRegex(ValueError, error):
                        capture(exe, trace_dir, base / "should-not-exist")
                    self.assertFalse((base / "should-not-exist").exists())
            manifest_path.write_text(json.dumps(original))

    def test_full_trace_loader_marker_is_required_and_identity_matched(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base, trace_mode="full")
            path = trace_dir / "source_provenance.json"
            original = json.loads(path.read_text())
            output = base / "wrong-loader"
            for marker, error in [
                (None, "valid loader build marker"),
                ("not-a-loader-id", "valid loader build marker"),
                ("VH_MAP02_TRACE_LOADER_ID:" + "f" * 64, "different identities"),
            ]:
                with self.subTest(marker=marker):
                    bad = dict(original)
                    if marker is None:
                        bad.pop("binary_loader_marker")
                    else:
                        bad["binary_loader_marker"] = marker
                    path.write_text(json.dumps(bad))
                    with self.assertRaisesRegex(ValueError, error):
                        capture(exe, trace_dir, output)
                    self.assertFalse(output.exists())
            path.write_text(json.dumps(original))
            raw = exe.read_bytes()
            missing = base / "missing-loader"
            missing.write_bytes(raw.replace(
                original["binary_loader_marker"].encode("ascii"),
                b"X" * len(original["binary_loader_marker"])))
            with self.assertRaisesRegex(ValueError, "wrong or unlinked loader"):
                capture(missing, trace_dir, output)
            self.assertFalse(output.exists())

    def test_full_trace_marker_scanner_handles_binary_chunk_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / "binary.bin"
            marker = "VH_MAP02_TRACE_BUILD_ID:" + "a" * 64
            needle = marker.encode("ascii") + b"\0"
            binary.write_bytes(b"x" * (65536 - 35) + needle + b"trailer")
            self.assertTrue(executable_contains_marker(binary, marker))
            self.assertFalse(executable_contains_marker(
                binary, "VH_MAP02_TRACE_BUILD_ID:" + "b" * 64))

    def test_full_trace_rejects_unlinked_or_incorrect_build_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base, trace_mode="full")
            manifest_path = trace_dir / "source_provenance.json"
            manifest = json.loads(manifest_path.read_text())
            wrong = dict(manifest, binary_marker="VH_MAP02_TRACE_BUILD_ID:" + "f" * 64)
            manifest_path.write_text(json.dumps(wrong))
            output = base / "wrong-build"
            with self.assertRaisesRegex(ValueError, "wrong or unlinked binary"):
                capture(exe, trace_dir, output)
            self.assertFalse(output.exists())
            wrong["binary_marker"] = "not-a-valid-marker"
            manifest_path.write_text(json.dumps(wrong))
            with self.assertRaisesRegex(ValueError, "valid binary marker"):
                capture(exe, trace_dir, output)
            manifest_path.write_text(json.dumps(manifest))

    def test_failed_process_launch_keeps_report_and_binary_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base)
            exe.write_text("#!/definitely/no/such/python3\n", encoding="utf-8")
            original_sha = sha256_file(exe)
            output = base / "run"
            self.assertEqual(capture(exe, trace_dir, output), 1)
            self.assertTrue((output / "game_stdout.log").exists())
            report = json.loads((output / "capture_report.json").read_text())
            self.assertEqual(report["binary_sha256"], original_sha)
            self.assertIsNone(report["game_exit_code"])
            self.assertIn("launch_error", report)
            self.assertTrue(report["analysis"]["errors"])
            self.assertFalse((output / "map02_trace.jsonl").exists())

    def test_binary_hash_identifies_executable_before_it_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base)
            content = exe.read_text(encoding="utf-8")
            original_end = "raise SystemExit(0)"
            self.assertIn(original_end, content)
            mutation = (
                "with open(__file__, 'ab') as stream: "
                "stream.write(bytes((35, 32, 99, 104, 97, 110, 103, 101, 100, 10)))"
            )
            exe.write_text(content.replace(original_end, mutation + "\n" + original_end),
                           encoding="utf-8")
            starting_hash = sha256_file(exe)
            output = base / "run"
            self.assertEqual(capture(exe, trace_dir, output), 0)
            report = json.loads((output / "capture_report.json").read_text())
            self.assertEqual(report["binary_sha256"], starting_hash)
            self.assertNotEqual(sha256_file(exe), starting_hash)

    def test_keyboard_interrupt_saves_partial_trace_and_terminates_child(self):
        """Ctrl+C while reading the output must not strand a child or lose evidence."""
        class FakeOutput:
            def __init__(self):
                self.calls = 0

            def read(self, count):
                self.calls += 1
                if self.calls == 1:
                    return b"PC-port starting\n"
                raise KeyboardInterrupt

        class FakeProcess:
            def __init__(self):
                self.stdout = FakeOutput()
                self.returncode = None
                self.terminated = False

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def poll(self):
                return self.returncode

            def terminate(self):
                self.terminated = True
                self.returncode = -15

            def communicate(self, timeout=None):
                return (b'{"z":8,"x":19,"face":0,"stage":"post_load","gfx":641}\n', None)

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe, trace_dir = fixture(root)
            output = root / "interrupted"
            proc = FakeProcess()
            with patch("tools.capture_map02_runtime.subprocess.Popen", return_value=proc):
                self.assertEqual(capture(exe, trace_dir, output), 1)
            self.assertTrue(proc.terminated)
            report = json.loads((output / "capture_report.json").read_text())
            self.assertTrue(report["interrupted"])
            self.assertEqual(report["game_exit_code"], -15)
            self.assertEqual(report["trace_events"], 1)
            self.assertTrue(any("missing draw" in error
                                for error in report["analysis"]["errors"]))
            self.assertIn(b"PC-port starting", (output / "game_stdout.log").read_bytes())
            self.assertIn(b'"stage":"post_load"', (output / "game_stdout.log").read_bytes())

    def test_closed_terminal_output_does_not_destroy_raw_capture(self):
        class BrokenOutput:
            class Buffer:
                def write(self, _):
                    raise BrokenPipeError("simulated terminal closing")

                def flush(self):
                    pass

            buffer = Buffer()

        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base)
            output = base / "run"
            with patch("tools.capture_map02_runtime.sys.stdout", BrokenOutput()):
                self.assertEqual(capture(exe, trace_dir, output), 0)
            self.assertIn(b"booting pc-port", (output / "game_stdout.log").read_bytes())
            self.assertEqual(json.loads((output / "capture_report.json").read_text())
                             ["analysis"]["errors"], [])

    def test_process_failure_is_not_mistaken_for_success(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe, trace_dir = fixture(base, mode="crash")
            dest = base / "run"
            self.assertEqual(capture(exe, trace_dir, dest), 1)
            report = json.loads((dest / "capture_report.json").read_text())
            self.assertEqual(report["game_exit_code"], 7)


if __name__ == "__main__":
    unittest.main()
