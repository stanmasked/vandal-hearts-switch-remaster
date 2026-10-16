#!/usr/bin/env python3
"""v52 fail-closed tests for ordered synthetic original-GPU evidence."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.verify_map02_overdraw_v52 import (
    SCENES,parse,audit,expected_sample,cross_worker,source_provenance,
    BadLayerEvidence
)

def scenario_lines(worker):
    lines=[]
    for name,(background,reverse,fixtures) in SCENES.items():
        order=list(reversed(range(len(fixtures)))) if reverse else list(range(len(fixtures)))
        for seq,idx in enumerate(order):
            depth,raw,semi,abr,dither,mx,my,ox,oy,u,v=fixtures[idx]
            eu=(u&~(mx*8))|((ox&mx)*8)
            ev=(v&~(my*8))|((oy&my)*8)
            ppw=4 if depth==0 else 2 if depth==1 else 1
            tpage=5+(depth<<7)
            tx=(tpage&15)*64+eu//ppw
            ty=((tpage>>4)&1)*256+ev
            index=-1 if depth==2 else idx+1 if depth==0 else idx+32
            word=raw if depth==2 else index*0x1111 if depth==0 else index*0x0101
            palx=-1 if index<0 else (31978&63)*16+index
            paly=-1 if index<0 else 31978>>6
            palette=0 if index<0 else raw
            parts={
                "scene":name,"seq":seq,"source":idx,"depth":depth,"tpage":tpage,
                "clut":31978,"u":u,"v":v,"maskx":mx,"masky":my,
                "offx":ox,"offy":oy,"tx":tx,"ty":ty,"word":word,
                "index":index,"palx":palx,"paly":paly,"palette":palette,
                "raw":raw,"semi":semi,"abr":abr,"dither":dither
            }
            lines.append("V52L "+" ".join(k+"="+str(v) for k,v in parts.items()))
        native=expected_sample(name,88,88)
        hires=expected_sample(name,177,176)
        details={
            "scene":name,"layers":len(order),"reverse":int(reverse),"workers":worker,
            "background":background,"native":native,"direct":hires,"deferred":hires,
            "x":88,"y":88,"hx":177,"hy":176,
            "directhash":"1234567890abcdef","deferredhash":"1234567890abcdef","pixels":1024
        }
        lines.append("V52RESULT "+" ".join(k+"="+str(v) for k,v in details.items()))
    return lines

class OrderedOriginalGpuTests(unittest.TestCase):
    def check(self,edits=None):
        values=scenario_lines(2)
        if edits:
            values=edits(values)
        return audit(values,2)
    def test_complete_all_five_scenes(self):
        r=self.check()
        self.assertEqual(r["status"],"verified_synthetic_layered_GPU")
        self.assertEqual(r["scene_count"],5)
        self.assertEqual(r["actual_gpu_layer_submissions"],25)
        self.assertTrue(r["order_sensitive_pair_different"])
        self.assertFalse(r["HD_replacement_approved"])
    def test_1_2_4_worker_reports_agree(self):
        reports={w:audit(scenario_lines(w),w) for w in (1,2,4)}
        self.assertEqual(cross_worker(reports)["status"],"verified")
    def test_wrong_layer_source_index_rejected(self):
        def edit(r):
            r[0]=r[0].replace("source=0","source=1")
            return r
        self.assertEqual(self.check(edit)["status"],"refused")
    def test_wrong_sequence_index_rejected(self):
        def edit(r):
            r[1]=r[1].replace("seq=1","seq=4")
            return r
        self.assertEqual(self.check(edit)["status"],"refused")
    def test_wrong_ABR_rejected(self):
        def edit(r):
            r[1]=r[1].replace("abr=0","abr=1")
            return r
        self.assertEqual(self.check(edit)["status"],"refused")
    def test_wrong_source_palette_rejected(self):
        def edit(r):
            r[1]=r[1].replace("palette=33760","palette=0")
            return r
        self.assertEqual(self.check(edit)["status"],"refused")
    def test_wrong_4bpp_nibble_rejected(self):
        def edit(r):
            r[0]=r[0].replace("word=4369","word=0")
            return r
        self.assertEqual(self.check(edit)["status"],"refused")
    def test_wrong_window_mask_rejected(self):
        def edit(r):
            for i,row in enumerate(r):
                if row.startswith("V52L scene=window_interleave seq=0"):
                    r[i]=row.replace("maskx=1","maskx=0")
                    break
            return r
        self.assertEqual(self.check(edit)["status"],"refused")
    def test_wrong_composited_native_pixel_rejected(self):
        def edit(r):
            for i,row in enumerate(r):
                if row.startswith("V52RESULT scene=abr_chain"):
                    val=expected_sample("abr_chain",88,88)
                    r[i]=row.replace("native="+str(val),"native="+str(val^1))
                    break
            return r
        self.assertEqual(self.check(edit)["status"],"refused")
    def test_wrong_hd_deferred_pixel_rejected(self):
        def edit(r):
            for i,row in enumerate(r):
                if row.startswith("V52RESULT scene=mixed_stp"):
                    val=expected_sample("mixed_stp",177,176)
                    r[i]=row.replace("deferred="+str(val),"deferred="+str(val^1))
                    break
            return r
        self.assertEqual(self.check(edit)["status"],"refused")
    def test_corrupt_full_HD_hash_rejected(self):
        def edit(r):
            for i,row in enumerate(r):
                if row.startswith("V52RESULT scene=mixed_stp"):
                    r[i]=row.replace("deferredhash=1234567890abcdef","deferredhash=1234567890abcdee")
                    break
            return r
        self.assertEqual(self.check(edit)["status"],"refused")
    def test_worker_count_mismatch_rejected(self):
        def edit(r):
            return [x.replace("workers=2","workers=4") for x in r]
        self.assertEqual(self.check(edit)["status"],"refused")
    def test_missing_synthetic_scene_refused(self):
        def edit(r):
            return [x for x in r if "scene=abr_chain" not in x]
        self.assertEqual(self.check(edit)["status"],"refused")
    def test_duplicate_original_scene_refused(self):
        def edit(r):
            return r+[r[5]]
        self.assertEqual(self.check(edit)["status"],"refused")
    def test_missing_source_layer_refused(self):
        def edit(r):
            return r[1:]
        self.assertEqual(self.check(edit)["status"],"refused")
    def test_missing_worker_report_refused(self):
        reports={w:audit(scenario_lines(w),w) for w in (1,2)}
        self.assertEqual(cross_worker(reports)["status"],"refused")
    def test_worker_output_divergence_refused(self):
        reports={w:audit(scenario_lines(w),w) for w in (1,2,4)}
        reports[4]["scenes"]["mixed_stp"]["hires"]^=1
        self.assertEqual(cross_worker(reports)["status"],"refused")
    def test_bad_hash_record_refused(self):
        with self.assertRaises(BadLayerEvidence):
            parse("V52RESULT scene=mixed_stp directhash=ggg")
    def test_parser_rejects_unknown_fields(self):
        with self.assertRaises(BadLayerEvidence):
            parse(scenario_lines(1)[0]+" extra=1")
    def test_draw_order_has_measurable_effect(self):
        self.assertNotEqual(expected_sample("mixed_stp",88,88),
                            expected_sample("mixed_reversed",88,88))
    def test_synthetic_scene_count_fixed(self):
        self.assertEqual(len(SCENES),5)
        self.assertTrue(all(len(x[2])==5 for x in SCENES.values()))
if __name__=="__main__":unittest.main()
