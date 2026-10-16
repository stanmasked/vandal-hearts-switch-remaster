"""Asset-free, mutation-resistant local MAP02 frame-bundle validation tests."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from tools.verify_map02_frame_bundle import (
    MAP_BYTES, VRAM_BYTES, PINNED_PC_SOURCE, verify_bundle,
)

FRAME = 411
CAMERA = [4096,0,0, 0,4096,0, 0,0,4096,
          0,0,0, 20*65536,20*65536,256,256]
VERTICES = [[0,0,512],[100,0,512],[100,100,512],[0,100,512]]
SCREEN = [[20,20],[70,20],[70,70],[20,70]]

def sha(data):
    return hashlib.sha256(data).hexdigest()

def word(raw, x, y, value):
    struct.pack_into("<H",raw,((y*1024)+x)*2,value)

def event(z, x, tpage, clut, index, probe_color):
    source = dict(
        z=z, x=x, record_index=z*28+x, face_index=0,
        local_gfx=241, shade=7, indices=[0,1,2,3],
        vertices=copy.deepcopy(VERTICES))
    return {
        "stage":"map02_ft4_submit","frame":FRAME,"register_frame":FRAME,
        "source":source,
        "gte":{"camera":CAMERA[:],"perimeter_xy":copy.deepcopy(SCREEN),
               "nclip_mac0":2500,"raw_otz":128},
        "texture":{"u":240,"v":192,"w":15,"h":15,"tpage":tpage,"clut":clut,
                   "mask_x":0,"mask_y":0,"offset_x":0,"offset_y":0,
                   "probes":[{"u":240,"v":192,"bgr555":probe_color},
                             {"u":241,"v":192,"bgr555":probe_color}]}
    }

class FrameBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        mp=bytearray(MAP_BYTES)
        for z,x in ((8,19),(11,11)):
            start=(z*28+x)*304
            struct.pack_into("<h",mp,start+176,241)
            mp[start+284]=7
            mp[start+302]=1
            for i,xyz in enumerate(VERTICES):
                mp[start+212+i]=i
                struct.pack_into("<hhh",mp,start+i*8,*xyz)
        vr=bytearray(VRAM_BYTES)
        for y in range(192,208):
            for x in range(380,384):
                word(vr,x,y,0x1111)
            for x in range(508,512):
                word(vr,x,y,0x2222)
        # CLUT #31978: x=672, y=499, index 1 STP red.
        word(vr,673,499,0x801f)
        # CLUT #31979: x=688, y=499, index 2 blue.
        word(vr,690,499,0x7c00)
        self.map_bytes=bytes(mp)
        self.vram_bytes=bytes(vr)
        self.events=[
            event(8,19,5,31978,1,0x801f),
            event(11,11,7,31979,2,0x7c00)
        ]
        self.manifest={
            "schema":"vh.map02.frame.v1","frame":FRAME,
            "vram_snapshot_frame":FRAME,
            "ot_size":1024,
            "pc_source_commit":PINNED_PC_SOURCE,
            "decoded_map_sha256":sha(self.map_bytes),
            "vram_sha256":sha(self.vram_bytes),
        }
        self.write()

    def write(self):
        event_bytes=b"".join((json.dumps(e,sort_keys=True)+"\n").encode() for e in self.events)
        self.manifest["events_sha256"]=sha(event_bytes)
        (self.folder/"bundle.json").write_text(json.dumps(self.manifest),encoding="utf-8")
        (self.folder/"map02.decoded.bin").write_bytes(self.map_bytes)
        (self.folder/"gpu-vram-le.bin").write_bytes(self.vram_bytes)
        (self.folder/"gpu-events.jsonl").write_bytes(event_bytes)

    def test_two_source_faces_and_compiled_gte_vram_probes(self):
        result=verify_bundle(self.folder)
        self.assertEqual(result["submitted_faces_checked"],2)
        self.assertEqual(result["source_faces_matched"],2)
        self.assertEqual(result["compiled_pc_gte_matches"],2)
        self.assertEqual(result["vram_4bpp_crop_texels_checked"],512)
        self.assertEqual(result["recorded_vram_color_probes_checked"],4)
        self.assertTrue(result["all_inputs_have_matching_frame_labels"])
        self.assertFalse(result["retail_ps1_pixels_verified"])
        self.assertFalse(result["frame_capture_authenticated"])
        self.assertFalse(result["vram_unchanged_between_draws_proven"])
        self.assertFalse(result["input_game_bytes_printed"])
        summary=json.dumps(result,sort_keys=True)
        self.assertNotIn("perimeter_xy",summary)
        self.assertNotIn("vertices",summary)
        self.assertNotIn("0x801f",summary)

    def test_hashes_reject_changed_source_vram_and_events(self):
        for name in ("map02.decoded.bin","gpu-vram-le.bin","gpu-events.jsonl"):
            with self.subTest(name=name):
                self.write()
                path=self.folder/name
                raw=bytearray(path.read_bytes())
                raw[-1] ^= 1
                path.write_bytes(raw)
                with self.assertRaisesRegex(ValueError,"SHA-256 mismatch"):
                    verify_bundle(self.folder)

    def test_cross_frame_source_and_gte_mutations(self):
        mutations=(
            (0,"register_frame",FRAME+1,"register_frame disagrees"),
            (1,"frame",FRAME+1,"frame disagrees"),
        )
        for idx,field,value,error in mutations:
            with self.subTest(field=field):
                self.events[idx][field]=value
                self.write()
                with self.assertRaisesRegex(ValueError,error):
                    verify_bundle(self.folder)
                self.events[idx][field]=FRAME
        self.manifest["vram_snapshot_frame"]=FRAME+1
        self.write()
        with self.assertRaisesRegex(ValueError,"snapshot frame differs"):
            verify_bundle(self.folder)
        self.manifest["vram_snapshot_frame"]=FRAME

    def test_mutations_fail_independent_checks_after_rehash(self):
        mutations=[
            ("source","record_index",244,"record_index"),
            ("source","local_gfx",242,"GFX mismatch"),
            ("source","shade",8,"shade mismatch"),
            ("gte","nclip_mac0",2499,"GTE mismatch"),
            ("gte","raw_otz",127,"GTE mismatch"),
            ("texture","tpage",133,"unsupported texture"),
            ("texture","clut",-1,"clut"),
            ("texture","w",30,"w"),
        ]
        for section,field,value,reason in mutations:
            with self.subTest(section=section,field=field):
                saved=self.events[1][section][field]
                self.events[1][section][field]=value
                self.write()
                with self.assertRaisesRegex(ValueError,reason):
                    verify_bundle(self.folder)
                self.events[1][section][field]=saved
        saved=copy.deepcopy(self.events[1]["source"]["vertices"])
        self.events[1]["source"]["vertices"][1][0] += 1
        self.write()
        with self.assertRaisesRegex(ValueError,"vertex coordinates mismatch"):
            verify_bundle(self.folder)
        self.events[1]["source"]["vertices"]=saved
        self.events[1]["gte"]["perimeter_xy"][2][1]+=1
        self.write()
        with self.assertRaisesRegex(ValueError,"GTE mismatch"):
            verify_bundle(self.folder)
        self.events[1]["gte"]["perimeter_xy"][2][1]-=1
        self.events[1]["texture"]["probes"][0]["bgr555"]=0x03e0
        self.write()
        with self.assertRaisesRegex(ValueError,"texture probe disagrees"):
            verify_bundle(self.folder)

    def test_identical_gfx_does_not_hide_duplicate_source_key(self):
        self.events[1]["source"]=copy.deepcopy(self.events[0]["source"])
        self.write()
        with self.assertRaisesRegex(ValueError,"duplicate submitted source face"):
            verify_bundle(self.folder)

    def test_invalid_bundle_shape_and_private_file_security(self):
        self.manifest["pc_source_commit"]="0"*40
        self.write()
        with self.assertRaisesRegex(ValueError,"unpinned PC"):
            verify_bundle(self.folder)
        self.manifest["pc_source_commit"]=PINNED_PC_SOURCE
        self.manifest["pc_game_binary_sha256"]="abcd"
        self.write()
        with self.assertRaisesRegex(ValueError,"fingerprint"):
            verify_bundle(self.folder)
        self.manifest.pop("pc_game_binary_sha256")
        self.write()
        path=self.folder/"gpu-events.jsonl"
        path.unlink()
        path.symlink_to(self.folder/"bundle.json")
        with self.assertRaisesRegex(ValueError,"linked or non-regular"):
            verify_bundle(self.folder)
        path.unlink()
        self.write()
        bad=(b'{"schema":"vh.map02.frame.v1","schema":"duplicate"}')
        (self.folder/"bundle.json").write_bytes(bad)
        with self.assertRaisesRegex(ValueError,"duplicate JSON"):
            verify_bundle(self.folder)

    def test_unobserved_gpu_texel_probes_are_not_claimed(self):
        self.events[0]["texture"].pop("probes")
        self.events[1]["texture"].pop("probes")
        self.write()
        result=verify_bundle(self.folder)
        self.assertEqual(result["recorded_vram_color_probes_checked"],0)
        self.assertEqual(result["vram_4bpp_crop_texels_checked"],512)

if __name__=="__main__":
    unittest.main()
