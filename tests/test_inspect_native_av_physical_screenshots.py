"""Host-only fabricated PNGs test the pixel reader, NEVER HOME itself."""
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
        before=frame(b=1,f=1,p=True,x="red",y="red")
        after=frame(b=1,f=1,p=True,x="blue",y="blue")
        out=self.images(before,after)
        self.assertFalse(out["difference"]["new_x_return_pixels"])
        self.assertFalse(out["difference"]["new_y_return_pixels"])
        self.assertNotEqual(self.cli("--require-x-return-pixels").returncode,0)
        self.assertNotEqual(self.cli("--require-y-return-pixels").returncode,0)
        # Both still look like manual interface screenshots, but their
        # colors cannot establish a continuous successful run.
        self.assertEqual(out["before"]["variant_pixels"],"focus_manual")
        self.assertEqual(out["after"]["variant_pixels"],"focus_manual")

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
                for xx,yy in ((x_coord-15,640),(x_coord,645),
                              (x_coord+14,655)):
                    missing.putpixel((xx,yy),BACKGROUND)
                with self.assertRaisesRegex(
                    ValueError,"missing or ambiguous " + label):
                    observe_frame(missing)
                unknown=frame()
                for xx,yy in ((x_coord-15,640),(x_coord,645),
                              (x_coord+14,655)):
                    unknown.putpixel((xx,yy),(127,127,127))
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
                for point in ((1110,699),(1125,702),(1139,707)):
                    image.putpixel(point,(127,127,127))
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
        for point in ((1053,669),(1053,671),(1054,674)):
            broken.putpixel(point,BACKGROUND)
        with self.assertRaisesRegex(ValueError,"blue without any event strokes"):
            observe_frame(broken)
        broken=frame(b=2)
        for point in ((1053,669),(1053,671),(1054,674)):
            broken.putpixel(point,BACKGROUND)
        with self.assertRaisesRegex(ValueError,"non-contiguous"):
            observe_frame(broken)

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
