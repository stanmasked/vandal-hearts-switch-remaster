#!/usr/bin/env python3
"""Stage376: source-attested *native* integrated NRO handoff; never hardware PASS.

Reads an immutable original GitHub Actions artifact ZIP and separate live
GitHub provenance JSON. Stdlib only, no sound samples, no unsigned claim of
physical execution. No network or writes unless explicit --output provided.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import struct
import sys
import zipfile

REPO = "stanmasked/vandal-hearts-switch-remaster"
HEAD = "7df0d02c93217b6f077e6ba30de9e1a554d95b9a"
SOURCE_RUN = 39453952599
SOURCE_ARTIFACT = 12278869762
SOURCE_ARTIFACT_NAME = "vandal-hearts-tactical-with-native-music"
SOURCE_ZIP_SHA = "cfc6ce877d238850d1d72c735f390e6a55c0729f4da72dade344af11f8c9ef97"
SOURCE_NRO_SHA = "cfc49a8ac8dcfe4704e697c1bea8fc750ea32d498c2942176c2ca9b9cbcae71b"
SOURCE_NRO_SIZE = 299064
SOURCE_NRO_DECLARED_SIZE = 282624
NRO_NAME = "vandal-hearts-prototype.nro"
HASH_NAME = "tactical-native.sha256"
NATIVE_JOBS = {
    "host_spu": (39453952411, "Host SPU audio regressions"),
    "native_pcm": (39453952443, "Switch native PCM transport cross-compile"),
    "stage374": (39453952772, "Stage374 recheck eight original NeXium optical exit sessions"),
    "native_audout": (39453952461, "Switch libnx audout music NRO"),
}
SDL2_RUN = 39453952566
RESULT = "STAGE376_PINNED_INTEGRATED_NRO_BYTES_AND_NATIVE_CI_PROVENANCE_VERIFIED"

class AuditError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise AuditError(message)

def sha(value):
    return hashlib.sha256(value).hexdigest()

def regular_bytes(path, max_bytes):
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), "missing or linked source: " + path.name)
    stat = path.stat()
    require(stat.st_nlink == 1 and 0 < stat.st_size <= max_bytes,
            "invalid source size or hard link: " + path.name)
    return path.read_bytes()

def object_json(path):
    obj = json.loads(regular_bytes(path, 1_000_000))
    require(type(obj) is dict, "JSON metadata must be object")
    return obj

def validate_nro(blob, *, expected_sha=SOURCE_NRO_SHA, expected_size=SOURCE_NRO_SIZE,
                 expected_declared=SOURCE_NRO_DECLARED_SIZE):
    require(len(blob) == expected_size, "NRO byte count changed")
    require(sha(blob) == expected_sha, "NRO digest differs from independent source pin")
    require(len(blob) >= 0x80 and blob[0x10:0x14] == b"NRO0", "NRO0 header absent")
    declared = struct.unpack_from("<I", blob, 0x18)[0]
    require(declared == expected_declared and declared <= len(blob), "NRO declared image size changed or truncated")
    ranges = []
    for name, field in (("text", 0x20), ("rodata", 0x28), ("data", 0x30)):
        off, size = struct.unpack_from("<II", blob, field)
        require(size > 0 and off >= 0 and off < declared and off + size <= declared,
                "out-of-bounds NRO segment: " + name)
        ranges.append([off, off+size])
    require(all(ranges[i][1] <= ranges[i+1][0] for i in range(2)),
            "overlapping or unordered NRO segments")
    return {"nro_sha256": sha(blob), "nro_bytes":len(blob),
            "declared_nro_size":declared, "nro_structure":"THREE_BOUNDED_NONOVERLAPPING_SEGMENTS"}

def validate_zip(raw, *, zip_sha=SOURCE_ZIP_SHA,
                 nro_sha=SOURCE_NRO_SHA, nro_size=SOURCE_NRO_SIZE,
                 nro_declared=SOURCE_NRO_DECLARED_SIZE):
    require(sha(raw) == zip_sha, "original Actions ZIP digest mismatch")
    with zipfile.ZipFile(io.BytesIO(raw), "r") as z:
        info=z.infolist()
        names=[f.filename for f in info]
        require(len(info)==2 and set(names)=={NRO_NAME,HASH_NAME},
                "archive contains missing, duplicate or extra members")
        for f in info:
            require(not f.is_dir() and not f.filename.startswith("/")
                    and ".." not in Path(f.filename).parts,
                    "unsafe archive path")
            require((f.external_attr >> 16) & 0o170000 not in (0o120000, 0o040000),
                    "archive member is a link or directory")
            require(f.file_size <= 350000, "oversized source archive member")
        require(z.testzip() is None, "archive member CRC mismatch")
        nro=z.read(NRO_NAME)
        text=z.read(HASH_NAME)
    require(len(text) <= 256 and text.decode("ascii") in
            (f"{nro_sha}  build/{NRO_NAME}\n", f"{nro_sha}  {NRO_NAME}\n"),
            "embedded hash row changed")
    result=validate_nro(nro,expected_sha=nro_sha,expected_size=nro_size,
                        expected_declared=nro_declared)
    return {**result,"source_archive_sha256":sha(raw),"artifact_entries":names}

def check_run(run, id, head=HEAD, *, name=None):
    require(run.get("id")==id and run.get("status")=="completed"
            and run.get("conclusion")=="success" and run.get("head_sha")==head
            and run.get("event")=="pull_request" and run.get("run_attempt")==1
            and run.get("repository",{}).get("full_name")==REPO,
            "original GitHub workflow run not authenticated")
    if name is not None:
        require(run.get("name")==name, "wrong GitHub workflow")

def audit(zip_path, metadata_dir, *, head=HEAD, run_id=SOURCE_RUN,
          artifact_id=SOURCE_ARTIFACT, artifact_name=SOURCE_ARTIFACT_NAME,
          archive_sha=SOURCE_ZIP_SHA, nro_sha=SOURCE_NRO_SHA,
          nro_size=SOURCE_NRO_SIZE, nro_declared=SOURCE_NRO_DECLARED_SIZE,
          native_jobs=NATIVE_JOBS, sdl2_run=SDL2_RUN):
    original=regular_bytes(zip_path, 1_000_000)
    image=validate_zip(original,zip_sha=archive_sha,nro_sha=nro_sha,
                       nro_size=nro_size,nro_declared=nro_declared)
    run=object_json(metadata_dir/"integrated-run.json")
    jobs=object_json(metadata_dir/"integrated-jobs.json")
    artifact=object_json(metadata_dir/"integrated-artifact.json")
    check_run(run,run_id,head)
    actual_jobs=jobs.get("jobs")
    require(type(actual_jobs) is list, "missing native build job list")
    native_name="Build tactical framebuffer game with nonblocking libnx audout"
    relevant=[j for j in actual_jobs if j.get("name")==native_name]
    require(len(relevant)==1 and relevant[0].get("run_id")==run_id
            and relevant[0].get("status")=="completed"
            and relevant[0].get("conclusion")=="success",
            "original integrated native build not completed")
    require(artifact.get("id")==artifact_id and artifact.get("name")==artifact_name
            and artifact.get("digest")=="sha256:"+archive_sha
            and artifact.get("expired") is False
            and artifact.get("size_in_bytes")==len(original)
            and artifact.get("workflow_run",{}).get("id")==run_id
            and artifact["workflow_run"].get("head_sha")==head,
            "wrong original CI artifact metadata")
    checked=[]
    for label,(id,workflow_name) in native_jobs.items():
        x=object_json(metadata_dir/(label+"-run.json"))
        check_run(x,id,head,name=workflow_name)
        checked.append({"run_id":id,"workflow_name":workflow_name,"conclusion":"success"})
    # Explicitly retain the red optional dependency; no false 'all green'.
    optional=object_json(metadata_dir/"optional-sdl2-run.json")
    require(optional.get("id")==sdl2_run and optional.get("head_sha")==head
            and optional.get("status")=="completed"
            and optional.get("conclusion")=="failure",
            "unacknowledged or changed optional SDL2 status")
    return {"schema":"vh-stage376-original-native-handoff-review/v1",
            "result":RESULT,"source_repository":REPO,"source_pr":176,
            "source_head_sha":head,"source_run_id":run_id,
            "source_artifact_id":artifact_id,"source_artifact_name":artifact_name,
            **image,"independent_native_ci":checked,
            "optional_sdl2": {"run_id":sdl2_run,"status":"FAILED_EXTERNAL_DEPENDENCY_NOT_RECLASSIFIED"},
            "guest_software_tested":True,"hardware_status":"HARDWARE NOT TESTED",
            "physical_speaker_audio_tested":False,"switch_home_sleep_tested":False,
            "soundtrack_assets_included":False,
            "note":"Read-only source-bound gate for an existing tactical prototype, not a new guest execution or commercial remake release."}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-zip",type=Path,required=True)
    parser.add_argument("--metadata",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    opts=parser.parse_args(argv)
    try:
        require(not opts.output.exists() and not opts.output.is_symlink(),
                "refuse to overwrite Stage376 receipt")
        result=audit(opts.artifact_zip,opts.metadata)
        opts.output.parent.mkdir(parents=True,exist_ok=True)
        with opts.output.open("x",encoding="utf-8") as f:
            json.dump(result,f,ensure_ascii=False,indent=2,sort_keys=True)
            f.write("\n")
        print(json.dumps({"result":RESULT,"nro_sha256":result["nro_sha256"],
                         "native_ci":len(result["independent_native_ci"]),
                         "hardware_status":result["hardware_status"]},sort_keys=True))
        return 0
    except (AuditError,OSError,ValueError,TypeError,KeyError,zipfile.BadZipFile,
            UnicodeError,struct.error,json.JSONDecodeError) as e:
        print(json.dumps({"result":"STAGE376_NATIVE_HANDOFF_NOT_VERIFIED",
                          "error_kind":type(e).__name__,"hardware_status":"HARDWARE NOT TESTED"},sort_keys=True))
        return 2

if __name__=="__main__":
    sys.exit(main())