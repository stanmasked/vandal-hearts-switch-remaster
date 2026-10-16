#!/usr/bin/env python3
"""v69 PS1 GPU plugin call-entry/return audit and strictly pinned source patch tests."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch as mock_patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.audit_map02_v69_plugin_callbacks import audit,main,DmaError
from tools.apply_map02_v69_pcsx_rearmed import once

APIS=("writeData","writeDataMem","writeStatus","dmaChain")

def build(pairs=APIS):
    r=[{"kind":"GPU_PLUGIN_CALLBACK","seq":1,"api":"bind","stage":"complete"}]
    for api in pairs:
        r.append({"kind":"GPU_PLUGIN_CALLBACK","seq":len(r)+1,
                  "api":api,"stage":"enter"})
        r.append({"kind":"GPU_PLUGIN_CALLBACK","seq":len(r)+1,
                  "api":api,"stage":"return"})
    return r

def serialized(events):
    return ("\n".join(json.dumps(x,sort_keys=True,separators=(",",":")) for x in events)+"\n").encode()

class PluginCallbackTests(unittest.TestCase):
    def setUp(self):self.records=build()
    def rejected(self,records=None):
        with self.assertRaises((DmaError,ValueError,TypeError)):
            audit(serialized(self.records if records is None else records))
    def test_four_real_function_signature_pairs(self):
        result=audit(serialized(self.records))
        self.assertEqual(result["plugin_callbacks_entered_and_returned"],4)
        self.assertEqual(result["plugin_callback_counts"],dict.fromkeys(sorted(APIS),1))
    def test_bind_only_valid_for_no_media_core_init(self):
        r=audit(serialized(build(())))
        self.assertEqual(r["plugin_callbacks_entered_and_returned"],0)
        self.assertEqual(r["callback_bind_events"],1)
    def test_no_binary_pixel_or_authenticity_claim(self):
        r=audit(serialized(self.records))
        for key in ("gpu_plugin_fifo_consumption_verified",
                    "gpu_rendering_or_pixel_parity_verified",
                    "real_game_boot_verified",
                    "retail_gp0_provenance_verified",
                    "original_retail_MAP02_verified",
                    "HD_replacement_approved","raw_gpu_payload_exported"):
            self.assertIs(r[key],False)
    def test_no_data_echoed_in_report(self):
        s=json.dumps(audit(serialized(self.records)))
        for word in ("e6000003","0x6000","first_vertex","private.png",
                     "gpu_word","texture"):
            self.assertNotIn(word,s)
    def test_reject_unknown_gpu_callback(self):
        e=build(("writeData",))
        e[1]["api"]="rasterComplete"
        self.rejected(e)
    def test_reject_unknown_callback_phase(self):
        e=build(("writeData",))
        e[1]["stage"]="pixels_done"
        self.rejected(e)
    def test_reject_mismatched_enter_return_pair(self):
        e=build(("writeData",))
        e[2]["api"]="writeStatus"
        self.rejected(e)
    def test_reject_nested_callback_without_support(self):
        e=build(("writeData",))
        e[2]["stage"]="enter"
        self.rejected(e)
    def test_reject_dangling_enter(self):
        e=build(("writeData",))
        del e[-1]
        self.rejected(e)
    def test_reject_return_before_enter(self):
        e=build(("writeData",))
        e[1]["stage"]="return"
        self.rejected(e)
    def test_reject_duplicate_bind(self):
        e=build()
        e[1]["api"]="bind"
        e[1]["stage"]="complete"
        self.rejected(e)
    def test_reject_no_bind(self):
        e=build()
        del e[0]
        self.rejected(e)
    def test_reject_disordered_seq(self):
        e=build()
        e[3]["seq"]=3
        self.rejected(e)
    def test_reject_non_integer_seq(self):
        e=build()
        e[3]["seq"]=True
        self.rejected(e)
    def test_reject_extra_privacy_field(self):
        e=build()
        e[1]["gpu_ram"]="PRIVATE"
        self.rejected(e)
    def test_reject_false_provenance_flag(self):
        e=build()
        e[1]["authentic_retail"]=True
        self.rejected(e)
    def test_reject_duplicate_json_key(self):
        with self.assertRaises(DmaError):
            audit(b'{"kind":"GPU_PLUGIN_CALLBACK","seq":1,"api":"bind","api":"writeData","stage":"complete"}\n')
    def test_reject_blank_event(self):
        with self.assertRaises(DmaError):
            audit(serialized(build())+b"\n")
    def test_reject_truncated_final_line(self):
        with self.assertRaises(DmaError):
            audit(serialized(build()).rstrip(b"\n"))
    def test_reject_oversized_log(self):
        with self.assertRaises(DmaError):
            audit(b"x"*(1024*1024+1))
    def test_reject_empty_log(self):
        with self.assertRaises(DmaError):
            audit(b"")
    def test_reject_extra_event_kind(self):
        e=build()
        e[2]["kind"]="GPU_PLUGIN_PIXELS_VERIFIED"
        self.rejected(e)
    def test_callback_can_be_called_multiple_times(self):
        e=build(("writeData","writeData","dmaChain"))
        v=audit(serialized(e))
        self.assertEqual(v["plugin_callback_counts"]["writeData"],2)
        self.assertEqual(v["plugin_callback_counts"]["dmaChain"],1)
    def test_cli_safe_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            log=root/"private-callbacks.jsonl";log.write_bytes(serialized(self.records))
            out=root/"safe.json"
            with mock_patch.object(sys,"argv",["v69","--log",str(log),"--output",str(out)]),redirect_stdout(StringIO()):
                self.assertEqual(main(),0)
            self.assertEqual(json.loads(out.read_text())["plugin_callbacks_entered_and_returned"],4)
            self.assertNotIn(str(root),out.read_text())
    def test_cli_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            log=root/"private-callbacks.jsonl";original=serialized(self.records);log.write_bytes(original)
            with mock_patch.object(sys,"argv",["v69","--log",str(log),"--output",str(log)]),redirect_stdout(StringIO()):
                self.assertEqual(main(),2)
            self.assertEqual(log.read_bytes(),original)
    def test_unique_upstream_anchor_refuses_missing_and_duplicates(self):
        with self.assertRaises(ValueError):once("something","missing","value","callback")
        with self.assertRaises(ValueError):once("gp0 gp0","gp0","x","callback")
    def test_unique_upstream_anchor_can_insert_once(self):
        self.assertEqual(once("AxxB","xx","pp","test"),"AppB")
    def test_mock_plugin_callback_counts_not_gpu_raster(self):
        self.assertFalse(audit(serialized(self.records))["gpu_plugin_fifo_consumption_verified"])

if __name__=="__main__":
    unittest.main()
