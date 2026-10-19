"""Asset-free composition tests; original-source compile verified in upstream CI."""
import unittest
from unittest.mock import patch

from tools import instrument_map02_joint_gpu_frame as joint

INPUT = b"synthetic placeholder (must be rejected unless hash is mocked)"
COMPOSED = (
    "static int vh_frame_pipe_selected;\n"
    "static void VH_Map02PrivateFrameFlush(void) {\n"
    "    if (fflush(NULL) != 0)\n"
    "        _exit(93);\n"
    "}\n"
    "static void VH_CaptureInit(void) {}\n"
    "static unsigned vh_capture_seq;\n"
    "static unsigned long vh_capture_frame;\n"
    "static int vh_capture_init;\n"
    "#define VH_CAPTURE_LIMIT 64u\n"
    + "\n".join(joint.PRIVATE_FILE_OPENERS) + "\n"
    + ('    file = fopen(status_path, "wx");\n' * 2)
    + joint.EVENT_ANCHOR + "\n"
    + joint.ORIGINAL_GPU_MARKER + "\n"
    "void DrawOTag(unsigned int *p) {}\n"
)


class CombinedMap02GpuFrameTests(unittest.TestCase):
    def generate(self, changed=COMPOSED):
        with (
            patch.object(joint, "git_blob_sha1", return_value=joint.PINNED_SOURCE),
            patch.object(joint, "frame_instrument", return_value="stage-one"),
            patch.object(joint, "gpu_instrument", return_value=changed)
        ):
            return joint.instrument(INPUT)

    def test_one_compiled_gpu_tu_contains_both_capture_paths(self):
        result = self.generate()
        self.assertIn("#error \"joint MAP02 frame flush requires", result)
        self.assertIn("static int VH_Map02JointGpuSessionReady(void);", result)
        self.assertIn("static int VH_Map02JointGpuSessionReady(void)\n{", result)
        self.assertIn("vh_capture_frame == (unsigned long)s_drawFrame", result)
        self.assertIn("vh_capture_seq < VH_CAPTURE_LIMIT", result)
        self.assertIn("vh_capture_seq >= 2u", result)
        self.assertIn("vh_capture_seq % 2u", result)
        self.assertIn("    if (!VH_Map02JointGpuSessionReady())\n        _exit(96);", result)
        self.assertLess(result.index("static int vh_capture_init;"),
                        result.index("static int VH_Map02JointGpuSessionReady(void)\n{"))


    def test_secure_exclusive_snapshot_and_persistent_event_log(self):
        result = self.generate()
        self.assertIn("O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600", result)
        self.assertIn("file = VH_Map02SecureFile(snapshot_path);", result)
        self.assertIn("file = VH_Map02SecureFile(upload_path);", result)
        self.assertIn("log = VH_Map02SecureLog(log_path);", result)
        self.assertIn("static FILE *vh_map02_joint_log;", result)
        self.assertIn("vh_map02_joint_events_completed == vh_capture_seq", result)
        self.assertIn("if (VH_Map02FlushLog(log) == 0)", result)
        self.assertIn("++vh_map02_joint_events_completed;", result)
        self.assertIn("++vh_capture_saved;", result)
        self.assertIn("file = VH_Map02SecureFile(status_path);", result)
        self.assertEqual(result.count("file = VH_Map02SecureFile(status_path);"), 2)
        self.assertIn("if (vh_capture_windows) return 0;", result)
        self.assertIn("if (ferror(log) == 0) {", result)
        self.assertEqual(result.count("file = fopen(snapshot_path, \"wb\");"), 1)
        self.assertEqual(result.count("log = fopen(log_path, \"ab\");"), 1)
        self.assertIn("#else\n    log = fopen(log_path, \"ab\");", result)

    def test_missing_or_duplicate_terminal_status_open_sites_fail_closed(self):
        status = '    file = fopen(status_path, "wx");'
        with self.assertRaisesRegex(ValueError,
                                    "completion receipt anchor changed"):
            self.generate(COMPOSED.replace(status, "", 1))
        with self.assertRaisesRegex(ValueError,
                                    "completion receipt anchor changed"):
            self.generate(COMPOSED + status)

    def test_main_recorder_close_sequence_must_match_exactly(self):
        original = joint.PRIVATE_FILE_OPENERS[3]
        self.assertIn("++vh_capture_saved", original)
        with self.assertRaisesRegex(ValueError,
                                    "joint MAP02 private GPU hook anchor changed"):
            self.generate(COMPOSED.replace(original, "    fclose(log);"))

    def test_missing_snapshot_open_site_refused(self):
        with self.assertRaisesRegex(ValueError, "anchor changed"):
            self.generate(COMPOSED.replace(joint.PRIVATE_FILE_OPENERS[0], ""))

    def test_missing_upload_open_site_refused(self):
        with self.assertRaisesRegex(ValueError, "anchor changed"):
            self.generate(COMPOSED.replace(joint.PRIVATE_FILE_OPENERS[1], ""))

    def test_missing_event_log_open_site_refused(self):
        with self.assertRaisesRegex(ValueError, "anchor changed"):
            self.generate(COMPOSED.replace(joint.PRIVATE_FILE_OPENERS[2], ""))

    def test_missing_persistent_log_close_site_refused(self):
        with self.assertRaisesRegex(ValueError, "anchor changed"):
            self.generate(COMPOSED.replace(joint.PRIVATE_FILE_OPENERS[3], ""))

    def test_duplicate_journal_open_site_refused(self):
        with self.assertRaisesRegex(ValueError, "anchor changed"):
            self.generate(COMPOSED.replace(joint.PRIVATE_FILE_OPENERS[2],
                                          joint.PRIVATE_FILE_OPENERS[2] * 2))

    def test_rejects_unpinned_source(self):
        with self.assertRaisesRegex(ValueError, "exact original"):
            joint.instrument(INPUT)

    def test_frame_transform_called_before_gpu_transform(self):
        calls = []
        def first(data):
            self.assertEqual(data, INPUT)
            calls.append("frame")
            return "after frame"
        def second(data):
            self.assertEqual(data, "after frame")
            calls.append("gpu")
            return COMPOSED
        with (
            patch.object(joint, "git_blob_sha1", return_value=joint.PINNED_SOURCE),
            patch.object(joint, "frame_instrument", side_effect=first),
            patch.object(joint, "gpu_instrument", side_effect=second)
        ):
            joint.instrument(INPUT)
        self.assertEqual(calls, ["frame", "gpu"])

    def test_drifted_journal_marker_refused(self):
        with self.assertRaisesRegex(ValueError, "anchor changed"):
            self.generate(COMPOSED.replace(joint.ORIGINAL_GPU_MARKER, ""))

    def test_missing_flush_guard_refused(self):
        with self.assertRaisesRegex(ValueError, "anchor changed"):
            self.generate(COMPOSED.replace(joint.RELEASE, ""))

    def test_duplicate_flush_guard_refused(self):
        with self.assertRaisesRegex(ValueError, "anchor changed"):
            self.generate(COMPOSED.replace(joint.RELEASE, joint.RELEASE * 2))

    def test_missing_frame_state_anchor_refused(self):
        with self.assertRaisesRegex(ValueError, "anchor changed"):
            self.generate(COMPOSED.replace(joint.FRAME_FUNCTION, ""))

    def test_duplicate_frame_state_anchor_refused(self):
        with self.assertRaisesRegex(ValueError, "anchor changed"):
            self.generate(COMPOSED.replace(joint.FRAME_FUNCTION,
                                           joint.FRAME_FUNCTION * 2))

    def test_missing_source_input_type_refused(self):
        with self.assertRaisesRegex(ValueError, "exact original"):
            joint.instrument("not bytes")

    def test_no_claim_of_authenticated_ps1_pixels(self):
        output = self.generate()
        self.assertNotIn("ps1_hardware_pixel_equivalence_verified = 1", output)
        self.assertNotIn("hd_replacement_authorized = 1", output)

    def test_explicit_disabled_normal_build(self):
        out = self.generate()
        self.assertIn(
            "#if defined(VH_MAP02_PRIVATE_FRAME_PIPE_TRACE) && !defined(VH_MAP02_GPU_CAPTURE)",
            out)


if __name__ == "__main__":
    unittest.main()
