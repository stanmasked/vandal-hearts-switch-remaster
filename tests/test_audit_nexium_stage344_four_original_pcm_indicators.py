"""Stage344 reject altered PCM summaries and original four-run chain claims."""
from __future__ import annotations
import copy,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from audit_nexium_stage344_four_original_pcm_indicators import (
    compare_verified_reports,compact_pcm,RESULT,PIN_FIELDS,
)
from analyze_nexium_pcm_stream_integrity import SCHEMA as STAGE299_SCHEMA

def fixture():
    names=("original_first","original_second","original_third","original_fourth")
    last=(11225937,22352500,18486979,25438021)
    median=(32154011,31247083,32374948,26170625)
    cohorts=[]
    for i,name in enumerate(names):
        row={"source":name,"guest_last_software_duration_ns":last[i],
             "guest_prior_lower_median_software_ns":median[i],
             "guest_prior_median_minus_last_software_ns":median[i]-last[i]}
        for j,key in enumerate(PIN_FIELDS):
            row[key]=format(i*4+j+1,"064x")
        cohorts.append(row)
    source={"schema":"vh-stage337-four-genuine-neXium-guest-host-source-to-nro-cohorts/v1",
        "result":"FOUR_DISTINCT_ORIGINAL_NEXIUM_GUEST_HOST_CAPTURE_COHORTS_SOURCE_VERIFIED",
        "cohorts":cohorts,
        "original_third_run_id":39175592570,
        "original_fourth_run_id":39182548276,
        "physical_Nintendo_Switch_audio_tested":False,
        **{k:True for k in (
            "all_three_previous_stage335_original_sources_replayed",
            "original_fourth_stage334_receipt_recomputed_exactly",
            "original_fourth_stage336_receipt_recomputed_exactly",
            "all_four_original_guest_host_CSV_source_hashes_distinct",
            "no_software_guest_clock_converted_into_host_PCM_clock")},
        }
    reports=[]
    for i in range(4):
        doc={"schema":STAGE299_SCHEMA,
             "result":"TWO_ORIGINAL_NEXIUM_VIRTUAL_PCM_STREAMS_AUDITED",
             "distinct_current_run_virtual_PCM_sources":True,
             "both_prior_PCM_audits_bound_by_exact_SHA256":True,
             "all_stereo_frames_and_10ms_blocks_accounted":True,
             "dropped_or_duplicated_audio_frames_proven":False,
             "physical_Nintendo_Switch_hardware_tested":False,
             "soundtrack_identity_or_audible_playback_verified":False}
        for k in ("monitor","scenes"):
            frames=1000+i*1000
            doc["monitor_capture" if k=="monitor" else "scene_capture"]={
                "kind":k,"pcm_sha256":format(99+i*2+(k=="scenes"),"064x"),
                "pcm_bytes":frames*4,"frames":frames,
                "analysis_block_frames":480,
                "analysis_blocks":(frames+479)//480,
                "final_partial_block_frames":frames%480,
                "pinned_prior_report_reconciled":True,
                "physical_console_DAC_or_audible_glitches_measured":False,
                "possible_sample_discontinuities_are_not_verified_dropouts":True,
                "missing_frames_cannot_be_proven_from_pcm_bytes_alone":True,
                "guest_audio_queue_state_not_measured_by_pcm":True,
                "exact_zero_stereo_frames":100,
                "longest_exact_zero_stereo_run_frames":80,
                "zero_runs_at_least_10ms":0,
                "low_rms_10ms_blocks":0,"exact_zero_10ms_blocks":0,
                "adjacent_frame_deltas_ge4096":2,
                "ge4096_deltas_at_10ms_block_boundaries":1,
                "scene_event_markers":None if k=="monitor" else [{}]*5,
            }
        reports.append(doc)
    return source,reports

