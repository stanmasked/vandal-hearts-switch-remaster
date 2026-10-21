"""Stage304 synthetic symbol-export parsing tests; not real ALSA invocations."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_alsa_symbols_stage304 import SYMBOLS,SCHEMA

class ALSAPreflightTests(unittest.TestCase):
    def test_symbol_list_bounded_and_unique(self):
        self.assertEqual(len(SYMBOLS),9)
        self.assertEqual(len(set(SYMBOLS)),len(SYMBOLS))
    def test_avail_delay_explicit(self):
        self.assertIn("snd_pcm_avail_delay",SYMBOLS)
    def test_no_unsafe_raw_paths_in_schema(self):
        self.assertTrue(SCHEMA.startswith("vh-map02-stage304"))
    def test_no_symbol_can_be_interpreted_as_hardware(self):
        self.assertTrue(all(x.startswith("snd_pcm_") for x in SYMBOLS))
if __name__=="__main__": unittest.main()
