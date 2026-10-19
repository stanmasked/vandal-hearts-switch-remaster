"""Real synthetic ELF -> private pipe -> independent offline replay."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_capture_map02_live_frame_pipe import SOURCE
from tools.capture_map02_live_frame_pipe import capture
from tools.replay_map02_live_frame_receipt import replay


class LivePipeReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="vh-map02-replay-elf-")
        root = Path(cls.workspace.name)
        cls.source = root / "producer.c"
        cls.executable = root / "producer"
        cls.source.write_text(SOURCE, encoding="utf-8")
        cc = os.environ.get("CC", "cc")
        if not shutil.which(cc):
            raise RuntimeError("selected native C compiler unavailable")
        subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                        str(cls.source), "-o", str(cls.executable)], check=True)
        cls.digest = hashlib.sha256(cls.executable.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vh-map02-live-replay-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "capture"
        self.directory.mkdir(mode=0o700)
        capture(self.executable, self.directory, frame=123, width=2, height=2,
                executable_sha256=self.digest, timeout=5)
        self.manifest = self.directory / "process-frame.json"
        self.image = self.directory / "process-frame.bgr555"

    def report(self):
        return replay(self.directory, executable=self.executable)

    def mutate(self, **changes):
        item = json.loads(self.manifest.read_text(encoding="utf-8"))
        item.update(changes)
        self.manifest.write_text(
            json.dumps(item, sort_keys=True) + "\n", encoding="utf-8")

    def test_replays_real_native_child_pipe_byte_for_byte(self):
        result = self.report()
        self.assertEqual(result["frame"], 123)
        self.assertEqual(result["width"], 2)
        self.assertEqual(result["height"], 2)
        self.assertEqual(result["image_sha256"], hashlib.sha256(
            bytes.fromhex("0000ff7f01000200")).hexdigest())
        self.assertEqual(result["executable_sha256"], self.digest)
        self.assertTrue(result["private_frame_integrity_replayed"])
        self.assertFalse(result["native_gpu_log_same_process_authenticated"])
        self.assertFalse(result["retail_disc_or_ps1_pixel_source_authenticated"])
        self.assertFalse(result["hd_replacement_authorized"])
        report = json.dumps(result)
        self.assertNotIn(str(self.directory), report)
        self.assertNotIn(str(self.executable), report)

    def test_modified_image_bytes_refused(self):
        self.image.write_bytes(b"\x00" * 8)
        with self.assertRaisesRegex(ValueError, "image SHA-256"):
            self.report()

    def test_altered_manifest_hash_refused(self):
        self.mutate(image_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "image SHA-256"):
            self.report()

    def test_executable_mismatch_refused(self):
        self.mutate(executable_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "executable SHA-256"):
            self.report()

    def test_wrong_frame_bool_refused(self):
        self.mutate(frame=True)
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.report()

    def test_fake_game_provenance_refused(self):
        self.mutate(native_renderer_origin_authenticated=True)
        with self.assertRaisesRegex(ValueError, "evidence flags"):
            self.report()

    def test_hd_activation_refused(self):
        self.mutate(hd_replacement_authorized=True)
        with self.assertRaisesRegex(ValueError, "evidence flags"):
            self.report()

    def test_missing_critical_flag_refused(self):
        self.mutate(child_stdout_pipe_frame_received=False)
        with self.assertRaisesRegex(ValueError, "evidence flags"):
            self.report()

    def test_unexpected_manifest_key_refused(self):
        self.mutate(trusted=True)
        with self.assertRaisesRegex(ValueError, "schema/fields"):
            self.report()

    def test_duplicate_json_key_refused(self):
        raw = self.manifest.read_bytes()
        self.manifest.write_bytes(
            raw.replace(b'"schema":', b'"schema":"fake","schema":', 1))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.report()

    def test_unterminated_manifest_refused(self):
        self.manifest.write_bytes(self.manifest.read_bytes().rstrip(b"\n"))
        with self.assertRaisesRegex(ValueError, "canonical JSON"):
            self.report()

    def test_carriage_return_refused(self):
        self.manifest.write_bytes(self.manifest.read_bytes().replace(b"\n", b"\r\n"))
        with self.assertRaisesRegex(ValueError, "canonical JSON"):
            self.report()

    def test_malformed_image_length_refused(self):
        self.image.write_bytes(self.image.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, "size, type or mode"):
            self.report()

    def test_new_unrecognized_file_refused(self):
        (self.directory / "injected").write_bytes(b"bogus")
        with self.assertRaisesRegex(ValueError, "exact file inventory"):
            self.report()

    def test_nonprivate_manifest_mode_refused(self):
        self.manifest.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "size, type or mode"):
            self.report()

    def test_output_directory_symlink_refused(self):
        alias = Path(self.temp.name) / "alias"
        alias.symlink_to(self.directory)
        with self.assertRaisesRegex(ValueError, "symlink"):
            replay(alias, executable=self.executable)

    def test_image_symlink_refused(self):
        saved = Path(self.temp.name) / "saved-image"
        self.image.rename(saved)
        self.image.symlink_to(saved)
        with self.assertRaises(OSError):
            self.report()


if __name__ == "__main__":
    unittest.main()
