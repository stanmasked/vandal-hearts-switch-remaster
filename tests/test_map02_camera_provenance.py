"""Asset-free tests for opt-in PC GTE camera snapshot and compiled replay."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.instrument_map02_camera import (
    GUARD, RENDER_START, RENDER_END, LIBGTE_ANCHOR,
    instrument_graphics, instrument_libgte, prepare,
)
from tools.verify_map02_camera_capture import parse_event, verify_capture

CAM = [4096,0,0, 0,4096,0, 0,0,4096,
       0,0,0, 160<<16,120<<16,256,256]

def record(z=8,x=19,visible=True):
    return {
        "stage":"camera_projection", "z":z, "x":x, "face":0,
        "path":"normal", "frame":25, "gfx":641 if visible else 643,
        "camera":CAM[:],
        "vertices": ([0,0,512, 100,0,512, 100,100,512, 0,100,512]
                     if visible else
                     [0,0,512, 0,100,512, 100,100,512, 100,0,512]),
        "nclip":2500 if visible else -2500,
        "visible":visible,
        "screen":[160,120, 210,120, 160,170, 210,170] if visible else None,
        "otz":128 if visible else None,
    }

def jsonl(*entries):
    return ("\n".join(json.dumps(x) for x in entries)+"\n").encode("utf-8")

def synthetic_graphics():
    return (
        '#include "PsyQ/gtemac.h"\n'
        + RENDER_START + '\n'
        + '   for (faceIdx=0;faceIdx<tileModel->faceCt;++faceIdx) {\n'
        + '      if (gfx != GFX_NULL) {\n'
        + '         pFaceVerts=tileModel->faces[faceIdx];\n'
        + '         gte_rtpt();\n'
        + '         gte_nclip();\n'
        + '         gte_stopz(&opz);\n'
        + '         if (opz > 0) {\n'
        + '            gte_rtps();\n'
        + '            gte_avsz4();\n'
        + '            gte_stotz(&otz);\n'
        + '         }\n'
        + '      }\n'
        + '   }\n'
        + '}\n' + RENDER_END + '\n}\n'
    )

class InstrumentCameraTests(unittest.TestCase):
    def test_trace_is_opt_in_and_limited_to_normal_renderer(self):
        updated=instrument_graphics(synthetic_graphics())
        before=updated[:updated.index(RENDER_END)]
        after=updated[updated.index(RENDER_END):]
        self.assertIn("VH_Map02CameraRegisters(vh_camera_registers);",before)
        self.assertIn("VH_Map02CameraEvent(tileModel, vh_camera_target, gfx,",before)
        self.assertEqual(before.count("VH_Map02CameraEvent(tileModel, vh_camera_target, gfx,"),2)
        self.assertNotIn("VH_Map02CameraEvent",after)
        self.assertIn('gState.mapNum != 11',updated)
        self.assertIn("vh_map02_camera_once[target] = 1;",updated)
        self.assertIn("if (vh_camera_target >= 0 && opz <= 0)",updated)
        self.assertIn("#if defined(PC_FEAT) && defined("+GUARD+")",updated)
        with self.assertRaisesRegex(ValueError,"already has camera"):
            instrument_graphics(updated)

    def test_libgte_reads_full_resident_matrix_not_debug_subset(self):
        data=LIBGTE_ANCHOR+"\n   return;\n}\n"
        edited=instrument_libgte(data)
        self.assertIn("g.rt.m[i][j]",edited)
        self.assertIn("g.tr[i]",edited)
        self.assertIn("g.ofx",edited)
        self.assertIn("g.ofy",edited)
        self.assertIn("g.h",edited)
        self.assertIn("g.zsf4",edited)
        self.assertIn("values[i * 3 + j]",edited)
        with self.assertRaisesRegex(ValueError,"already has camera"):
            instrument_libgte(edited)

    def test_fail_closed_on_modified_anchor(self):
        with self.assertRaisesRegex(ValueError,"unique pinned anchor"):
            instrument_libgte("void PC_GteDebugState(void){}")
        with self.assertRaisesRegex(ValueError,"unique pinned anchor"):
            instrument_graphics(synthetic_graphics().replace("gte_rtpt();","gte_rtps();"))
        with self.assertRaisesRegex(ValueError,"function boundaries"):
            instrument_graphics("void RenderMapTile() {}")

    def test_failure_never_creates_output_dir(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            (path/"src/core").mkdir(parents=True)
            (path/"platform/pc/src").mkdir(parents=True)
            (path/"src/core/graphics.c").write_text(synthetic_graphics())
            (path/"platform/pc/src/libgte.c").write_text(LIBGTE_ANCHOR)
            output=path/"out"
            with self.assertRaisesRegex(ValueError,"refusing changed pinned source"):
                prepare(path,output)
            self.assertFalse(output.exists())

class ReplayTests(unittest.TestCase):
    def test_matched_forward_cull_and_two_targets(self):
        result=verify_capture(jsonl(record(),record(11,11,False)))
        self.assertEqual(result["camera_projection_events"],2)
        self.assertEqual(result["visible_faces"],1)
        self.assertEqual(result["culled_faces"],1)
        self.assertEqual(len(result["source_sha256"]),64)
        self.assertTrue(result["pc_projection_matches_captured_gte"])
        self.assertFalse(result["original_game_pixels_verified"])
        self.assertFalse(result["ps1_hardware_gte_verified"])
        self.assertFalse(result["source_vertices_or_camera_emitted"])

    def test_screen_camera_nclip_and_otz_tampering_fails(self):
        for field, value in (
            ("screen",[161,120,210,120,160,170,210,170]),
            ("otz",127),
            ("nclip",2499),
            ("camera",CAM[:9]+[100]+CAM[10:]),
            ("vertices",[0,0,512, 90,0,512, 100,100,512, 0,100,512]),
        ):
            with self.subTest(field=field):
                bad=record()
                bad[field]=value
                with self.assertRaisesRegex(ValueError,"projection mismatch"):
                    verify_capture(jsonl(bad))

    def test_strict_types_and_sequencing(self):
        invalid=[
            {"frame":True},{"z":9},{"path":"edge"},{"face":1},
            {"visible":1},{"camera":CAM[:-1]},{"otz":True},
            {"screen":[0]*7},{"vertices":[0]*12},
            {"camera":CAM[:9]+[2**31]+CAM[10:]},
        ]
        for mutation in invalid:
            with self.subTest(mutation=mutation):
                bad=record();bad.update(mutation)
                with self.assertRaises(ValueError):
                    verify_capture(jsonl(bad))
        with self.assertRaisesRegex(ValueError,"duplicate target face"):
            verify_capture(jsonl(record(),record()))
        with self.assertRaisesRegex(ValueError,"expected camera_projection"):
            verify_capture(b'{"stage":"draw"}\n')
        with self.assertRaisesRegex(ValueError,"blank event"):
            verify_capture(jsonl(record())+b"\n")
        with self.assertRaisesRegex(ValueError,"over 2MiB"):
            verify_capture(b"a"*(2*1024*1024+1))
        with self.assertRaisesRegex(ValueError,"empty"):
            verify_capture(b"")

    def test_culled_polygon_cannot_claim_screen_or_otz(self):
        bad=record(11,11,False)
        bad["otz"]=0
        with self.assertRaisesRegex(ValueError,"must have null screen/OTZ"):
            parse_event(bad)
        good=record(11,11,False)
        good["nclip"]=1
        with self.assertRaisesRegex(ValueError,"contradicts original NCLIP"):
            parse_event(good)

if __name__=="__main__":
    unittest.main()
