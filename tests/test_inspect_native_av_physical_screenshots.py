"""Host-only fabricated PNGs test the pixel reader, NEVER HOME itself."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from inspect_native_av_physical_screenshots import (
    BACKGROUND, BLUE, RED, YELLOW, inspect, observe_frame,
)


def frame(*, b=0, f=0, r=0, p=False, x="yellow", y="yellow", n="blue"):
    image=Image.new("RGB",(1280,720),BACKGROUND)
    draw=ImageDraw.Draw(image)
    colors={"blue":BLUE,"yellow":YELLOW,"red":RED,"not_present":BACKGROUND}
    states=(n,"blue" if b else "yellow","blue" if f else "yellow",
            "blue" if p else "yellow","blue" if r else "yellow")
    for i,color in enumerate(states):
        left=1000+i*48
        draw.rectangle((left,635,left+39,660),fill=colors[color])
    for i,cnt in ((1,b),(2,f),(4,r)):
        for stroke in range(min(cnt,5)):
            xx=1004+i*48+stroke*7
            draw.rectangle((xx,667,xx+3,675),fill=BLUE)
    for xx,code in ((1105,x),(1160,y)):
        if code!="not_present":
            draw.rectangle((xx,696,xx+39,710),fill=colors[code])
    return image


class PhysicalScreenshotPixelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.a=Path(self.tmp.name)/"before.png"
        self.b=Path(self.tmp.name)/"after.png"

    def images(self,before,after):
        before.save(self.a)
        after.save(self.b)
        return inspect(self.a,self.b)

    def cli(self,*flags):
        return subprocess.run(
            [sys.executable,"tests/inspect_native_av_physical_screenshots.py",
             str(self.a),str(self.b),*flags],
            capture_output=True,text=True)

    def test_two_image_focus_cycle_pixels_and_disclaimers(self):
        out=self.images(frame(),frame(b=1,f=1,p=True))
        self.assertTrue(out["difference"]["new_focus_cycle_pixels"])
        self.assertEqual(out["difference"]["increment"]["B"],"observed")
        self.assertEqual(out["difference"]["increment"]["F"],"observed")
        for key in ("physical_hardware_verified","home_event_verified",
                    "audible_audio_verified"):
            self.assertIs(out[key],False)
        accepted=self.cli("--require-focus-pixels")
        self.assertEqual(accepted.returncode,0,accepted.stderr)

    def test_second_cycle_requires_fresh_pcm_marker(self):
        first=frame(b=1,f=1,p=True)
        pending=frame(b=2,f=2,p=False)
        out=self.images(first,pending)
        self.assertFalse(out["difference"]["new_focus_cycle_pixels"])
        denied=self.cli("--require-focus-pixels")
        self.assertNotEqual(denied.returncode,0)
        out=self.images(first,frame(b=2,f=2,p=True))
        self.assertTrue(out["difference"]["new_focus_cycle_pixels"])

    def test_repeated_bf_without_count_change_cannot_fake_a_cycle(self):
        out=self.images(frame(b=1,f=1,p=True),frame(b=1,f=1,p=True))
        self.assertFalse(out["difference"]["new_focus_cycle_pixels"])
        self.assertEqual(out["difference"]["increment"]["B"],"not_observed")
        self.assertEqual(out["difference"]["increment"]["F"],"not_observed")

    def test_saturated_five_strokes_are_inconclusive(self):
        out=self.images(frame(b=5,f=5,p=True),frame(b=8,f=7,p=True))
        self.assertFalse(out["difference"]["new_focus_cycle_pixels"])
        self.assertEqual(out["difference"]["increment"]["B"],
                         "saturated_or_unchanged")
        self.assertEqual(out["after"]["tallies_capped_at_five"]["B"],5)

    def test_actual_x_y_pixels_without_false_audibility_claims(self):
        before=frame(b=1,f=1,p=True,x="yellow",y="yellow")
        out=self.images(before,frame(b=1,f=1,p=True,x="blue",y="yellow"))
        self.assertTrue(out["difference"]["new_x_return_pixels"])
        self.assertEqual(out["after"]["variant_pixels"],"focus_manual")
        self.assertFalse(out["difference"]["new_y_return_pixels"])
        self.assertEqual(self.cli("--require-x-return-pixels").returncode,0)
        self.assertNotEqual(self.cli("--require-y-return-pixels").returncode,0)
        out=self.images(before,frame(b=1,f=1,p=True,x="blue",y="blue"))
        self.assertTrue(out["difference"]["new_y_return_pixels"])
        self.assertEqual(self.cli("--require-y-return-pixels").returncode,0)
        self.assertFalse(out["audible_audio_verified"])

    def test_terminal_red_manual_error_cannot_turn_into_success(self):
        for label, initial, later in (
            ("X", frame(x="red"), frame(x="blue")),
            ("Y", frame(y="red"), frame(y="yellow")),
        ):
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                        ValueError,"terminal " + label + " error changed"):
                    self.images(initial,later)
                self.assertNotEqual(
                    self.cli("--require-x-return-pixels").returncode,0)
                self.assertNotEqual(
                    self.cli("--require-y-return-pixels").returncode,0)

    def test_other_manual_result_cannot_turn_blue_after_terminal_failure(self):
        # X/Y share one audio thread. Once a red status is already
        # visible, no new returned PCM can be reported by its sibling.
        for failed, before, after in (
            ("X", frame(x="red",y="yellow"), frame(x="red",y="blue")),
            ("Y", frame(x="yellow",y="red"), frame(x="blue",y="red")),
        ):
            with self.subTest(failed=failed):
                with self.assertRaisesRegex(
                        ValueError,"PCM return after terminal manual error"):
                    self.images(before,after)
                self.assertNotEqual(
                    self.cli("--require-x-return-pixels").returncode,0)
                self.assertNotEqual(
                    self.cli("--require-y-return-pixels").returncode,0)
        # Earlier confirmed success stays blue without representing a
        # new return after failure. It must not be falsely rejected.
        out=self.images(frame(x="red",y="blue"),
                        frame(x="red",y="blue"))
        self.assertFalse(out["difference"]["new_x_return_pixels"])
        self.assertFalse(out["difference"]["new_y_return_pixels"])

    def test_notification_mode_cannot_flip_in_one_nro_session(self):
        for previous, current in (("red","blue"),("blue","red")):
            with self.subTest(previous=previous,current=current):
                with self.assertRaisesRegex(
                        ValueError,"notification-mode indicator changed"):
                    self.images(frame(n=previous),frame(n=current))
                self.assertNotEqual(
                    self.cli("--require-focus-pixels").returncode,0)
        # A red N may be compared with itself for observation, but no
        # HOME/focus cycle can be certified when notification mode failed.
        out=self.images(frame(n="red"),frame(n="red",b=1,f=1,p=True))
        self.assertFalse(out["difference"]["new_focus_cycle_pixels"])

    def test_reject_nonuniform_shades_within_one_palette_class(self):
        image=frame(b=1)
        # Both RGB values are individually close enough to BLUE to be
        # classified as blue, but the solid-color fill is inconsistent.
        image.putpixel((1051,637),(BLUE[0]+20,BLUE[1],BLUE[2]))
        with self.assertRaisesRegex(
                ValueError,"inconsistent B tile shades"):
            observe_frame(image)
        tally=frame(b=1)
        tally.putpixel((1052,667),(BLUE[0]+20,BLUE[1],BLUE[2]))
        with self.assertRaisesRegex(
                ValueError,"inconsistent B tally tile shades"):
            observe_frame(tally)

    def test_small_uniform_capture_noise_is_accepted(self):
        image=frame(b=1)
        image.putpixel((1051,637),(BLUE[0]+3,BLUE[1]-2,BLUE[2]))
        self.assertEqual(observe_frame(image)["indicators"]["B"],"blue")

    def test_old_blue_x_is_not_a_new_x_confirmation(self):
        out=self.images(frame(x="blue"),frame(x="blue"))
        self.assertFalse(out["difference"]["new_x_return_pixels"])

    def test_mixing_focus_and_manual_nros_cannot_fake_any_outcome(self):
        focus_only=frame(x="not_present",y="not_present")
        manual_after=frame(b=1,f=1,p=True,x="blue",y="blue")
        with self.assertRaisesRegex(ValueError,"different focus NRO variants"):
            self.images(focus_only,manual_after)
        self.assertNotEqual(
            self.cli("--require-focus-pixels").returncode,0)
        self.assertNotEqual(
            self.cli("--require-x-return-pixels").returncode,0)
        self.assertNotEqual(
            self.cli("--require-y-return-pixels").returncode,0)
        with self.assertRaisesRegex(ValueError,"different focus NRO variants"):
            self.images(manual_after,focus_only)

    def test_core_focus_indicators_must_be_present_and_recognized(self):
        for label, x_coord in (("N",1020),("B",1068),("F",1116),
                               ("P",1164),("R",1212)):
            with self.subTest(label=label):
                missing=frame(x="not_present",y="not_present")
                ImageDraw.Draw(missing).rectangle(
                    (x_coord-20,635,x_coord+19,660),fill=BACKGROUND)
                with self.assertRaisesRegex(
                    ValueError,"missing or ambiguous " + label):
                    observe_frame(missing)
                unknown=frame()
                ImageDraw.Draw(unknown).rectangle(
                    (x_coord-20,635,x_coord+19,660),fill=(127,127,127))
                with self.assertRaisesRegex(
                    ValueError,"missing or ambiguous " + label):
                    observe_frame(unknown)
        valid_n_failure=observe_frame(frame(n="red"))
        self.assertEqual(valid_n_failure["indicators"]["N"],"red")
        self.assertEqual(valid_n_failure["variant_pixels"],"focus_manual")

    def test_partial_manual_tiles_fail_closed(self):
        for x,y in (("not_present","yellow"),
                    ("blue","not_present"),
                    ("not_present","red"),
                    ("unknown","blue")):
            if x=="unknown":
                image=frame(x="yellow",y=y)
                ImageDraw.Draw(image).rectangle(
                    (1105,696,1144,710),fill=(127,127,127))
            else:
                image=frame(x=x,y=y)
            with self.subTest(x=x,y=y):
                with self.assertRaisesRegex(
                        ValueError,"incomplete or ambiguous X/Y"):
                    observe_frame(image)

    def test_both_focus_only_frames_are_accepted_as_pixel_observations(self):
        before=frame(x="not_present",y="not_present")
        after=frame(b=1,f=1,p=True,x="not_present",y="not_present")
        out=self.images(before,after)
        self.assertEqual(out["before"]["variant_pixels"],"focus")
        self.assertEqual(out["after"]["variant_pixels"],"focus")
        self.assertTrue(out["difference"]["new_focus_cycle_pixels"])
        self.assertFalse(out["difference"]["new_x_return_pixels"])
        self.assertEqual(self.cli("--require-focus-pixels").returncode,0)

    def test_no_manual_tiles_cannot_look_like_manual_return(self):
        out=self.images(frame(x="not_present",y="not_present"),
                        frame(x="not_present",y="not_present"))
        self.assertEqual(out["after"]["indicators"]["X"],"not_present")
        self.assertFalse(out["difference"]["new_y_return_pixels"])

    def test_reject_inconsistent_or_noncontiguous_tally(self):
        broken=frame(b=1)
        ImageDraw.Draw(broken).rectangle(
            (1052,667,1055,675),fill=BACKGROUND)
        with self.assertRaisesRegex(ValueError,"blue without any event strokes"):
            observe_frame(broken)
        broken=frame(b=2)
        ImageDraw.Draw(broken).rectangle(
            (1052,667,1055,675),fill=BACKGROUND)
        with self.assertRaisesRegex(ValueError,"non-contiguous"):
            observe_frame(broken)

    def test_blue_pcm_requires_matched_unsaturated_focus_tallies(self):
        # B can legitimately lead F while the app is in the background,
        # but P cannot be blue until the paired foreground return occurs.
        for b,f in ((2,1),(5,4)):
            with self.subTest(b=b,f=f):
                with self.assertRaisesRegex(
                        ValueError,"post-return PCM marker has unmatched B/F"):
                    observe_frame(frame(b=b,f=f,p=True))
        # When F is absent entirely, the older missing-pair guard
        # triggers first, before count equality is considered.
        with self.assertRaisesRegex(ValueError,"has no B/F pair"):
            observe_frame(frame(b=1,f=0,p=True))
        # Pending state remains an admissible observation, not proof.
        self.assertEqual(
            observe_frame(frame(b=2,f=1,p=False))["indicators"]["P"],
            "yellow")
        # After saturation, 5/5 means 5+ each: equality cannot be
        # established from pixels, so never invent an exact count.
        self.assertEqual(
            observe_frame(frame(b=7,f=6,p=True))[
                "tallies_capped_at_five"]["B"],5)
        self.assertEqual(
            observe_frame(frame(b=2,f=2,p=True))["indicators"]["P"],
            "blue")

    def test_unpaired_return_pixels_cannot_certify_focus_cycle(self):
        before=frame()
        after=frame(b=2,f=1,p=True)
        with self.assertRaisesRegex(
                ValueError,"post-return PCM marker has unmatched B/F"):
            self.images(before,after)
        self.assertNotEqual(self.cli("--require-focus-pixels").returncode,0)

    def test_reject_foreground_count_greater_than_background(self):
        with self.assertRaisesRegex(ValueError, "foreground tally exceeds"):
            observe_frame(frame(b=1,f=2))
        with self.assertRaisesRegex(ValueError, "foreground tally exceeds"):
            self.images(frame(),frame(b=2,f=3,p=True))
        # Saturated B=5 means 5 or more: cannot infer a contradiction.
        self.assertEqual(observe_frame(frame(b=5,f=5))[
            "tallies_capped_at_five"]["B"],5)

    def test_reject_partial_tile_and_tally_pixel_corruption(self):
        # A valid-looking center pixel does not override disagreeing
        # interior samples of a flat UI indicator.
        for label,point in (
            ("N",(1005,640)), ("B",(1053,640)),
            ("F",(1101,640)), ("P",(1149,640)),
            ("R",(1197,640)), ("X",(1110,699)),
            ("Y",(1165,699))):
            with self.subTest(label=label):
                corrupt=frame(b=1,f=1,p=True)
                corrupt.putpixel(point,(127,127,127))
                with self.assertRaisesRegex(
                    ValueError,"inconsistent " + label + " tile pixels"):
                    observe_frame(corrupt)
        tally=frame(b=1)
        tally.putpixel((1053,669),BACKGROUND)
        with self.assertRaisesRegex(
            ValueError,"inconsistent B tally tile pixels"):
            observe_frame(tally)

    def test_reject_damage_outside_original_three_pixel_probes(self):
        # A single changed pixel anywhere in the solid interior must
        # defeat an otherwise correct-looking three-point sample.
        locations=(
            ("N",(1002,638)), ("B",(1050,638)),
            ("F",(1098,638)), ("P",(1146,638)),
            ("R",(1194,638)), ("X",(1107,698)),
            ("Y",(1162,698)),
        )
        for label,point in locations:
            with self.subTest(tile=label):
                image=frame(b=1,f=1,p=True)
                image.putpixel(point,(127,127,127))
                with self.assertRaisesRegex(
                    ValueError,"inconsistent " + label + " tile pixels"):
                    observe_frame(image)
        # The edge of a 4x9 tally stroke was outside the old probes.
        image=frame(b=1)
        image.putpixel((1052,667),BACKGROUND)
        with self.assertRaisesRegex(
            ValueError,"inconsistent B tally tile pixels"):
            observe_frame(image)

    def test_report_binds_exact_png_bytes_and_is_exclusive(self):
        frame().save(self.a)
        frame(b=1,f=1,p=True).save(self.b)
        report_path=Path(self.tmp.name)/"pixel-report.json"
        result=self.cli("--require-focus-pixels",
                        "--report-out",str(report_path))
        self.assertEqual(result.returncode,0,result.stderr)
        bound=json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(bound,json.loads(result.stdout))
        self.assertEqual(
            bound["format"],
            "vh-av-physical-screenshot-pixel-observation-v2")
        self.assertEqual(bound["source_png_sha256"],{
            "before":hashlib.sha256(self.a.read_bytes()).hexdigest(),
            "after":hashlib.sha256(self.b.read_bytes()).hexdigest(),
        })
        self.assertFalse(bound["physical_hardware_verified"])
        self.assertFalse(bound["audible_audio_verified"])
        self.assertEqual(self.cli("--report-out",str(report_path)).returncode,2)
        # Editing non-status pixels must change the byte identity, even
        # when the visible status classification remains unchanged.
        altered=frame(b=1,f=1,p=True)
        altered.putpixel((40,40),(99,77,55))
        altered.save(self.b)
        self.assertNotEqual(
            bound["source_png_sha256"]["after"],
            hashlib.sha256(self.b.read_bytes()).hexdigest())

    def test_failed_gate_does_not_create_a_bound_report(self):
        frame().save(self.a)
        frame().save(self.b)
        report_path=Path(self.tmp.name)/"rejected-report.json"
        denied=self.cli("--require-focus-pixels",
                        "--report-out",str(report_path))
        self.assertNotEqual(denied.returncode,0)
        self.assertFalse(report_path.exists())
        # Backwards-compatible stdout remains the unbound v1 format.
        accepted=self.cli()
        self.assertEqual(accepted.returncode,0,accepted.stderr)
        unbound=json.loads(accepted.stdout)
        self.assertEqual(
            unbound["format"],
            "vh-av-physical-screenshot-pixel-observation-v1")
        self.assertNotIn("source_png_sha256",unbound)

    def test_optional_nro_report_out_records_exact_binary_digest(self):
        binary=Path(self.tmp.name)/"probe.nro"
        data=bytearray(0x100)
        data[0x10:0x14]=b"NRO0"
        data[0x18:0x1c]=(0x100).to_bytes(4,"little")
        for header,segment in ((0x20,0x80),(0x28,0x90),(0x30,0xa0)):
            data[header:header+4]=segment.to_bytes(4,"little")
            data[header+4:header+8]=(0x10).to_bytes(4,"little")
        binary.write_bytes(data)
        frame().save(self.a)
        frame(b=1,f=1,p=True).save(self.b)
        report_path=Path(self.tmp.name)/"nro-bound.json"
        result=self.cli("--report-out",str(report_path),"--nro",str(binary))
        self.assertEqual(result.returncode,0,result.stderr)
        bound=json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(bound["format"],
                         "vh-av-physical-screenshot-pixel-observation-v3")
        self.assertEqual(bound["source_nro_sha256"],
                         hashlib.sha256(data).hexdigest())
        self.assertEqual(bound["source_nro_size_bytes"],len(data))
        self.assertFalse(bound["physical_hardware_verified"])
        self.assertFalse(bound["audible_audio_verified"])

    def test_nro_binding_requires_report_and_valid_header(self):
        binary=Path(self.tmp.name)/"wrong.nro"
        binary.write_bytes(b"garbage"*40)
        frame().save(self.a)
        frame().save(self.b)
        no_report=self.cli("--nro",str(binary))
        self.assertNotEqual(no_report.returncode,0)
        self.assertIn("requires a bound PNG report",no_report.stderr)
        report_path=Path(self.tmp.name)/"bad-nro.json"
        wrong=self.cli("--nro",str(binary),"--report-out",str(report_path))
        self.assertNotEqual(wrong.returncode,0)
        self.assertIn("recognizable NRO0",wrong.stderr)
        self.assertFalse(report_path.exists())

    def test_reject_transparent_rgba_hidden_status_pixels(self):
        image=frame().convert("RGBA")
        image.putpixel((1005,640),(*BLUE,0))
        image.save(self.a)
        frame().save(self.b)
        with self.assertRaisesRegex(ValueError,"fully opaque"):
            inspect(self.a,self.b)

    def test_reject_decreasing_counts_and_invalid_resolution(self):
        with self.assertRaisesRegex(ValueError,"tally decreased"):
            self.images(frame(b=2,f=2),frame(b=1,f=1))
        frame().resize((640,360)).save(self.a)
        frame().save(self.b)
        with self.assertRaisesRegex(ValueError,"unscaled"):
            inspect(self.a,self.b)

    def test_red_indicator_does_not_count_as_confirmed_return(self):
        out=self.images(frame(),frame(b=1,f=1,p=False,x="red"))
        self.assertEqual(out["after"]["indicators"]["X"],"red")
        self.assertFalse(out["difference"]["new_x_return_pixels"])
        self.assertFalse(out["difference"]["new_focus_cycle_pixels"])


if __name__=="__main__":
    unittest.main()
