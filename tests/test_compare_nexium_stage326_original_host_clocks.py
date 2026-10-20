"""Stage326 two independent NeXium original host-clock cohorts: synthetic tests.

Strict source validation only; no real audio samples, captured game assets,
guest-to-host sample timing conversion or physical-console claims.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from audit_nexium_host_clock_pairs import audit,ClockPairError,EVENTS
from compare_nexium_stage326_original_host_clocks import (
    compare_cohorts,load_from_root,STAGE304_OK,STAGE305_OK,
)


def sample(base:int, sizes=(100000,101000,120000),
           wall_intervals=(357,4270),
           monotonic_intervals=(357687151,4269790190)):
    wall=[base,base+wall_intervals[0],base+sum(wall_intervals)]
    mono=[123450000000,123450000000+monotonic_intervals[0],
          123450000000+sum(monotonic_intervals)]
    legacy=("event,pcm_bytes,host_epoch_ms\n"+"".join(
        f"{ev},{size},{ts}\n" for ev,size,ts in zip(EVENTS,sizes,wall))).encode()
    dual=("event,pcm_bytes,host_epoch_ms,host_monotonic_ns\n"+"".join(
        f"{ev},{size},{ts},{ns}\n"
        for ev,size,ts,ns in zip(EVENTS,sizes,wall,mono))).encode()
    receipt=audit(legacy,dual)
    return {
        "legacy_csv":legacy,
        "dual_csv":dual,
        "stage325":receipt,
        "stage304":{
            "result":STAGE304_OK,
            "all_original_source_witnesses_replayed":True,
            "physical_Nintendo_Switch_audio_tested":False,
            "exit_control_snapshots":[
                {"event":e,"pcm_bytes":size,"host_epoch_ms":epoch}
                for e,size,epoch in zip(EVENTS,sizes,wall)],
        },
        "stage305":{
            "result":STAGE305_OK,
            "all_original_stage299_through_stage304_evidence_replayed":True,
            "physical_Nintendo_Switch_audio_tested":False,
        },
    }


def pins(s):
    return (hashlib.sha256(s["legacy_csv"]).hexdigest(),
            hashlib.sha256(s["dual_csv"]).hexdigest())


class OriginalDualClockCohortComparisonTests(unittest.TestCase):
    def setUp(self):
        self.a=sample(100000)
        self.b=sample(200000,sizes=(200000,201600,240000),
                      wall_intervals=(358,4286),
                      monotonic_intervals=(357696182,4285779743))
        self.ap=pins(self.a)
        self.bp=pins(self.b)

    def compare(self,a=None,b=None,ap=None,bp=None):
        return compare_cohorts(
            self.a if a is None else a,self.b if b is None else b,
            first_pins=self.ap if ap is None else ap,
            second_pins=self.bp if bp is None else bp)

    def test_two_distinct_valid_cohorts_and_exact_ns_deltas(self):
        out=self.compare()
        self.assertEqual(out["result"],"TWO_DISTINCT_ORIGINAL_NEXIUM_HOST_CLOCK_COHORTS_REPLAYED")
        rows=out["original_control_pair_comparison"]
        self.assertEqual([r["second_minus_first_wall_delta_ms"] for r in rows],[1,16])
        self.assertEqual([r["second_minus_first_monotonic_delta_ns"] for r in rows],
                         [9031,15989553])
        self.assertFalse(out["entire_stage304_or_stage305_pcm_chain_independently_rerun"])
        self.assertFalse(out["physical_Nintendo_Switch_audio_tested"])
        self.assertTrue(out["each_original_stage304_host_controls_matched_strict_receipt"])

    def test_unpinned_original_bytes_rejected(self):
        alt=sample(100000, sizes=(100000,101004,120000))
        with self.assertRaises(ClockPairError):
            self.compare(a=alt)

    def test_equal_cohort_pins_rejected(self):
        with self.assertRaises(ClockPairError):
            self.compare(b=copy.deepcopy(self.a),bp=self.ap)

    def test_wrong_pinned_hash_shape_rejected(self):
        with self.assertRaises(ClockPairError):
            self.compare(ap=("not-a-digest",self.ap[1]))

    def test_source_receipt_mismatch_rejected(self):
        changed=copy.deepcopy(self.b)
        changed["stage325"]["wall_epoch_equal_pair_count"]=1
        with self.assertRaises(ClockPairError):
            self.compare(b=changed)

    def test_stage304_controls_have_to_match_original_csv(self):
        changed=copy.deepcopy(self.a)
        changed["stage304"]["exit_control_snapshots"][1]["pcm_bytes"]+=1
        with self.assertRaises(ClockPairError):
            self.compare(a=changed)

    def test_stage304_failed_or_missing_provenance_rejected(self):
        for field,value in (("result","STAGE304_FAILED"),
                            ("all_original_source_witnesses_replayed",False),
                            ("physical_Nintendo_Switch_audio_tested",True)):
            with self.subTest(field=field):
                changed=copy.deepcopy(self.a)
                changed["stage304"][field]=value
                with self.assertRaises(ClockPairError):
                    self.compare(a=changed)

    def test_stage305_failed_or_unbounded_scope_rejected(self):
        for field,value in (("result","STAGE305_FAILED"),
                            ("all_original_stage299_through_stage304_evidence_replayed",False),
                            ("physical_Nintendo_Switch_audio_tested",True)):
            with self.subTest(field=field):
                changed=copy.deepcopy(self.b)
                changed["stage305"][field]=value
                with self.assertRaises(ClockPairError):
                    self.compare(b=changed)

    def test_stage304_clock_regression_is_not_rescued_by_monotonic_clock(self):
        failed=sample(300000,wall_intervals=(-347,4270))
        with self.assertRaises(ClockPairError):
            self.compare(a=failed,ap=pins(failed))

    def test_missing_or_ambiguous_source_files_rejected(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(ClockPairError):
                load_from_root(root)
            sources={
                "scene-exit-controls.csv":self.a["legacy_csv"],
                "scene-exit-controls-monotonic.csv":self.a["dual_csv"],
                "host-dual-clock-stage325.json":json.dumps(self.a["stage325"]).encode(),
                "pcm-exit-controls-stage304.json":json.dumps(self.a["stage304"]).encode(),
                "pcm-plus-onset-fence-stage305.json":json.dumps(self.a["stage305"]).encode(),
            }
            for name,content in sources.items():
                (root/name).write_bytes(content)
            got=load_from_root(root)
            self.assertEqual(got["legacy_csv"],self.a["legacy_csv"])
            nested=root/"extra"
            nested.mkdir()
            (nested/"scene-exit-controls.csv").write_bytes(self.a["legacy_csv"])
            with self.assertRaises(ClockPairError):
                load_from_root(root)

    def test_symlinked_original_source_rejected(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            (root/"target").write_bytes(b"synthetic")
            (root/"scene-exit-controls.csv").symlink_to(root/"target")
            with self.assertRaises(ClockPairError):
                load_from_root(root)

    def test_no_absolute_host_timestamps_or_pcm_in_comparison(self):
        self.a=sample(1712345678000)
        self.b=sample(1712346678000,sizes=(200000,201600,240000),
                      wall_intervals=(358,4286),
                      monotonic_intervals=(357696182,4285779743))
        self.ap=pins(self.a)
        self.bp=pins(self.b)
        text=json.dumps(self.compare(),sort_keys=True)
        self.assertNotIn("1712345678000",text)
        self.assertNotIn("1712346678000",text)
        self.assertNotIn("123450000000",text)
        self.assertNotIn("original_pcm_bytes",text)


if __name__=="__main__":
    unittest.main()
