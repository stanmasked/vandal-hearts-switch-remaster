"""Synthetic staged pair -> PutPixel promotion -> BlendG1 witness chain.

The original-PC VRAM/GTE verifier is mocked ONLY in this isolated fixture:
passing this test does not authenticate real original gameplay.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.promote_map02_putpixel_stage import promote_staged_putpixel
from tools.publish_map02_blendg1_witness import publish_blendg1_witness
from tools.verify_map02_blendg1_witness import verify_blendg1_witness


def as_lines(rows):
    return b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for row in rows
    )


class PairedPublishChainTests(unittest.TestCase):
    def test_complete_synthetic_chain_and_hash_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, native = base / "source", base / "native"
            source.mkdir(mode=0o700)
            native.mkdir(mode=0o700)
            p0 = {
                "stage": "native_putpixel", "step": 0, "frame": 17,
                "primitive_ordinal": 2, "primitive_type": 4,
                "x": 10, "y": 20, "before": 31, "front": 31744,
                "after": 992, "abr": 0, "semi": 1, "textured": 1,
                "accurate": 1,
            }
            p1 = dict(p0, step=1, before=992, front=16,
                      after=16, semi=0)
            blend = {
                "stage": "native_blendg1", "putpixel_step": 0,
                "frame": 17, "primitive_ordinal": 2, "primitive_type": 4,
                "x": 10, "y": 20, "accurate": 1, "abr": 0,
                "before": 31, "front": 31744, "after": 992,
                "blend_fg": 64512, "blend_bg": 31,
                "blend_result": 992,
            }
            pixels_raw, blend_raw = as_lines([p0, p1]), as_lines([blend])
            (native / "putpixel-native-events.pending.jsonl").write_bytes(pixels_raw)
            (native / "blendg1-native-events.pending.jsonl").write_bytes(blend_raw)
            source_manifest = {
                "schema": "vh.map02.native-putpixel-ot.v1",
                "source_frame": 17, "gpu_draw_frame": 17,
                "overdraw_manifest_sha256": "a" * 64,
                "native_events_sha256": "b" * 64,
                "putpixel_events_sha256":
                    hashlib.sha256(pixels_raw).hexdigest(),
            }
            (source / "gpu-putpixel-ot.json").write_bytes(
                as_lines([source_manifest]))
            verified = {"observed_native_putpixel_calls": 2}
            with (
                patch("tools.promote_map02_putpixel_stage.verify_pixel_ot",
                      return_value=verified),
                patch("tools.publish_map02_blendg1_witness.verify_pixel_ot",
                      return_value=verified),
                patch("tools.verify_map02_blendg1_witness.verify_pixel_ot",
                      return_value=verified),
            ):
                pixel_report = promote_staged_putpixel(source, native)
                blend_report = publish_blendg1_witness(source, native)
                final_report = verify_blendg1_witness(source, native)
            self.assertEqual(pixel_report["verified_native_putpixel_calls"], 2)
            self.assertEqual(blend_report["blendg1_events"], 1)
            self.assertEqual(final_report["observed_blendg1_putpixel_pairs"], 1)
            self.assertEqual(final_report["upstream_putpixel_calls"], 2)
            self.assertFalse(final_report["ps1_hardware_equivalence_proven"])
            self.assertFalse(final_report["original_gameplay_authenticated"])
            manifest = json.loads(
                (source / "gpu-blendg1-witness.json").read_bytes())
            self.assertEqual(
                manifest["putpixel_events_sha256"],
                hashlib.sha256(
                    (native / "putpixel-native-events.jsonl").read_bytes()
                ).hexdigest())
            self.assertEqual(
                manifest["blendg1_events_sha256"],
                hashlib.sha256(
                    (native / "blendg1-native-events.jsonl").read_bytes()
                ).hexdigest())


if __name__ == "__main__":
    unittest.main()