class OriginalPcmIndicatorTests(unittest.TestCase):
    def setUp(self):self.source,self.docs=fixture()
    def test_four_different_original_pcm_records(self):
        d=compare_verified_reports(self.source,self.docs)
        self.assertEqual(d["result"],RESULT)
        self.assertEqual(len(d["original_capture_indicator_rows"]),4)
        self.assertEqual(d["original_capture_indicator_rows"][0]["monitor"]["exact_zero_frames_per_million"],100000)
        self.assertFalse(d["physical_Nintendo_Switch_audio_tested"])
    def test_guest_source_duplicate_rejected(self):
        a=copy.deepcopy(self.source)
        a["cohorts"][3][PIN_FIELDS[0]]=a["cohorts"][2][PIN_FIELDS[0]]
        with self.assertRaises(ValueError):compare_verified_reports(a,self.docs)
    def test_pcm_capture_sha_duplicate_rejected(self):
        a=copy.deepcopy(self.docs)
        a[3]["monitor_capture"]["pcm_sha256"]=a[2]["monitor_capture"]["pcm_sha256"]
        with self.assertRaises(ValueError):compare_verified_reports(self.source,a)
    def test_fake_pcm_fidelity_claim_rejected(self):
        a=copy.deepcopy(self.docs)
        a[0]["dropped_or_duplicated_audio_frames_proven"]=True
        with self.assertRaises(ValueError):compare_verified_reports(self.source,a)
    def test_no_hardware_scope_overclaim(self):
        a=copy.deepcopy(self.docs)
        a[2]["scene_capture"]["physical_console_DAC_or_audible_glitches_measured"]=True
        with self.assertRaises(ValueError):compare_verified_reports(self.source,a)
    def test_altered_stereo_frame_size_rejected(self):
        a=copy.deepcopy(self.docs)
        a[1]["monitor_capture"]["pcm_bytes"]+=4
        with self.assertRaises(ValueError):compare_verified_reports(self.source,a)
    def test_longest_zero_run_cannot_exceed_zero_total(self):
        a=copy.deepcopy(self.docs)
        a[3]["scene_capture"]["longest_exact_zero_stereo_run_frames"]=101
        with self.assertRaises(ValueError):compare_verified_reports(self.source,a)
    def test_partial_final_10ms_block_can_be_all_zero_without_full_480_frames(self):
        v=copy.deepcopy(self.docs[0]["monitor_capture"])
        v["frames"]=763
        v["pcm_bytes"]=763*4
        v["analysis_blocks"]=2
        v["final_partial_block_frames"]=283
        v["exact_zero_stereo_frames"]=283
        v["longest_exact_zero_stereo_run_frames"]=283
        v["exact_zero_10ms_blocks"]=1
        v["low_rms_10ms_blocks"]=1
        result=compact_pcm(v,"monitor")
        self.assertEqual(result["all_zero_10ms_blocks"],1)
        self.assertEqual(result["exact_zero_frames"],283)

    def test_partial_block_cannot_claim_more_full_zero_blocks_than_zero_frames(self):
        v=copy.deepcopy(self.docs[0]["monitor_capture"])
        v["frames"]=763
        v["pcm_bytes"]=763*4
        v["analysis_blocks"]=2
        v["final_partial_block_frames"]=283
        v["exact_zero_stereo_frames"]=282
        v["longest_exact_zero_stereo_run_frames"]=282
        v["exact_zero_10ms_blocks"]=1
        v["low_rms_10ms_blocks"]=1
        with self.assertRaises(ValueError):
            compact_pcm(v,"monitor")

    def test_large_step_boundary_cannot_exceed_total(self):
        a=copy.deepcopy(self.docs)
        a[0]["scene_capture"]["ge4096_deltas_at_10ms_block_boundaries"]=3
        with self.assertRaises(ValueError):compare_verified_reports(self.source,a)
    def test_cannot_substitute_monitor_for_scene_markers(self):
        a=copy.deepcopy(self.docs)
        a[1]["scene_capture"]["scene_event_markers"]=None
        with self.assertRaises(ValueError):compare_verified_reports(self.source,a)
    def test_derived_rates_normalize_by_valid_actual_frame_counts(self):
        sample=self.docs[3]["scene_capture"]
        r=compact_pcm(sample,"scenes")
        self.assertEqual(r["frames"],4000)
        self.assertEqual(r["exact_zero_frames_per_million"],25000)
        self.assertEqual(r["large_steps_per_million_frame_transitions"],2*1000000//3999)
    def test_without_original_stage342_success_rejected(self):
        a=copy.deepcopy(self.source);a["original_fourth_stage336_receipt_recomputed_exactly"]=False
        with self.assertRaises(ValueError):compare_verified_reports(a,self.docs)
    def test_summary_has_no_absolute_host_epochs_or_waveform(self):
        text=str(compare_verified_reports(self.source,self.docs))
        for forbidden in ("host_epoch_ms","original_pcm_data","raw_pcm","begin_guest_ns"):
            self.assertNotIn(forbidden,text)

if __name__=="__main__":
    unittest.main()
