"""Stage300 generated-only falsification checks; NEVER fabricate real trial proof."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_pulse_sinks_stage300 import parse_pulse_snapshot,ROUTES

def one(n,spec,client=5,pid=100,corked="no",application="ALSA plug-in [nexium]"):
    return (
        f"Sink Input #{n}\n"
        f"\tDriver: protocol-native.c\n\tClient: {client}\n"
        f"\tSink: 1\n\tSample Specification: {spec}\n"
        f"\tCorked: {corked}\n\tMute: no\n"
        f"\tBuffer Latency: 10666 usec\n"
        f"\tProperties:\n"
        f'\t\tmedia.name = "ALSA Playback"\n'
        f'\t\tapplication.name = "{application}"\n'
        f'\t\tapplication.process.binary = "nexium"\n'
        f'\t\tapplication.process.id = "{pid}"\n'
    )

def fixture(stereo_id=2,other_id=94,stereo_client=5,other_client=7,pid=100):
    return one(stereo_id,"float32le 2ch 48000Hz",stereo_client,pid)+(
        "\n"+one(other_id,"float32le 32ch 384000Hz",other_client,pid))

class Stage300PulseParserTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.path=Path(t.name)/"snapshot.txt"
        self.path.write_text(fixture())

    def parse(self,text):
        self.path.write_text(text)
        return parse_pulse_snapshot(self.path)

    def test_source_shaped_real_pulse_two_routes(self):
        snap=parse_pulse_snapshot(self.path)
        self.assertEqual(len(snap["by_route"]),2)
        self.assertEqual(set(snap["by_route"]),set(ROUTES))
        self.assertEqual(snap["by_route"][("float32le",2,48000)]["sink_input_id"],2)
        self.assertEqual(snap["by_route"][("float32le",32,384000)]["sink_input_id"],94)
        self.assertFalse(snap["by_route"][("float32le",2,48000)]["corked"])
        self.assertEqual(len(snap["original_snapshot_sha256"]),64)

    def test_sink_input_replacement_changes_only_id_not_client(self):
        early=self.parse(fixture())
        later=self.parse(fixture(stereo_id=14))
        a=early["by_route"][ROUTES[0]]
        b=later["by_route"][ROUTES[0]]
        self.assertNotEqual(a["sink_input_id"],b["sink_input_id"])
        self.assertEqual(a["client"],b["client"])
        self.assertEqual(a["_private_run_pid"],b["_private_run_pid"])

    def test_uncorked_is_not_hardcoded(self):
        s=self.parse(fixture().replace("Corked: no","Corked: yes",1))
        self.assertTrue(s["by_route"][ROUTES[0]]["corked"])
        self.assertFalse(s["by_route"][ROUTES[1]]["corked"])

    def test_unknown_application_refused(self):
        with self.assertRaisesRegex(ValueError,"Unrecognized"):
            self.parse(fixture().replace("ALSA plug-in [nexium]","unknown"))

    def test_duplicate_sink_input_id_refused(self):
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            self.parse(fixture(stereo_id=2,other_id=2))

    def test_wrong_sample_profile_refused(self):
        with self.assertRaisesRegex(ValueError,"Unexpected original"):
            self.parse(fixture().replace("384000Hz","48000Hz"))

    def test_missing_corked_refused(self):
        with self.assertRaisesRegex(ValueError,"Corked"):
            self.parse(fixture().replace("Corked: no","Corked: maybe",1))

    def test_ambiguous_corked_refused(self):
        with self.assertRaisesRegex(ValueError,"ambiguous"):
            self.parse(fixture().replace("Corked: no",
                              "Corked: no\n\tCorked: no",1))

    def test_two_processes_refused(self):
        with self.assertRaisesRegex(ValueError,"multiple unrelated"):
            self.parse(fixture().replace('application.process.id = "100"',
                                        'application.process.id = "777"',1))

    def test_missing_sink_input_refused(self):
        with self.assertRaisesRegex(ValueError,"Expected exactly"):
            self.parse(fixture().split("Sink Input #94")[0]+"\n")

    def test_symlink_refused(self):
        shortcut=self.path.parent/"link.txt"
        shortcut.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError,"unavailable"):
            parse_pulse_snapshot(shortcut)

if __name__=="__main__":
    unittest.main()
