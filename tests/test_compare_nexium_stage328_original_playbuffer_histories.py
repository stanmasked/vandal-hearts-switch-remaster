"""Stage328 source-pinned two-cohort guest PlayBuffer history synthetic tests."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from audit_nexium_guest_exit_timeline import SUBDIR,ExitTimelineError
from audit_nexium_guest_playbuffer_history import (
    audit_source,HEADER,SCHEMA as HISTORY_SCHEMA,VERIFIED as HISTORY_VERIFIED,
    FILE as HISTORY_FILE,
)
from audit_nexium_guest_last_playbuffer import (
    SCHEMA as LAST_SCHEMA,VERIFIED as LAST_VERIFIED,
)
from compare_nexium_stage328_original_playbuffer_histories import (
    compare,load,FILES,
)


def cohort(last_duration=11225937,prior_duration=32154011,total=380):
    begin=1_000_000_000
    rows=[]
    for seq in range(total-15,total):
        end=begin+prior_duration
        rows.append(f"{total},{seq},{begin},{end},1\n".encode())
        begin=end+10_000
    last_begin=begin+20_000
    last_end=last_begin+last_duration
    rows.append(f"{total},{total},{last_begin},{last_end},1\n".encode())
    history=HEADER+b"".join(rows)
    last=(f"event,value\nattempts,{total}\nsuccesses,{total}\nfailures,0\n"
          f"last_success_attempt,{total}\n"
          f"last_success_begin_guest_ns,{last_begin}\n"
          f"last_success_end_guest_ns,{last_end}\nnonmonotonic_rejected,0\n").encode()
    stage320={
        "schema":LAST_SCHEMA,
        "result":LAST_VERIFIED,
        "original_source_bytes_preserved":True,
        "original_guest_playbuffer_source_observed":True,
        "original_last_playbuffer_csv_sha256":hashlib.sha256(last).hexdigest(),
        "PlayBuffer_call_attempt_count":total,
        "successful_PlayBuffer_call_count":total,
        "last_successful_PlayBuffer_attempt_index":total,
        "last_successful_PlayBuffer_begin_guest_ns":last_begin,
        "last_successful_PlayBuffer_return_guest_ns":last_end,
        "last_successful_PlayBuffer_software_duration_ns":last_duration,
        "audout_PlayBuffer_return_not_audible_speaker_or_DAC":True,
        "one_call_does_not_explain_entire_stop_delay_automatically":True,
        "physical_Nintendo_Switch_audio_tested":False,
        "audible_dropout_verified":False,
    }
    stage322=audit_source(history,stage320)
    stage322.update({
        "original_guest_history_source_observed":True,
        "original_guest_history_bytes_preserved":True,
        "original_guest_history_source_path":str(SUBDIR/HISTORY_FILE),
    })
    return {
        "last_csv":last,
        "history_csv":history,
        "stage320":stage320,
        "stage322":stage322,
    }


def pin(source):
    return hashlib.sha256(source["history_csv"]).hexdigest()

def pin_last(source):
    return hashlib.sha256(source["last_csv"]).hexdigest()


class TwoAuthenticGuestHistoryComparisonTests(unittest.TestCase):
    def setUp(self):
        self.first=cohort()
        self.second=cohort(last_duration=22352500,prior_duration=31247083,total=382)
        self.first_pin=pin(self.first)
        self.second_pin=pin(self.second)
        self.first_last_pin=pin_last(self.first)
        self.second_last_pin=pin_last(self.second)

    def compare(self,first=None,second=None,first_pin=None,second_pin=None,
                first_last_pin=None,second_last_pin=None):
        return compare(self.first if first is None else first,
                       self.second if second is None else second,
                       self.first_pin if first_pin is None else first_pin,
                       self.second_pin if second_pin is None else second_pin,
                       self.first_last_pin if first_last_pin is None else first_last_pin,
                       self.second_last_pin if second_last_pin is None else second_last_pin)

    def test_original_two_cohort_software_brackets_and_medians(self):
        r=self.compare()
        self.assertEqual(r["result"],"TWO_ORIGINAL_GUEST_PLAYBUFFER_HISTORY_COHORTS_SOURCE_REPLAYED")
        self.assertEqual([c["last_software_ns"] for c in r["cohorts"]],
                         [11225937,22352500])
        self.assertEqual([c["previous_lower_median_software_ns"] for c in r["cohorts"]],
                         [32154011,31247083])
        self.assertEqual(r["second_minus_first_last_software_ns"],11126563)
        self.assertEqual(r["second_minus_first_prior_median_software_ns"],-906928)
        self.assertTrue(r["each_original_stage322_receipt_recomputed_from_exact_csv"])
        self.assertFalse(r["speaker_audio_or_original_soundtrack_verified"])

    def test_original_history_csv_tamper_with_same_pin_rejected(self):
        altered=copy.deepcopy(self.first)
        altered["history_csv"]=altered["history_csv"].replace(b"380,370,",b"380,369,")
        with self.assertRaises(ExitTimelineError):
            self.compare(first=altered)

    def test_altered_stage322_receipt_rejected(self):
        altered=copy.deepcopy(self.first)
        altered["stage322"]["final_call_duration_guest_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.compare(first=altered)

    def test_altered_stage320_last_csv_rejected(self):
        altered=copy.deepcopy(self.second)
        altered["last_csv"]+=b"garbage"
        with self.assertRaises(ExitTimelineError):
            self.compare(second=altered)

    def test_forged_stage320_success_index_rejected(self):
        altered=copy.deepcopy(self.second)
        altered["stage320"]["last_successful_PlayBuffer_attempt_index"]-=1
        with self.assertRaises(ExitTimelineError):
            self.compare(second=altered)

    def test_forged_original_last_call_csv_pin_rejected(self):
        with self.assertRaises(ExitTimelineError):
            self.compare(first_last_pin="0"*64)

    def test_original_stage320_provenance_missing_rejected(self):
        for field in ("original_source_bytes_preserved",
                      "original_guest_playbuffer_source_observed",
                      "audout_PlayBuffer_return_not_audible_speaker_or_DAC"):
            altered=copy.deepcopy(self.first)
            altered["stage320"][field]=False
            with self.subTest(field=field),self.assertRaises(ExitTimelineError):
                self.compare(first=altered)

    def test_original_stage322_provenance_missing_rejected(self):
        for field in ("original_guest_history_bytes_preserved",
                      "original_guest_history_source_observed"):
            altered=copy.deepcopy(self.second)
            altered["stage322"][field]=False
            with self.subTest(field=field),self.assertRaises(ExitTimelineError):
                self.compare(second=altered)

    def test_identical_source_history_pins_rejected(self):
        with self.assertRaises(ExitTimelineError):
            self.compare(second=self.first,second_pin=self.first_pin,
                         second_last_pin=self.first_last_pin)

    def test_missing_earlier_call_baseline_cannot_be_fabricated(self):
        altered=cohort(last_duration=11225937,prior_duration=5000000)
        with self.assertRaises(ExitTimelineError):
            self.compare(first=altered,first_pin=pin(altered),
                         first_last_pin=pin_last(altered))

    def test_corrupt_or_ambiguous_original_artifact_rejected(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            for key,name in FILES.items():
                value=self.first[key]
                (root/name).write_bytes(value if key.endswith("csv")
                    else json.dumps(value).encode())
            self.assertEqual(load(root)["history_csv"],self.first["history_csv"])
            extra=root/"nested"
            extra.mkdir()
            (extra/"audio-playbuffer-history-000.csv").write_bytes(
                self.first["history_csv"])
            with self.assertRaises(ExitTimelineError):
                load(root)

    def test_symlinked_original_history_rejected(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            (root/"real").write_bytes(self.first["history_csv"])
            (root/"audio-playbuffer-history-000.csv").symlink_to(root/"real")
            with self.assertRaises(ExitTimelineError):
                load(root)

    def test_guest_absolute_timestamps_and_raw_pcm_never_output(self):
        result=self.compare()
        text=json.dumps(result,sort_keys=True)
        self.assertNotIn("1000000000",text)
        self.assertNotIn("begin_guest_ns",text)
        self.assertNotIn("end_guest_ns",text)
        self.assertNotIn("pcm_bytes",text)
        self.assertFalse(result["physical_Nintendo_Switch_audio_tested"])


if __name__=="__main__":
    unittest.main()
