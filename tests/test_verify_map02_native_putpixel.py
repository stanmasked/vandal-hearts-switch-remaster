"""No assets: exact private native PutPixel event integrity and no-op accounting."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.verify_map02_native_putpixel import verify_pixel_calls

def row(i, before, front, after, semi=0, accurate=1):
    return {
        "stage":"native_putpixel","step":i,"x":32,"y":24,
        "before":before,"front":front,"after":after,"abr":1,
        "semi":semi,"textured":1,"accurate":accurate
    }

class NativePutPixelAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.rows=[
            row(0,0,0,0),
            row(1,0,0x001f,0x001f),
            row(2,0x001f,0x801f,0x801f,semi=1),
            row(3,0x801f,0x03e0,0x03e0),
            row(4,0x001f,0,0x001f,semi=1),
        ]
        # Textured accurate BlendG1 retains bit15. An untextured
        # zero-front blend is a legitimate unchanged BGR555 result.
        self.rows[4]["textured"] = 0
        self.save()

    def save(self):
        self.path=self.root/"putpixel-native-events.jsonl"
        self.path.write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in self.rows))

    def test_same_value_native_writes_and_blend_requests_not_guessed(self):
        r=verify_pixel_calls(self.root)
        self.assertEqual(r["native_putpixel_calls_observed"],5)
        self.assertEqual(r["opaque_copy_calls"],3)
        self.assertEqual(r["semi_transparent_blend_requests"],2)
        self.assertEqual(r["accurate_pc_blend_results_checked"],2)
        self.assertEqual(r["legacy_pc_blend_results_checked"],0)
        self.assertTrue(r["single_runtime_accurate_mode_consistent"])
        self.assertTrue(r["original_pc_writepixel_effects_verified"])
        self.assertEqual(r["same_color_write_calls_invisible_to_vram_delta"],2)
        self.assertEqual(r["changed_word_write_calls"],3)
        self.assertEqual(r["bit15_unset_to_set_calls"],1)
        self.assertEqual(r["bit15_set_to_unset_calls"],1)
        self.assertEqual(r["gaps_between_consecutive_sampled_calls"],1)
        self.assertEqual(r["accurate_gpu_mode_calls"],5)
        self.assertTrue(r["original_opaque_copy_invariant_checked"])
        self.assertFalse(r["blending_or_mask_hardware_accuracy_verified"])
        for key in ("no_unlogged_putpixel_calls_proven",
                    "no_raster_or_transparency_skip_proven",
                    "observations_matched_to_map02_faces",
                    "real_gameplay_authenticated", "raw_pixel_values_emitted"):
            self.assertFalse(r[key])
        public=json.dumps(r)
        for private in ("front","0x801f","\"x\"","\"y\"","before"):
            self.assertNotIn(private,public)

    def test_nonsemi_after_must_equal_native_front(self):
        self.rows[1]["after"]=0x7c00
        self.save()
        with self.assertRaisesRegex(ValueError,"opaque native WritePixel"):
            verify_pixel_calls(self.root)

    def test_accurate_and_legacy_semitransparent_forgery_rejected(self):
        # Both native source algorithms are replayed, even when the
        # submitted JSONL otherwise preserves all record ordering.
        self.assertEqual(verify_pixel_calls(self.root)[
            "semi_transparent_blend_requests"], 2)
        # The background already has maximum red (0x001f).
        # Adding only one red quantum would saturate to the *same*
        # expected result and cannot serve as a negative ABR1 vector.
        # Change the green channel instead; the output must differ.
        self.rows[2]["front"] = 0x03e0
        self.save()
        with self.assertRaisesRegex(ValueError, "semi-transparent native WritePixel"):
            verify_pixel_calls(self.root)
        self.rows[2]["front"] = 0x801f
        for entry in self.rows:
            entry["accurate"] = 0
        self.rows[2]["after"] = 0x001f
        self.save()
        legacy = verify_pixel_calls(self.root)
        self.assertEqual(legacy["legacy_pc_blend_results_checked"],2)
        self.assertEqual(legacy["accurate_pc_blend_results_checked"],0)
        self.rows[4]["after"] = 0x801f
        self.save()
        with self.assertRaisesRegex(ValueError, "semi-transparent native WritePixel"):
            verify_pixel_calls(self.root)

    def test_mixed_runtime_accurate_mode_rejected(self):
        # Pinned AccurateEnabled() is fixed after its first invocation.
        self.rows[4]["accurate"] = 0
        self.save()
        with self.assertRaisesRegex(ValueError, "inconsistent native AccurateEnabled"):
            verify_pixel_calls(self.root)

    def test_duplicate_noncontiguous_and_mutated_numeric_fields(self):
        self.rows[3]["step"]=2
        self.save()
        with self.assertRaisesRegex(ValueError,"noncontiguous"):
            verify_pixel_calls(self.root)
        self.rows[3]["step"]=3
        for field,value in (
            ("semi",2),("textured",-1),("accurate",True),
            ("abr",4),("front",65536),("x",-1),("y",512)
        ):
            with self.subTest(field=field):
                prior=self.rows[0][field]
                self.rows[0][field]=value
                self.save()
                with self.assertRaisesRegex(ValueError,"expected integer"):
                    verify_pixel_calls(self.root)
                self.rows[0][field]=prior

    def test_other_position_mixed_into_sample_refused(self):
        self.rows[-1]["y"]=25
        self.save()
        with self.assertRaisesRegex(ValueError,"mixed sampled pixel"):
            verify_pixel_calls(self.root)

    def test_duplicate_json_field_refused(self):
        self.path.write_text('{"step":0,"step":1}\n')
        with self.assertRaisesRegex(ValueError,"duplicate JSON field"):
            verify_pixel_calls(self.root)

    def test_private_file_required_and_symlink_rejected(self):
        self.path.unlink()
        with self.assertRaisesRegex(ValueError,"missing, linked"):
            verify_pixel_calls(self.root)
        self.path.symlink_to(self.root/"does-not-exist")
        with self.assertRaisesRegex(ValueError,"missing, linked"):
            verify_pixel_calls(self.root)
        self.path.unlink()
        self.save()
        self.path.write_bytes(b"X" * 20000)
        with self.assertRaisesRegex(ValueError,"exceeds cap"):
            verify_pixel_calls(self.root)

    def test_max_records_is_bounded_and_marked_incomplete(self):
        self.rows=[row(i,0,0,0) for i in range(64)]
        self.save()
        r=verify_pixel_calls(self.root)
        self.assertTrue(r["record_cap_reached"])
        self.assertEqual(r["same_color_write_calls_invisible_to_vram_delta"],64)
        self.rows.append(row(64,0,0,0))
        self.save()
        with self.assertRaisesRegex(ValueError,"record count invalid"):
            verify_pixel_calls(self.root)


if __name__=="__main__":
    unittest.main()
