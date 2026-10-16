#!/usr/bin/env python3
"""Synthetic v79 timeline parser regressions: not original MAP02 evidence."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.verify_map02_v79_vblank_timeline import analyze, TraceError

def event(**kwargs):
    return json.dumps(kwargs)

def fixture():
    return [
        event(kind="vblank", seq=1, frame=10, cycle=100),
        event(kind="gp0", seq=2, word=0xe1000001),
        event(kind="vram_write", seq=3, x=5, y=6, value=42),
        event(kind="vblank", seq=4, frame=11, cycle=200),
        event(kind="snapshot", seq=5, edge_seq=4, x=5, y=6, value=42),
        event(kind="gp1", seq=6, word=0x01000000),
        event(kind="vblank", seq=7, frame=12, cycle=300),
    ]

class V79Timeline(unittest.TestCase):
    def test_attribution(self):
        r=analyze(fixture())
        self.assertEqual(r["vblank_edges"], 3)
        self.assertEqual(r["intervals"][0]["gp0_words"], [0xe1000001])
        self.assertEqual(r["intervals"][1]["gp1_words"], [0x01000000])
        self.assertEqual(r["snapshot_vs_explicit_last_write"], {"retained": 1})
        self.assertFalse(r["HD_replacement_approved"])

    def test_mismatch(self):
        f=fixture()
        f[4]=event(kind="snapshot", seq=5, edge_seq=4, x=5, y=6, value=43)
        self.assertEqual(analyze(f)["snapshot_vs_explicit_last_write"], {"mismatch": 1})

    def test_unknown_not_assumed_to_be_unchanged(self):
        f=fixture()
        f[4]=event(kind="snapshot", seq=5, edge_seq=4, x=7, y=6, value=42)
        self.assertEqual(analyze(f)["snapshot_vs_explicit_last_write"], {"unknown": 1})

    def test_refuse_sequence_overlap(self):
        f=fixture()
        f[2]=event(kind="vram_write", seq=2, x=5, y=6, value=42)
        with self.assertRaises(TraceError): analyze(f)

    def test_refuse_frame_gap(self):
        f=fixture()
        f[3]=event(kind="vblank", seq=4, frame=13, cycle=200)
        with self.assertRaises(TraceError): analyze(f)

    def test_refuse_cycle_regression(self):
        f=fixture()
        f[3]=event(kind="vblank", seq=4, frame=11, cycle=99)
        with self.assertRaises(TraceError): analyze(f)

    def test_refuse_missing_boundary(self):
        with self.assertRaises(TraceError): analyze(fixture()[1:])

    def test_refuse_bad_gpu_word(self):
        f=fixture()
        f[1]=event(kind="gp0", seq=2, word=-1)
        with self.assertRaises(TraceError): analyze(f)

    def test_refuse_bad_edge(self):
        f=fixture()
        f[4]=event(kind="snapshot", seq=5, edge_seq=2, x=5, y=6, value=42)
        with self.assertRaises(TraceError): analyze(f)

    def test_refuse_post_edge_write_before_snapshot(self):
        f=fixture()
        f.insert(4, event(kind="vram_write", seq=5, x=5, y=6, value=42))
        f[5]=event(kind="snapshot", seq=6, edge_seq=4, x=5, y=6, value=42)
        f[6]=event(kind="gp1", seq=7, word=0x01000000)
        f[7]=event(kind="vblank", seq=8, frame=12, cycle=300)
        with self.assertRaises(TraceError): analyze(f)

if __name__=="__main__":
    unittest.main()
