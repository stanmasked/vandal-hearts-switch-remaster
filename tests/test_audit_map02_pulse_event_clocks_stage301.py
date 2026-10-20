"""ROM-free Stage301 Pulse subscribe receipt and provenance falsification tests."""
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from capture_map02_pulse_events_stage301 import sanitize
from audit_map02_pulse_event_clocks_stage301 import parse_subscribe,event_phase

STUB="""S,10000000000,monitor_started
new,10100000000,2
change,10200000000,2
new,10300000000,11
remove,10500000000,2
new,10700000000,14
S,11000000000,monitor_stopped
"""

class Stage301Events(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.path=Path(t.name)/"events.csv"
        self.path.write_text(STUB)

    def check(self,value):
        self.path.write_text(value)
        return parse_subscribe(self.path)

    def test_true_pactl_subscribe_sanitizes_only_sink_inputs(self):
        self.assertEqual(sanitize("Event 'new' on sink-input #14"),("new",14))
        self.assertEqual(sanitize("Event 'remove' on sink-input #2"),("remove",2))
        self.assertEqual(sanitize("Event 'change' on sink-input #94"),("change",94))
        self.assertIsNone(sanitize("Event 'new' on client #3"))
        self.assertIsNone(sanitize("Event 'new' on source-output #99"))
        self.assertIsNone(sanitize("host private data 123"))

    def test_monotonic_receipt_events_and_sha(self):
        rows,sha=parse_subscribe(self.path)
        self.assertEqual(len(rows),7)
        self.assertEqual(len(sha),64)
        self.assertEqual(rows[4]["kind"],"remove")
        self.assertEqual(rows[4]["id"],2)
        self.assertEqual(rows[5]["received_ns"],10_700_000_000)

    def test_reject_hostnames_or_raw_subscriptions_in_csv(self):
        with self.assertRaisesRegex(ValueError,"Unexpected unsanitized"):
            self.check(STUB.replace("new,10100000000,2",
                                    "file,10100000000,/home/runner/secret"))

    def test_reject_missing_start(self):
        with self.assertRaisesRegex(ValueError,"not initialized"):
            self.check(STUB.replace("monitor_started","monitor_stopped"))

    def test_reject_missing_stop(self):
        with self.assertRaisesRegex(ValueError,"not finish"):
            self.check(STUB.replace("monitor_stopped","monitor_started"))

    def test_reject_counter_clock_reversal(self):
        with self.assertRaisesRegex(ValueError,"decreased"):
            self.check(STUB.replace("new,10300000000,11","new,10000000001,11"))

    def test_reject_notification_missing_real_new(self):
        with self.assertRaisesRegex(ValueError,"No REAL"):
            self.check(STUB.replace("new,","change,"))

    def test_reject_non_integer_pulse_input_id(self):
        with self.assertRaisesRegex(ValueError,"Non-numeric"):
            self.check(STUB.replace("new,10700000000,14","new,10700000000,nexium-pid"))

    def test_reject_duplicate_start(self):
        with self.assertRaisesRegex(ValueError,"Ambiguous"):
            self.check(STUB.replace("change,10200000000,2",
                "S,10200000000,monitor_started"))

    def test_late_event_phase_is_receive_time_only(self):
        intervals=(10_000_000_000,10_100_000_000,10_200_000_000,
                   10_300_000_000,10_400_000_000,10_500_000_000)
        self.assertEqual(event_phase(10_250_000_000,*intervals),
            "BETWEEN_GUEST_INPUT_AND_LATE_SNAPSHOT")
        self.assertEqual(event_phase(10_600_000_000,*intervals),
            "AFTER_GUEST_FINAL_MARKER")

    def test_symlink_rejected(self):
        link=self.path.parent/"link.csv"
        link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError,"missing"):
            parse_subscribe(link)

if __name__=="__main__":
    unittest.main()
