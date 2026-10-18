"""Stage325 synthetic host monotonic/epoch Plus-control witness tests.

Synthetic CSV only. None of these tests imports original PCM, PS1 assets, or
asserts that Nintendo Switch speakers emitted audio.
"""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from audit_nexium_host_clock_pairs import (
    audit,record,ClockPairError,LEGACY_HEADER,DUAL_HEADER,EVENTS,
)
from audit_nexium_pcm_exit_controls import control_events
from analyze_nexium_pcm_stream_integrity import VirtualPcmEvidenceError


class HostDualClockEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.pcm=root/"private-empty-synthetic.pcm"
        self.pcm.write_bytes(b"\0"*8)
        self.legacy=root/"scene-exit-controls.csv"
        self.dual=root/"scene-exit-controls-monotonic.csv"
        self.legacy.write_text(",".join(LEGACY_HEADER)+"\n",encoding="ascii")
        self.dual.write_text(",".join(DUAL_HEADER)+"\n",encoding="ascii")

    def write(self,index:int,*,epoch:int,mono:int,size:int)->None:
        self.pcm.write_bytes(b"\0"*size)
        # One monotonic tick brackets the wall clock, one after it.
        ticks=iter([mono-1,mono])
        record(EVENTS[index],self.pcm,self.legacy,self.dual,
               wall_ns=lambda:epoch*1_000_000,
               mono_ns=lambda:next(ticks))

    def complete(self,epochs=(100000,100003,100010),
                 monotonic=(1000000000,1002000000,1008000000)):
        for i,(epoch,mono) in enumerate(zip(epochs,monotonic)):
            self.write(i,epoch=epoch,mono=mono,size=100+i*16)
        return audit(self.legacy.read_bytes(),self.dual.read_bytes())

    def test_three_synchronized_records_and_sha(self):
        data=self.complete()
        self.assertEqual(data["result"],
                         "ORIGINAL_HOST_DUAL_CLOCK_CSVS_INDEPENDENTLY_MATCHED")
        self.assertEqual([d["pcm_file_size_delta_bytes"]
                          for d in data["adjacent_host_clock_deltas"]],[16,16])
        self.assertEqual([d["host_monotonic_delta_ns"]
                          for d in data["adjacent_host_clock_deltas"]],
                         [2000000,6000000])
        self.assertEqual(data["wall_epoch_backwards_pair_count"],0)
        self.assertTrue(data["all_monotonic_intervals_positive"])
        self.assertFalse(data["physical_Nintendo_Switch_audio_tested"])
        self.assertEqual(len(data["legacy_csv_sha256"]),64)
        self.assertEqual(len(data["paired_clock_csv_sha256"]),64)
        self.assertEqual(len(control_events(self.legacy.read_bytes())),3)

    def test_clock_backstep_is_observable_but_not_stage304_success(self):
        data=self.complete(epochs=(100000,99653,103867),
                           monotonic=(1000000000,1250000000,5500000000))
        self.assertEqual([x["host_wall_delta_ms"]
                          for x in data["adjacent_host_clock_deltas"]],
                         [-347,4214])
        self.assertEqual(data["wall_epoch_backwards_pair_count"],1)
        self.assertTrue(data["all_monotonic_intervals_positive"])
        with self.assertRaises(VirtualPcmEvidenceError):
            control_events(self.legacy.read_bytes())

    def test_same_millisecond_is_separate_from_backstep(self):
        data=self.complete(epochs=(100000,100000,100010))
        self.assertEqual(data["wall_epoch_equal_pair_count"],1)
        self.assertEqual(data["wall_epoch_backwards_pair_count"],0)

    def test_second_clock_refuses_nonpositive_interval(self):
        self.write(0,epoch=100000,mono=10000000,size=100)
        self.write(1,epoch=100002,mono=10000200,size=110)
        dual=self.dual.read_bytes().replace(b"10000200",b"10000000")
        with self.assertRaises(ClockPairError):
            audit(self.legacy.read_bytes()+
                  f"{EVENTS[2]},120,100003\n".encode(),
                  dual+f"{EVENTS[2]},120,100003,11000000\n".encode())

    def test_cross_file_mismatch_rejected(self):
        self.complete()
        legacy=self.legacy.read_bytes()
        dual=self.dual.read_bytes().replace(
            b"after_plus_up,116,100003,",b"after_plus_up,117,100003,")
        with self.assertRaises(ClockPairError):
            audit(legacy,dual)

    def test_duplicate_or_skipped_event_rejected(self):
        self.write(0,epoch=100000,mono=10000000,size=100)
        with self.assertRaises(ClockPairError):
            self.write(0,epoch=100001,mono=10000200,size=104)
        with self.assertRaises(ClockPairError):
            self.write(2,epoch=100002,mono=10000300,size=108)

    def test_capture_refuses_clock_regression_before_writing(self):
        self.write(0,epoch=100000,mono=10000000,size=100)
        original=(self.legacy.read_bytes(),self.dual.read_bytes())
        with self.assertRaises(ClockPairError):
            self.write(1,epoch=100001,mono=10000000,size=104)
        self.assertEqual(original,
                         (self.legacy.read_bytes(),self.dual.read_bytes()))

    def test_missing_companion_record_refuses_any_further_write(self):
        self.write(0,epoch=100000,mono=10000000,size=100)
        self.dual.write_text(",".join(DUAL_HEADER)+"\n",encoding="ascii")
        before=self.legacy.read_bytes()
        with self.assertRaises(ClockPairError):
            self.write(1,epoch=100001,mono=10002000,size=104)
        self.assertEqual(before,self.legacy.read_bytes())

    def test_empty_truncated_or_extra_csv_fails_closed(self):
        self.complete()
        legacy=self.legacy.read_bytes()
        dual=self.dual.read_bytes()
        for bad in (b"",dual[:-1],dual+b"extra,1,2,3\n",
                    dual.replace(b"\n",b"\r\n"),
                    dual.replace(b"host_monotonic_ns",b"other"),
                    dual.replace(b"1000000000",b"01000000000")):
            with self.subTest(bad=bad[:30]),self.assertRaises(ClockPairError):
                audit(legacy,bad)

    def test_host_pcm_size_decrease_is_only_reported_not_accepted(self):
        for i,(size,epoch,mono) in enumerate(
                [(100,100000,1000000000),
                 (96,100010,1010000000),
                 (116,100020,1020000000)]):
            self.write(i,size=size,epoch=epoch,mono=mono)
        data=audit(self.legacy.read_bytes(),self.dual.read_bytes())
        self.assertEqual(data["pcm_size_regression_pair_count"],1)
        with self.assertRaises(VirtualPcmEvidenceError):
            control_events(self.legacy.read_bytes())

    def test_no_absolute_epochs_or_monotonic_uptime_in_public_receipt(self):
        data=self.complete(epochs=(1712345678000,1712345678010,1712345678020),
                           monotonic=(998800000000,998810000000,998820000000))
        text=str(data)
        self.assertNotIn("1712345678000",text)
        self.assertNotIn("998800000000",text)
        self.assertEqual([x["host_wall_delta_ms"]
                          for x in data["adjacent_host_clock_deltas"]],[10,10])


if __name__=="__main__":
    unittest.main()
