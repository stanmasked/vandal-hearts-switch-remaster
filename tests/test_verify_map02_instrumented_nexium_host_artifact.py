"""ROM-free ELF artifact provenance checks for the opt-in Stage276 host build."""
import copy
import hashlib
import json
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from verify_map02_instrumented_nexium_host_artifact import (
    FILES, HOST_SCHEMA, LOCK, RESEARCH, SOURCE, verify,
)

def fake_elf():
    raw=bytearray(110_000)
    raw[0:6]=b"\x7fELF\x02\x01"
    struct.pack_into("<H",raw,16,3)
    struct.pack_into("<H",raw,18,62)
    raw[80:80+len(b"VH_MAP02_CPAL_TRACE_PATH")]=b"VH_MAP02_CPAL_TRACE_PATH"
    raw[150:150+len(b"map02-cpal-counts")]=b"map02-cpal-counts"
    return bytes(raw)


def manifest(raw):
    return {
        "schema":HOST_SCHEMA,
        "result":"OPT_IN_INSTRUMENTED_NEXIUM_LINUX_BINARY_COMPILED",
        "research_head_sha":RESEARCH,
        "pinned_upstream_source_sha":SOURCE,
        "cargo_lock_sha256":LOCK,
        "executable_sha256":hashlib.sha256(raw).hexdigest(),
        "executable_size_bytes":len(raw),
        "platform":"linux-x86_64",
        "cpu_backend":"rustarmic",
        "build_profile":"release",
        "cpal_trace_opt_in_env_present":True,
        "nightly_binary_equivalence_proven":False,
        "emulator_guest_boot_proven":False,
        "cpal_callback_runtime_activity_proven":False,
        "guest_audout_service_root_cause_proven":False,
        "physical_nintendo_switch_audio_proven":False,
        "licensed_game_rom_or_pcm_included":False,
        "rustc_version":"rustc 1.99.1 (synthetic)",
        "cargo_version":"cargo 1.99.1 (synthetic)",
        "source_overlay_files":[
            {"path":path,"sha256_before":hashlib.sha256(("base"+path).encode()).hexdigest(),
             "sha256_after":hashlib.sha256(("patched"+path).encode()).hexdigest()}
            for path in sorted(FILES)
        ],
    }


class ExperimentalHostArtifactTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.elf=self.root/"nexium"
        self.json=self.root/"manifest.json"
        raw=fake_elf()
        self.elf.write_bytes(raw)
        self.elf.chmod(0o700)
        self.json.write_text(json.dumps(manifest(raw)))
    def data(self):
        return json.loads(self.json.read_text())
    def save(self,value):
        self.json.write_text(json.dumps(value))
    def reject_manifest(self,key,value,msg):
        m=self.data()
        m[key]=value
        self.save(m)
        with self.assertRaisesRegex(ValueError,msg):
            verify(self.root)

    def test_valid_elf_bound_to_exact_source_and_lock_without_guest_claims(self):
        r=verify(self.root)
        self.assertEqual(r["result"],
                         "EXACT_SOURCE_INSTRUMENTED_HOST_ELF_ARTIFACT_VERIFIED")
        self.assertEqual(r["pinned_research_build_source_sha"],RESEARCH)
        self.assertTrue(r["opt_in_cpal_reporter_symbols_present"])
        self.assertFalse(r["guest_emulator_boot_or_cpal_execution_proven"])
        self.assertFalse(r["historical_nightly_binary_equivalent"])
        self.assertFalse(r["physical_switch_speaker_audio_proven"])

    def test_missing_binary_is_unverified(self):
        self.elf.unlink()
        with self.assertRaisesRegex(ValueError,"Missing"):
            verify(self.root)

    def test_symlink_to_executable_is_refused(self):
        real=self.root/"real"
        self.elf.rename(real)
        self.elf.symlink_to(real)
        with self.assertRaisesRegex(ValueError,"symlinks"):
            verify(self.root)

    def test_content_hash_mismatch_detects_modified_elf(self):
        raw=self.elf.read_bytes()
        self.elf.write_bytes(raw[:10]+b"A"+raw[11:])
        with self.assertRaisesRegex(ValueError,"executable_sha256"):
            verify(self.root)

    def test_no_runtime_callback_marker_is_rejected_even_if_hash_forged(self):
        raw=self.elf.read_bytes().replace(b"map02-cpal-counts",b"map02-cpal-offxx")
        self.elf.write_bytes(raw)
        m=self.data()
        m["executable_sha256"]=hashlib.sha256(raw).hexdigest()
        self.save(m)
        with self.assertRaisesRegex(ValueError,"reporter marker"):
            verify(self.root)

    def test_wrong_elf_machine_rejected(self):
        raw=bytearray(self.elf.read_bytes())
        struct.pack_into("<H",raw,18,183)
        self.elf.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,"x86-64 ELF"):
            verify(self.root)

    def test_mismatched_source_sha_rejected(self):
        self.reject_manifest("pinned_upstream_source_sha","0"*40,"pinned_upstream_source_sha")

    def test_wrong_research_build_identity_rejected(self):
        self.reject_manifest("research_head_sha","0"*40,"research_head_sha")

    def test_different_resolved_cargo_lock_rejected(self):
        self.reject_manifest("cargo_lock_sha256","b"*64,"cargo_lock_sha256")

    def test_never_accept_claim_of_original_nightly_equivalence(self):
        self.reject_manifest("nightly_binary_equivalence_proven",True,
                             "nightly_binary_equivalence_proven")

    def test_never_accept_claim_of_guest_boot(self):
        self.reject_manifest("emulator_guest_boot_proven",True,"emulator_guest_boot_proven")

    def test_missing_source_overlay_rejected(self):
        m=self.data()
        m["source_overlay_files"].pop()
        self.save(m)
        with self.assertRaisesRegex(ValueError,"three-file"):
            verify(self.root)

    def test_duplicated_overlay_path_rejected(self):
        m=self.data()
        m["source_overlay_files"][1]=copy.deepcopy(m["source_overlay_files"][0])
        self.save(m)
        with self.assertRaisesRegex(ValueError,"Duplicate source"):
            verify(self.root)

    def test_unchanged_source_file_sha_rejected(self):
        m=self.data()
        m["source_overlay_files"][0]["sha256_after"]=m["source_overlay_files"][0]["sha256_before"]
        self.save(m)
        with self.assertRaisesRegex(ValueError,"unchanged source"):
            verify(self.root)

    def test_absent_executable_permission_rejected(self):
        self.elf.chmod(0o600)
        with self.assertRaisesRegex(ValueError,"executable"):
            verify(self.root)

    def test_manifest_symlink_rejected(self):
        real=self.root/"real_manifest"
        self.json.rename(real)
        self.json.symlink_to(real)
        with self.assertRaisesRegex(ValueError,"symlinks"):
            verify(self.root)

    def test_malformed_manifest_not_a_success(self):
        self.json.write_text("{broken")
        with self.assertRaisesRegex(ValueError,"Unreadable"):
            verify(self.root)

if __name__=="__main__":
    unittest.main()
