"""Stage343 unit tests for original same executable NeXium service-time variation."""
from __future__ import annotations
import copy,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from audit_nexium_stage343_same_nro_variation import report,RESULT,FLAGS,SOURCE_KEYS

def sample():
    last=[11225937,22352500,18486979,25438021]
    previous=[32154011,31247083,32374948,26170625]
    hosts=[[357687151,4269790190],[357696182,4285779743],
           [324470642,4220779386],[350024814,4269756021]]
    rows=[]
    for i in range(4):
        v={
            "source":("original_first","original_second","original_third","original_fourth")[i],
            "guest_last_software_duration_ns":last[i],
            "guest_prior_lower_median_software_ns":previous[i],
            "guest_prior_median_minus_last_software_ns":previous[i]-last[i],
            "guest_last_first_possible_rank":(1,6,7,7)[i],
            "host_control_intervals":[{"host_wall_delta_ms":350+j+1,
                 "host_monotonic_delta_ns":hosts[i][j]} for j in range(2)]
        }
        for j,key in enumerate(SOURCE_KEYS):
            v[key]=format(i*4+j+1,"064x")
        rows.append(v)
    difference={
        "fourth_minus_earlier_guest_last_software_ns":last[3]-last[2],
        "fourth_minus_earlier_guest_prior_median_software_ns":previous[3]-previous[2],
        "fourth_minus_earlier_host_monotonic_control_deltas_ns":[
            hosts[3][0]-hosts[2][0],hosts[3][1]-hosts[2][1]]}
    return {
        "schema":"vh-stage337-four-genuine-neXium-guest-host-source-to-nro-cohorts/v1",
        "result":"FOUR_DISTINCT_ORIGINAL_NEXIUM_GUEST_HOST_CAPTURE_COHORTS_SOURCE_VERIFIED",
        "cohorts":rows,
        "original_third_run_id":39175592570,
        "original_fourth_run_id":39182548276,
        "third_same_run_nro_sha256":"a"*64,
        "fourth_same_run_nro_sha256":"a"*64,
        "third_and_fourth_nro_sha256_match":True,
        "fourth_minus_previous_three_own_clock_differences":[{}, {}, difference],
        **{key:True for key in FLAGS},
        "physical_Nintendo_Switch_audio_tested":False,
        "original_PS1_soundtrack_or_audible_dropout_verified":False,
    }

class SameNROVariationTests(unittest.TestCase):
    def setUp(self):self.src=sample()
    def test_original_source_matched_guest_and_host_deltas(self):
        r=report(self.src)
        self.assertEqual(r["result"],RESULT)
        self.assertEqual(r["fourth_minus_third_last_guest_software_ns"],6951042)
        self.assertEqual(r["fourth_minus_third_previous_median_guest_software_ns"],-6204323)
        self.assertEqual(r["fourth_minus_third_median_margin_guest_software_ns"],-13155365)
        self.assertEqual(r["fourth_minus_third_host_only_monotonic_interval_deltas_ns"],[25554172,48976635])
        self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])
    def test_other_NRO_hash_must_fail(self):
        a=copy.deepcopy(self.src)
        a["fourth_same_run_nro_sha256"]="b"*64
        with self.assertRaises(ValueError):report(a)
    def test_false_equivalence_of_NRO_fails(self):
        a=copy.deepcopy(self.src);a["third_and_fourth_nro_sha256_match"]=False
        with self.assertRaises(ValueError):report(a)
    def test_original_guest_source_duplicate_fails(self):
        a=copy.deepcopy(self.src)
        a["cohorts"][3][SOURCE_KEYS[0]]=a["cohorts"][2][SOURCE_KEYS[0]]
        with self.assertRaises(ValueError):report(a)
    def test_original_host_source_duplicate_fails(self):
        a=copy.deepcopy(self.src)
        a["cohorts"][3][SOURCE_KEYS[2]]=a["cohorts"][2][SOURCE_KEYS[2]]
        with self.assertRaises(ValueError):report(a)
    def test_wrong_historical_source_digest_format_fails(self):
        a=copy.deepcopy(self.src)
        a["cohorts"][0][SOURCE_KEYS[3]]="not-a-sha"
        with self.assertRaises(ValueError):report(a)
    def test_changed_software_duration_fails_closed(self):
        a=copy.deepcopy(self.src)
        a["cohorts"][3]["guest_last_software_duration_ns"]+=1
        with self.assertRaises(ValueError):report(a)
    def test_cross_capture_host_delta_tampering_fails(self):
        a=copy.deepcopy(self.src)
        a["fourth_minus_previous_three_own_clock_differences"][2]["fourth_minus_earlier_host_monotonic_control_deltas_ns"][0]+=1
        with self.assertRaises(ValueError):report(a)
    def test_original_source_flag_false_fails(self):
        a=copy.deepcopy(self.src);a[FLAGS[1]]=False
        with self.assertRaises(ValueError):report(a)
    def test_new_fourth_must_not_be_failed_run(self):
        a=copy.deepcopy(self.src);a["original_fourth_run_id"]=39179079695
        with self.assertRaises(ValueError):report(a)
    def test_physical_speaker_evidence_claim_rejected(self):
        a=copy.deepcopy(self.src);a["physical_Nintendo_Switch_audio_tested"]=True
        with self.assertRaises(ValueError):report(a)
    def test_output_contains_no_absolute_epochs(self):
        text=str(report(self.src))
        for bad in ("host_epoch_ms","begin_guest_ns","end_guest_ns","pcm_samples"):
            self.assertNotIn(bad,text)
        self.assertTrue(report(self.src)["software_guest_clock_not_subtracted_from_host_clock"])

if __name__=="__main__": unittest.main()
