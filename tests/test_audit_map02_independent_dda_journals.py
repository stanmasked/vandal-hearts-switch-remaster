"""Independent journals describe different DDA events, not proven pixels."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.audit_map02_independent_dda_journals import (
    audit, SPAN_FILE, CANDIDATE_FILE,
)
from tools.verify_map02_vram_timeline import VRAM_BYTES

SPAN = {
    "stage": "native_dda_span", "step": 0, "frame": 3,
    "primitive_ordinal": 9, "primitive_type": 2, "y": 12,
    "x_start": 10, "x_bound": 20, "clip_l": 5, "clip_r": 25,
    "clip_t": 10, "clip_b": 15,
}
CANDIDATE = {
    "stage": "rejected_edge_candidate", "step": 0, "frame": 3,
    "primitive_ordinal": 10, "reason": 4, "y": 12,
    "x_start": 10, "x_bound": 20, "clip_t": 13, "clip_b": 15,
}


def write(directory, filename, *rows):
    data = b"".join((json.dumps(row, sort_keys=True) + "\n").encode()
                    for row in rows)
    (directory / filename).write_bytes(data)
    return data


class IndependentJournalAuditTests(unittest.TestCase):
    def test_both_valid_journals_and_hashes_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            span_data = write(root, SPAN_FILE, SPAN)
            candidate_data = write(root, CANDIDATE_FILE, CANDIDATE)
            result = audit(root)
            self.assertEqual(result["schema"], "map02_independent_dda_journal_audit_v1")
            self.assertEqual(result["files"][SPAN_FILE]["sha256"],
                             hashlib.sha256(span_data).hexdigest())
            self.assertEqual(result["files"][CANDIDATE_FILE]["sha256"],
                             hashlib.sha256(candidate_data).hexdigest())
            self.assertEqual(result["shared_frame_ids"], [3])
            self.assertEqual(result["same_primitive_row_keys"], 0)
            self.assertTrue(result["single_sample_envelope_consistent"])
            self.assertEqual(result["dda_observation_mode"], "both")
            self.assertTrue(result["all_dda_journal_classes_observed"])
            for field in ("journal_origin_authenticated", "retail_map02_frame_verified",
                          "rejected_triangle_pixel_coverage_verified",
                          "hd_replacement_authorized"):
                self.assertIs(result[field], False)

    def test_candidate_only_is_missing_span_not_zero_span(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, CANDIDATE_FILE, CANDIDATE)
            result = audit(root)
            self.assertEqual(result["files"][CANDIDATE_FILE]["event_count"], 1)
            self.assertIsNone(result["files"][SPAN_FILE]["event_count"])
            self.assertFalse(result["files"][SPAN_FILE]["present"])
            self.assertEqual(result["dda_observation_mode"], "rejected_only")
            self.assertFalse(result["all_dda_journal_classes_observed"])
            self.assertEqual(result["shared_frame_ids"], [])

    def test_span_only_is_missing_candidate_not_zero_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, SPAN_FILE, SPAN)
            result = audit(root)
            self.assertIsNone(result["files"][CANDIDATE_FILE]["event_count"])
            self.assertFalse(result["files"][CANDIDATE_FILE]["present"])
            self.assertEqual(result["dda_observation_mode"], "entered_only")
            self.assertFalse(result["all_dda_journal_classes_observed"])

    def test_conflicting_executed_and_rejected_same_primitive_row_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, SPAN_FILE, SPAN)
            write(root, CANDIDATE_FILE, dict(CANDIDATE, primitive_ordinal=9))
            with self.assertRaisesRegex(ValueError, "entered and vertically rejected"):
                audit(root)

    def test_reject_mixed_frame_y_and_clip_window_in_joint_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, SPAN_FILE, SPAN)
            write(root, CANDIDATE_FILE, dict(CANDIDATE, y=9, clip_t=10))
            with self.assertRaisesRegex(ValueError, "mixed DDA capture"):
                audit(root)
            write(root, CANDIDATE_FILE, dict(CANDIDATE, frame=4))
            with self.assertRaisesRegex(ValueError, "mixed DDA capture"):
                audit(root)
            write(root, CANDIDATE_FILE, CANDIDATE,
                  dict(CANDIDATE, step=1, clip_t=14))
            with self.assertRaisesRegex(ValueError, "conflicting DDA clip window"):
                audit(root)

    def test_corruption_and_64_row_saturation_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, SPAN_FILE, SPAN)
            write(root, CANDIDATE_FILE, CANDIDATE)
            path = root / CANDIDATE_FILE
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
            with self.assertRaises(ValueError):
                audit(root)
            write(root, CANDIDATE_FILE,
                  *(dict(CANDIDATE, step=i) for i in range(64)))
            with self.assertRaises(ValueError):
                audit(root)

    def write_native_gpu(self, root, *, frame=3, primitive_type=2, draw_pairs=1):
        def event(index, phase):
            return {
                "stage": "native_vram", "step": index, "frame": frame,
                "phase": phase, "operation": "draw",
                "snapshot": f"gpu-{index:04d}-vram.bin",
                "rect": None, "dest": [0, 0], "rgb": [0, 0, 0],
                "primitive_type": primitive_type, "semi": 0,
                "window": [0, 0, 0, 0], "draw_mode": [0, 0, 0],
                "upload": "", "ft4": (
                    {"tpage":0, "clut":0,
                     "xy":[0,0,1,0,0,1,1,1],
                     "uv":[0,0,1,0,0,1,1,1]}
                    if primitive_type == 2 else None),
            }
        (root / "gpu-native-events.jsonl").write_bytes(
            b"".join((json.dumps(event(i, "before" if i % 2 == 0 else "after"))
                      + "\n").encode() for i in range(2 * draw_pairs)))
        empty_vram = bytes(VRAM_BYTES)
        for i in range(2 * draw_pairs):
            (root / f"gpu-{i:04d}-vram.bin").write_bytes(empty_vram)

    def test_verified_gpu_frame_and_primitive_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, SPAN_FILE, dict(SPAN, primitive_ordinal=0))
            write(root, CANDIDATE_FILE, dict(CANDIDATE, primitive_ordinal=1))
            self.write_native_gpu(root, draw_pairs=2)
            report = audit(root, native_frame=3)
            binding = report["native_gpu_binding"]
            self.assertTrue(binding["verified"])
            self.assertEqual(binding["frame"], 3)
            self.assertEqual(binding["native_gpu_pairs_verified"], 2)
            self.assertEqual(binding["draw_boundary_vram_checks"], 1)
            self.assertEqual(binding["draw_boundary_gpu_state_checks"], 1)
            zero_sha = hashlib.sha256(bytes(VRAM_BYTES)).hexdigest()
            self.assertEqual(
                binding["vram_snapshot_sha256_list_sha256"],
                hashlib.sha256((zero_sha * 4).encode("ascii")).hexdigest(),
            )
            self.assertEqual(binding["draw_primitives_in_bounded_capture"], 2)
            self.assertEqual(binding["observed_dda_primitive_keys"], 2)
            self.assertFalse(report["journal_origin_authenticated"])
            self.assertFalse(report["retail_map02_frame_verified"])
            self.assertFalse(report["hd_replacement_authorized"])

    def test_preframe_transfer_does_not_shift_draw_primitive_ordinal(self):
        # The native GPU log may start with Load/Move/ClearImage on the
        # preceding frame. The DDA primitive ordinal is counted only from
        # DrawOTag's walked primitives, not all GPU operation pairs.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, SPAN_FILE, dict(SPAN, primitive_ordinal=0))
            self.write_native_gpu(root)
            journal = root / "gpu-native-events.jsonl"
            draws = [json.loads(line) for line in journal.read_bytes().splitlines()]
            transfers = []
            for index, event in enumerate(draws):
                transfer = dict(event, step=index, frame=2,
                                snapshot=f"gpu-{index:04d}-vram.bin",
                                operation="clear", primitive_type=0,
                                rect=[0, 0, 1, 1], ft4=None)
                transfers.append(transfer)
                event["step"] = index + 2
                event["snapshot"] = f"gpu-{index+2:04d}-vram.bin"
                (root / event["snapshot"]).write_bytes(bytes(VRAM_BYTES))
            journal.write_bytes(b"".join(
                (json.dumps(event, sort_keys=True) + "\n").encode()
                for event in transfers + draws
            ))
            result = audit(root, native_frame=3)
            self.assertEqual(result["native_gpu_binding"]["native_gpu_pairs_verified"], 2)
            self.assertEqual(result["native_gpu_binding"]["draw_primitives_in_bounded_capture"], 1)
            self.assertEqual(result["native_gpu_binding"]["observed_dda_primitive_keys"], 1)
            # Reversing the order is impossible under the original
            # instrumented frame selectors, even with valid JSON and VRAM.
            reordered = draws + transfers
            for i, event in enumerate(reordered):
                event["step"] = i
                event["snapshot"] = f"gpu-{i:04d}-vram.bin"
            journal.write_bytes(b"".join(
                (json.dumps(event, sort_keys=True) + "\n").encode()
                for event in reordered
            ))
            with self.assertRaisesRegex(ValueError, "transfer appears after"):
                audit(root, native_frame=3)

    def test_wrong_ordinal_type_and_frame_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_native_gpu(root, draw_pairs=2)
            write(root, SPAN_FILE, SPAN)
            write(root, CANDIDATE_FILE, CANDIDATE)
            with self.assertRaisesRegex(ValueError, "ordinal"):
                audit(root, native_frame=3)
            write(root, SPAN_FILE, dict(SPAN, primitive_ordinal=0,
                                        primitive_type=3))
            write(root, CANDIDATE_FILE, dict(CANDIDATE, primitive_ordinal=1))
            with self.assertRaisesRegex(ValueError, "type"):
                audit(root, native_frame=3)
            write(root, SPAN_FILE, dict(SPAN, primitive_ordinal=0, frame=4))
            with self.assertRaisesRegex(ValueError, "frame"):
                audit(root, native_frame=3)
            with self.assertRaisesRegex(ValueError, "frame"):
                audit(root, native_frame=2)

    def test_missing_and_truncated_gpu_evidence_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, SPAN_FILE, dict(SPAN, primitive_ordinal=0))
            with self.assertRaisesRegex(ValueError, "gpu-native-events"):
                audit(root, native_frame=3)
            self.write_native_gpu(root)
            (root / "gpu-0001-vram.bin").write_bytes(b"\x00\x00")
            with self.assertRaisesRegex(ValueError, "wrong file size"):
                audit(root, native_frame=3)
            self.write_native_gpu(root)
            with self.assertRaises(ValueError):
                audit(root, native_frame=True)

    def test_native_gpu_log_mutated_after_vram_check_is_rejected(self):
        from tools.verify_map02_native_gpu_capture import verify_capture
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, SPAN_FILE, dict(SPAN, primitive_ordinal=0))
            self.write_native_gpu(root)

            def mutate_after_validation(directory, *, target_frame):
                report = verify_capture(directory, target_frame=target_frame)
                log = root / "gpu-native-events.jsonl"
                original = log.read_bytes()
                changed = original.replace(b'"primitive_type": 2',
                                           b'"primitive_type": 3', 1)
                self.assertNotEqual(original, changed)
                log.write_bytes(changed)
                return report

            with patch("tools.audit_map02_independent_dda_journals.verify_capture",
                       side_effect=mutate_after_validation):
                with self.assertRaisesRegex(ValueError, "bytes changed"):
                    audit(root, native_frame=3)

    def test_missing_and_symlinked_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "no native"):
                audit(root)
            write(root, SPAN_FILE, SPAN)
            (root / CANDIDATE_FILE).symlink_to(root / SPAN_FILE)
            with self.assertRaisesRegex(ValueError, "symlink"):
                audit(root)


if __name__ == "__main__":
    unittest.main()
