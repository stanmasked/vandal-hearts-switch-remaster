#!/usr/bin/env python3
"""Fail closed on experimental Stage276 NeXium ELF executable provenance.

Checks only the *research-only host artifact*. It does not boot an emulator,
prove 21/22-ms behavior, infer a physical Nintendo Switch speaker result,
or identify a historical nightly binary's source commit.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct

SCHEMA="vh-map02-nexium-instrumented-host-artifact-audit/v1"
HOST_SCHEMA="vh-map02-nexium-cpal-host-build/v1"
SOURCE="089562567a0a8760dfdd8420e1f57c35159a9219"
RESEARCH="6d24825f45f286dc3ec109d25c0abbc9f864e59d"
LOCK="e6e8fcb90624650afddd1f25327dd4e6b042b094e8336cb5f43d2dc370e28739"
FILES={
    "nexium-runner/src/audio.rs",
    "nexium-kernel/src/services/audio_out/handlers.rs",
    "nexium-runner/Cargo.toml",
}
SHA=re.compile(r"[0-9a-f]{64}\Z")


def require(condition,reason):
    if not condition: raise ValueError(reason)


def verify(root):
    root=root.resolve(strict=True)
    binary=root/"nexium"
    manifest_path=root/"manifest.json"
    require(not binary.is_symlink() and not manifest_path.is_symlink(),
            "No symlinks accepted for host artifact or manifest")
    require(binary.is_file() and manifest_path.is_file(),
            "Missing research ELF executable or manifest.json")
    require((binary.stat().st_mode & stat.S_IXUSR)!=0,
            "Experimental host ELF must be executable")
    raw=binary.read_bytes()
    require(100_000<len(raw)<500_000_000,"Unexpected ELF executable size")
    require(raw[:4]==b"\x7fELF" and raw[4]==2 and raw[5]==1,
            "Expected 64-bit little-endian ELF executable")
    require(struct.unpack_from("<H",raw,18)[0]==62,
            "Not x86-64 ELF")
    require(struct.unpack_from("<H",raw,16)[0] in (2,3),
            "Not executable / PIE ELF type")
    for marker in (b"VH_MAP02_CPAL_TRACE_PATH",b"map02-cpal-counts"):
        require(marker in raw,"Compiled ELF missing CPAL reporter marker")
    try:
        m=json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeError,json.JSONDecodeError) as exc:
        raise ValueError("Unreadable host manifest JSON") from exc
    require(type(m) is dict,"Host manifest must be object")
    def exact(key,value):
        require(m.get(key)==value,f"Manifest field {key} does not match pinned value")
    exact("schema",HOST_SCHEMA)
    exact("result","OPT_IN_INSTRUMENTED_NEXIUM_LINUX_BINARY_COMPILED")
    exact("research_head_sha",RESEARCH)
    exact("pinned_upstream_source_sha",SOURCE)
    exact("cargo_lock_sha256",LOCK)
    exact("executable_sha256",hashlib.sha256(raw).hexdigest())
    exact("executable_size_bytes",len(raw))
    exact("platform","linux-x86_64")
    exact("cpu_backend","rustarmic")
    exact("build_profile","release")
    for k in ("cpal_trace_opt_in_env_present",):
        exact(k,True)
    for k in (
        "nightly_binary_equivalence_proven",
        "emulator_guest_boot_proven",
        "cpal_callback_runtime_activity_proven",
        "guest_audout_service_root_cause_proven",
        "physical_nintendo_switch_audio_proven",
        "licensed_game_rom_or_pcm_included",
    ):
        exact(k,False)
    require(bool(re.fullmatch(r"rustc [0-9].*",str(m.get("rustc_version")))),
            "Compiler version missing")
    require(bool(re.fullmatch(r"cargo [0-9].*",str(m.get("cargo_version")))),
            "Cargo version missing")
    entries=m.get("source_overlay_files")
    require(type(entries) is list and len(entries)==len(FILES),
            "Expected exact three-file source provenance")
    observed=set()
    for entry in entries:
        require(type(entry) is dict and entry.get("path") in FILES,
                "Unknown source file in manifest")
        name=entry["path"]
        require(name not in observed,"Duplicate source file provenance")
        observed.add(name)
        before=entry.get("sha256_before")
        after=entry.get("sha256_after")
        require(type(before) is str and type(after) is str and
                SHA.fullmatch(before) and SHA.fullmatch(after) and before!=after,
                "Malformed or unchanged source file SHA-256")
    require(observed==FILES,"Incomplete source provenance")
    return {
        "schema":SCHEMA,
        "result":"EXACT_SOURCE_INSTRUMENTED_HOST_ELF_ARTIFACT_VERIFIED",
        "observed_elf_sha256":hashlib.sha256(raw).hexdigest(),
        "observed_elf_size_bytes":len(raw),
        "pinned_neixum_source_sha":SOURCE,
        "pinned_research_build_source_sha":RESEARCH,
        "pinned_cargo_lock_sha256":LOCK,
        "source_overlay_paths_verified":sorted(FILES),
        "rustc_version":m["rustc_version"],
        "executable_is_linux_x86_64_elf":True,
        "opt_in_cpal_reporter_symbols_present":True,
        "historical_nightly_binary_equivalent":False,
        "guest_emulator_boot_or_cpal_execution_proven":False,
        "game_audio_transport_correctness_proven":False,
        "physical_switch_speaker_audio_proven":False,
        "licensed_game_data_examined":False,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifact-dir",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    try:
        report=verify(a.artifact_dir)
        status=0
    except (OSError,ValueError,TypeError,OverflowError,IndexError) as exc:
        report={
            "schema":SCHEMA,"result":"UNVERIFIED","reason":str(exc),
            "historical_nightly_binary_equivalent":False,
            "guest_emulator_boot_or_cpal_execution_proven":False,
            "game_audio_transport_correctness_proven":False,
            "physical_switch_speaker_audio_proven":False,
        }
        status=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))
    return status


if __name__=="__main__":
    raise SystemExit(main())
