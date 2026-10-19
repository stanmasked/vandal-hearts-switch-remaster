"""Synthetic image/payload regressions for the NeXium optical receipt."""
import importlib.util
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from PIL import Image

PATH=Path(__file__).resolve().parents[1]/"tools/decode_map02_guest_scene_trace.py"
spec=importlib.util.spec_from_file_location("map02_guest_trace", PATH)
tool=importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

def fixture(rows=None, dropped=0):
    if rows is None:
        rows=[]
        for serial,scene in ((1,2),(2,1)):
            for kind in (1,2,3,7,4,5):
                rows.append((kind,scene,serial,1000000+len(rows)*1000))
    buf=bytearray(924)
    buf[:8]=b"VHFBTRC1"
    buf[8]=len(rows)
    struct.pack_into("<I",buf,9,dropped)
    for i,(kind,scene,serial,clock) in enumerate(rows):
        struct.pack_into("<BBIQ",buf,13+i*14,kind,scene,serial,clock)
    struct.pack_into("<I",buf,909,zlib.crc32(buf[:909]))
    return bytes(buf)

def screenshot(path,packet):
    img=Image.new("RGB",(1280,720),(8,8,8))
    # Match all 7x7 modules including the magenta calibration border.
    from PIL import ImageDraw
    draw=ImageDraw.Draw(img)
    draw.rectangle((250,160,250+798-1,160+476-1),fill=(255,0,255))
    draw.rectangle((257,167,257+784-1,167+462-1),fill=(255,255,255))
    for bit in range(924*8):
        if packet[bit//8] & (0x80>>(bit%8)):
            x=257+(bit%112)*7
            y=167+(bit//112)*7
            draw.rectangle((x,y,x+6,y+6),fill=(0,0,0))
    img.save(path)

class TraceOpticalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.image=Path(self.tmp.name)/"receipt.png"

    def test_valid_pair_has_ticket_correlated_input_post_accept_and_pcm(self):
        screenshot(self.image,fixture())
        result=tool.audit_receipt(tool.decode_image(self.image),0)
        self.assertEqual(result["result"],"FIRST_PCM_PAGE_NONZERO_AND_SUBMITTED")
        self.assertEqual([x["serial"] for x in result["confirmed_transitions"]],[1,2])
        self.assertFalse(result["sample_aligned_guest_reverb_proven"])
        self.assertTrue(result["first_pre_submit_pcm_page_nonzero_verified"])

    def test_bad_crc_rejected(self):
        broken=bytearray(fixture())
        broken[40]^=1
        screenshot(self.image,broken)
        with self.assertRaisesRegex(ValueError,"CRC"):
            tool.decode_image(self.image)

    def test_optical_border_is_required(self):
        screenshot(self.image,fixture())
        img=Image.open(self.image)
        from PIL import ImageDraw
        ImageDraw.Draw(img).rectangle((250,160,1047,635),outline=(0,0,0),width=7)
        img.save(self.image)
        with self.assertRaisesRegex(ValueError,"border"):
            tool.decode_image(self.image)

    def test_nexium_letterboxed_viewport_calibration(self):
        screenshot(self.image,fixture())
        original=Image.open(self.image).convert("RGB")
        # Reproduce the actual 769x459 viewport from the NeXium log.
        image=Image.new("RGB",(1280,720),(9,9,12))
        crop=original.crop((250,160,1048,636))
        image.paste(crop.resize((769,459),Image.Resampling.NEAREST),(264,154))
        image.save(self.image)
        decoded=tool.decode_image(self.image)
        self.assertEqual(len(decoded["rows"]),12)
        self.assertEqual(tool.audit_receipt(decoded,1)["result"],
                         "FIRST_PCM_PAGE_NONZERO_AND_SUBMITTED")

    def test_missing_accept_is_rejected(self):
        rows=[]
        for serial,scene in ((1,2),(2,1)):
            for kind in (1,2,7,4,5) if serial==1 else (1,2,3,7,4,5):
                rows.append((kind,scene,serial,100000+1000*len(rows)))
        with self.assertRaisesRegex(ValueError,"ACCEPT"):
            tool.audit_receipt(tool.unpack(fixture(rows)),0)

    def test_cross_ticket_accept_does_not_count(self):
        rows=[]
        for serial,scene in ((1,2),(2,1)):
            for kind in (1,2,3,7,4,5):
                rows.append((kind,scene,1 if kind==3 and serial==2 else serial,
                            100000+1000*len(rows)))
        with self.assertRaisesRegex(ValueError,"ACCEPT"):
            tool.audit_receipt(tool.unpack(fixture(rows)),1)

    def test_missing_pcm_release_is_rejected(self):
        rows=[]
        for serial,scene in ((1,2),(2,1)):
            for kind in (1,2,3,7,4) if serial==2 else (1,2,3,7,4,5):
                rows.append((kind,scene,serial,100000+1000*len(rows)))
        with self.assertRaisesRegex(ValueError,"RELEASE_RETURN"):
            tool.audit_receipt(tool.unpack(fixture(rows)),0)

    def test_dropped_rows_rejected(self):
        with self.assertRaisesRegex(ValueError,"Incomplete"):
            tool.audit_receipt(tool.unpack(fixture(dropped=1)),0)

    def test_submit_error_rejected(self):
        rows=[]
        for serial,scene in ((1,2),(2,1)):
            for kind in (1,2,3,7,4,5):
                rows.append((kind,scene,serial,100000+1000*len(rows)))
        rows.append((6,1,2,200000))
        with self.assertRaisesRegex(ValueError,"failed"):
            tool.audit_receipt(tool.unpack(fixture(rows)),0)

    def test_missing_pre_submit_pcm_page_proof_is_rejected(self):
        rows=[]
        for serial,scene in ((1,2),(2,1)):
            for kind in (1,2,3,4,5) if serial==2 else (1,2,3,7,4,5):
                rows.append((kind,scene,serial,100000+1000*len(rows)))
        with self.assertRaisesRegex(ValueError,"PCM_PAGE_NONZERO"):
            tool.audit_receipt(tool.unpack(fixture(rows)),0)

    def test_explicit_silent_first_pcm_page_is_rejected(self):
        rows=[]
        for serial,scene in ((1,2),(2,1)):
            for kind in (1,2,3,8,4,5) if serial==1 else (1,2,3,7,4,5):
                rows.append((kind,scene,serial,100000+1000*len(rows)))
        with self.assertRaisesRegex(ValueError,"silent"):
            tool.audit_receipt(tool.unpack(fixture(rows)),1)

    def test_pcm_page_proof_from_wrong_ticket_is_rejected(self):
        rows=[]
        for serial,scene in ((1,2),(2,1)):
            for kind in (1,2,3,7,4,5):
                rows.append((kind,scene,serial+1 if kind==7 and serial==1 else serial,
                             100000+1000*len(rows)))
        with self.assertRaisesRegex(ValueError,"PCM_PAGE_NONZERO"):
            tool.audit_receipt(tool.unpack(fixture(rows)),0)

    def test_nonmonotonic_clock_rejected(self):
        rows=[]
        for serial,scene in ((1,2),(2,1)):
            for kind in (1,2,3,7,4,5):
                rows.append((kind,scene,serial,100000+1000*len(rows)))
        kind,scene,serial,_=rows[3]
        rows[3]=(kind,scene,serial,2)
        with self.assertRaisesRegex(ValueError,"Nonmonotonic"):
            tool.audit_receipt(tool.unpack(fixture(rows)),0)

if __name__=="__main__":
    unittest.main()
