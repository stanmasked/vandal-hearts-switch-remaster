"""ROM-free deterministic optical tests for audout pre-join atomic stage panel."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image,ImageDraw

path=Path(__file__).resolve().parents[1]/"tools/decode_map02_prejoin_stage.py"
spec=importlib.util.spec_from_file_location("prejoin_stage",path)
stage=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=stage
spec.loader.exec_module(stage)

def panel(phase=3,entered=11,returned=10,stop=1):
    bytes_=[0xa5,0x5a,phase,entered&255,entered>>8,
            returned&255,returned>>8,stop]
    crc=0
    for b in bytes_:crc^=b
    bytes_.extend((crc,crc^0xc3))
    im=Image.new("RGB",(1280,720),(0,0,0))
    d=ImageDraw.Draw(im)
    d.rectangle((244,154,335,265),fill=(255,0,255))
    d.rectangle((246,156,333,263),fill=(0,0,0))
    for row,n in enumerate(bytes_):
        for bit in range(8):
            x,y=250+10*bit,160+10*row
            d.rectangle((x,y,x+7,y+7),
                        fill=(255,255,255) if n&(1<<bit) else (0,0,0))
    return im

class PrejoinOpticalTests(unittest.TestCase):
    def read(self,im):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"stage.png"
            im.save(p)
            return stage.decode_image(p)

    def test_true_before_join_call_enter_without_return(self):
        result=self.read(panel(phase=3,entered=11,returned=10))
        self.assertEqual(result["stage_name"],"ENTERED_PLAYBUFFER")
        self.assertTrue(result["snapshot_before_blocking_thread_join"])
        self.assertEqual(result["audout_playbuffer_call_entries"],11)
        self.assertEqual(result["audout_playbuffer_call_returns"],10)
        self.assertFalse(result["audout_service_stall_proven"])
        self.assertFalse(result["audio_worker_deadlock_proven"])

    def test_cleanup_completed_is_not_speaker_audio_proof(self):
        result=self.read(panel(phase=6,entered=20,returned=20))
        self.assertEqual(result["stage_name"],"CLEANUP_COMPLETED")
        self.assertFalse(result["physical_switch_speaker_output_verified"])

    def test_missing_border_rejected(self):
        im=panel()
        im.putpixel((244,154),(0,0,0))
        with self.assertRaisesRegex(ValueError,"magenta"):
            self.read(im)

    def test_mutated_module_fails_checksum(self):
        im=panel()
        im.putpixel((250+4,160+3*10+4),(255,255,255))
        with self.assertRaisesRegex(ValueError,"checksum"):
            self.read(im)

    def test_return_count_cannot_exceed_enter(self):
        with self.assertRaisesRegex(ValueError,"phase or counters"):
            self.read(panel(phase=4,entered=5,returned=6))

    def test_malformed_canvas_dimensions_rejected(self):
        im=panel().resize((640,360))
        with self.assertRaisesRegex(ValueError,"1280x720"):
            self.read(im)

if __name__=="__main__":
    unittest.main()
