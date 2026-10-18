"""Stage289 service-probe source binding synthetic tests, not hardware."""
from __future__ import annotations

import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from audit_nexium_audout_service_probes import parse_probes


def fixture():
    # Three 1/16 probes across 34 audout attempts; each second is
    # independently accounted for by an equal 17-call guest window.
    origin={"origin_ns":1_000_000_000,"attempts":34}
    queue={"attempts":34,"queue_probes_ok":2,"queue_probes_failed":1,
           "queue_min_pre_submit":0,"queue_max_pre_submit":3}
    latency={
        "attempts":34,"from40to50ms_calls":1,"ge50ms_calls":0,
        "per_second_call_bands":[
            {"second":0,"attempts":17},{"second":1,"attempts":17}]
    }
    slow=[{"attempt":17,"begin_ns":1_900_000_000,"audio_second":0,
           "duration_ns":41_000_000}]
    raw=("scope,index,attempt,submit_begin_ns,status,queue_count,total_probes,dropped_probes\n"
         "TOTAL,-1,0,0,-1,0,3,0\n"
         "SAMPLE,0,1,1000000000,1,3,0,0\n"
         "SAMPLE,1,17,1900000000,0,0,0,0\n"
         "SAMPLE,2,33,2900000000,1,0,0,0\n").encode("ascii")
    return raw,origin,queue,latency,slow


class ServiceProbeCSVTests(unittest.TestCase):
    def test_strict_probe_and_slow_match(self):
        args=fixture()
        report=parse_probes(*args)
        self.assertEqual(report["queue_probe_samples"],3)
        self.assertEqual(report["queue_probe_successes"],2)
        self.assertEqual(report["queue_probe_failures"],1)
        self.assertEqual(len(report["probed_slow_calls"]),1)
        self.assertEqual(report["probed_slow_calls"][0]["attempt"],17)
        self.assertFalse(report["scheduler_or_DAC_state_measured"])

    def test_mutations_fail_closed(self):
        raw,origin,queue,latency,slow=fixture()
        cases=[
            raw.replace(b"total_probes",b"other_probes"),
            raw.replace(b",3,0\nSAMPLE",b",4,0\nSAMPLE"),
            raw.replace(b"SAMPLE,1,17,",b"SAMPLE,1,18,"),
            raw.replace(b"1900000000",b"1800000000"),
            raw.replace(b"SAMPLE,1,17,1900000000,0,0",
                        b"SAMPLE,1,17,1900000000,0,8"),
            raw.replace(b"SAMPLE,2,33,2900000000,1,0",
                        b"SAMPLE,2,33,2900000000,1,2"),
            raw.replace(b"SAMPLE,2,33",b"SAMPLE,1,33"),
            raw+b"APPENDED\n",
            raw.replace(b",3,0\nSAMPLE",b",3,1\nSAMPLE"),
        ]
        for candidate in cases:
            self.assertNotEqual(candidate,raw)
            with self.subTest(candidate=candidate[-90:]),self.assertRaises(CorrelationError):
                parse_probes(candidate,origin,queue,latency,slow)

    def test_clock_source_and_queue_summary_mismatch_rejected(self):
        raw,origin,queue,latency,slow=fixture()
        with self.assertRaises(CorrelationError):
            parse_probes(raw,{**origin,"origin_ns":3_000_000_000},queue,latency,slow)
        with self.assertRaises(CorrelationError):
            parse_probes(raw,origin,{**queue,"queue_probes_failed":0},latency,slow)
        with self.assertRaises(CorrelationError):
            parse_probes(raw,origin,queue,{**latency,"attempts":40},slow)

    def test_no_absent_slow_call_fabrication(self):
        raw,origin,queue,latency,slow=fixture()
        with self.assertRaises(CorrelationError):
            parse_probes(raw,origin,queue,latency,[])


if __name__=="__main__":
    unittest.main()
