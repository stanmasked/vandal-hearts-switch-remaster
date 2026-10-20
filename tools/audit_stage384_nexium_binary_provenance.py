#!/usr/bin/env python3
"""Identify the *actual* NeXium nightly bytes used in one Stage371 guest run.

This records a run-scoped binary fingerprint, NOT a verified emulator release,
reproducibility across historic runs, audible music or Nintendo Switch hardware.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ASSET = "nexium-linux-x86_64.tar.gz"
SCHEMA = "vh-stage384-nexium-runtime-bytes/v1"
RESULT = "STAGE384_ONE_GUEST_RUN_NEXIUM_BYTES_PINNED"
HEX = re.compile(r"[0-9a-f]{64}\Z")
GIT = re.compile(r"[0-9a-f]{40}\Z")

class ProvenanceError(ValueError):
    pass

def require(value, reason):
    if not value:
        raise ProvenanceError(reason)

def file_bytes(path:Path, limit:int)->bytes:
    require(path.is_file() and not path.is_symlink(), "missing or symlink input")
    size=path.stat().st_size
    require(0<size<=limit,"empty or oversized input")
    return path.read_bytes()

def digest(content):
    return hashlib.sha256(content).hexdigest()

def release_identity(release_json:bytes, archive:bytes):
    try:
        source=json.loads(release_json)
    except (ValueError,UnicodeError) as exc:
        raise ProvenanceError("invalid release JSON") from exc
    require(type(source) is dict and source.get("tag_name")=="nightly",
            "wrong release tag or schema")
    require(type(source.get("id")) is int and source["id"]>0,
            "missing release identity")
    assets=source.get("assets")
    require(type(assets) is list,"missing assets")
    found=[a for a in assets if type(a) is dict and a.get("name")==ASSET]
    require(len(found)==1,"missing or duplicated NeXium release asset")
    a=found[0]
    require(type(a.get("id")) is int and a["id"]>0,
            "missing numeric asset id")
    require(type(a.get("size")) is int and a["size"]==len(archive),
            "downloaded archive size differs from release metadata")
    require(a.get("state")=="uploaded","release asset was not uploaded")
    received=digest(archive)
    advertised=a.get("digest")
    if advertised is not None:
        require(type(advertised) is str and advertised=="sha256:"+received,
                "GitHub release asset digest differs from actual archive")
    return {"release_id":source["id"],"release_tag":"nightly",
            "release_asset_id":a["id"],"asset_name":ASSET,
            "asset_size_bytes":len(archive),"asset_sha256":received,
            "advertised_asset_digest_checked":advertised is not None}

def make_receipt(release:Path, archive:Path, binary:Path, *, run_id:int, head:str):
    require(type(run_id) is int and run_id>0, "invalid GitHub run ID")
    require(type(head) is str and GIT.fullmatch(head),"invalid Git commit")
    rel=file_bytes(release,2_000_000)
    art=file_bytes(archive,500_000_000)
    executable=file_bytes(binary,1_000_000_000)
    require(os.access(binary,os.X_OK),"NeXium binary lacks execute permission")
    asset=release_identity(rel,art)
    return {"schema":SCHEMA,"result":RESULT,
            "origin":"GitHub public release API; mutable nightly tag; no binary signature verified",
            "source_run_id":run_id,"source_head_sha":head,
            **asset,"binary_name":binary.name,
            "binary_size_bytes":len(executable),"binary_sha256":digest(executable),
            "different_run_binary_identity_proven":False,
            "same_binary_in_historical_runs_proven":False,
            "hardware_status":"HARDWARE NOT TESTED",
            "physical_audio_output_tested":False}

def verify_receipt(receipt:Path, archive:Path, binary:Path, *, run_id:int, head:str):
    r=json.loads(file_bytes(receipt,100_000))
    require(type(r) is dict and r.get("schema")==SCHEMA and r.get("result")==RESULT,
            "receipt schema/result differs")
    require(r.get("source_run_id")==run_id and r.get("source_head_sha")==head,
            "receipt belongs to another guest run or source commit")
    require(r.get("asset_name")==ASSET and r.get("release_tag")=="nightly" and
            type(r.get("release_asset_id")) is int and r["release_asset_id"]>0,
            "invalid source release identity")
    art=file_bytes(archive,500_000_000)
    exe=file_bytes(binary,1_000_000_000)
    require(os.access(binary,os.X_OK),"NeXium executable permission changed")
    require(r.get("asset_size_bytes")==len(art) and
            r.get("asset_sha256")==digest(art),"downloaded nightly archive changed")
    require(r.get("binary_name")==binary.name and
            r.get("binary_size_bytes")==len(exe) and
            r.get("binary_sha256")==digest(exe),"NeXium binary changed during guest execution")
    require(r.get("hardware_status")=="HARDWARE NOT TESTED" and
            r.get("physical_audio_output_tested") is False and
            r.get("same_binary_in_historical_runs_proven") is False,
            "receipt must not claim cross-run or physical confirmation")
    return {"result":"STAGE384_SAME_NEXIUM_BINARY_BEFORE_AND_AFTER_GUEST_RUN",
            "source_run_id":run_id,"asset_sha256":r["asset_sha256"],
            "binary_sha256":r["binary_sha256"],"hardware_status":"HARDWARE NOT TESTED"}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode",choices=("create","verify"))
    p.add_argument("--release",type=Path)
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--binary",type=Path,required=True)
    p.add_argument("--receipt",type=Path,required=True)
    p.add_argument("--run-id",type=int,required=True)
    p.add_argument("--head",required=True)
    a=p.parse_args(argv)
    try:
        if a.mode=="create":
            require(a.release is not None,"missing original release metadata")
            require(not a.receipt.exists() and not a.receipt.is_symlink(),
                    "will not overwrite receipt")
            r=make_receipt(a.release,a.archive,a.binary,run_id=a.run_id,head=a.head)
            a.receipt.parent.mkdir(parents=True,exist_ok=True)
            with a.receipt.open("x",encoding="utf-8") as f:
                json.dump(r,f,indent=2,sort_keys=True)
                f.write("\n")
            print(json.dumps({"result":RESULT,"binary_sha256":r["binary_sha256"],
                              "asset_sha256":r["asset_sha256"]},sort_keys=True))
        else:
            print(json.dumps(verify_receipt(a.receipt,a.archive,a.binary,
                          run_id=a.run_id,head=a.head),sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,UnicodeError) as e:
        # Report only our fixed validation failure messages: the old generic
        # ProvenanceError hid whether release hash, size or executable bounds failed.
        reason=str(e) if isinstance(e,ProvenanceError) else None
        print(json.dumps({"result":"STAGE384_NEIXUM_BYTES_NOT_VERIFIED",
                          "error_kind":type(e).__name__,
                          "validation_reason":reason,
                          "hardware_status":"HARDWARE NOT TESTED"},sort_keys=True),file=sys.stderr)
        return 2

if __name__=="__main__":
    sys.exit(main())
