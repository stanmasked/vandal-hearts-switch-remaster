#!/usr/bin/env python3
"""Fail-closed *pre-extraction* check for the exact NeXium nightly release TAR.

This is a source/transport check, not a signature, emulator attestation,
rom validator, guest audio test or proof of physical Switch execution.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile

ASSET="nexium-linux-x86_64.tar.gz"
SCHEMA="vh-stage385-nexium-archive-preextract/v1"
RESULT="STAGE385_RELEASE_ARCHIVE_BYTES_AND_TAR_PATHS_VERIFIED"
MAX_ARCHIVE=500_000_000
MAX_MEMBERS=100_000
MAX_TOTAL=3_000_000_000
MAX_MEMBER=1_500_000_000

class UnsafeTarError(ValueError): pass

def check(cond,why):
    if not cond: raise UnsafeTarError(why)

def data_from_file(p:Path, max_size:int)->bytes:
    check(p.is_file() and not p.is_symlink(),"input is missing or symbolic link")
    length=p.stat().st_size
    check(0<length<=max_size,"input file size outside bounds")
    return p.read_bytes()

def path_parts(name):
    check(isinstance(name,str) and name and "\\" not in name and "\x00" not in name,
          "unsafe non-POSIX member path")
    # GNU tar archives often contain './' directory headers and './bin'.
    # Permit *only* this leading root marker; never internal '..' traversal.
    check(not name.startswith("/"),"absolute TAR member")
    raw=name.rstrip("/")
    if raw==".": return ()
    while raw.startswith("./"):
        raw=raw[2:]
    check(raw and all(c not in ("", ".", "..") for c in raw.split("/")),
          "traversal or non-normalized TAR member")
    return tuple(raw.split("/"))

def resolved_symlink_path(member_name, target):
    """Resolve link targets lexically; a path outside extraction root fails."""
    check(target and not target.startswith("/") and "\\" not in target,
          "absolute or Windows-style symlink target")
    pieces=list(PurePosixPath(member_name).parent.parts)
    for chunk in target.split("/"):
        if chunk in ("", "."): continue
        if chunk=="..":
            check(bool(pieces),"symlink target exits extraction root")
            pieces.pop()
        else: pieces.append(chunk)
    check(bool(pieces),"symlink target resolves outside or to root")
    return tuple(pieces)

def scan_tar(blob):
    checked=set()
    kinds={}
    hardlinks={}
    symlinks=set()
    resolved_links={}
    n=0;total=0;regular=0
    try:
        with tarfile.open(fileobj=io.BytesIO(blob),mode="r:gz") as t:
            for member in t:
                n+=1
                check(n<=MAX_MEMBERS,"too many TAR entries")
                parts=path_parts(member.name)
                if not parts and member.isdir():
                    # Harmless GNU TAR root marker; nothing to extract.
                    continue
                check(parts,"unnamed non-directory TAR member")
                check(parts not in checked,"duplicate TAR member path")
                checked.add(parts)
                check(member.isfile() or member.isdir() or member.issym() or member.islnk(),
                      "device, fifo or unsupported TAR entry")
                kinds[parts] = ("file" if member.isfile() else
                                "dir" if member.isdir() else
                                "sym" if member.issym() else "hard")
                if member.isfile():
                    regular+=1
                    check(0<=member.size<=MAX_MEMBER,"oversized file entry")
                    total+=member.size
                    check(total<=MAX_TOTAL,"excess uncompressed TAR size")
                if member.issym():
                    symlinks.add(parts)
                    resolved_links[parts]=resolved_symlink_path(member.name,member.linkname)
                if member.islnk():
                    # POSIX hard-link targets refer to archive-root names.
                    hardlinks[parts] = path_parts(member.linkname)
            check(n>0 and regular>0,"empty or file-free TAR")
    except (tarfile.TarError,EOFError,OSError,OverflowError) as exc:
        raise UnsafeTarError("unreadable TAR file") from exc
    # Post-scan checks matter: archive order can put child entries before
    # the symlink which would later become their parent.
    for parts in checked:
        check(not any(parts[:k] in symlinks for k in range(1,len(parts))),
              "archive contains an entry beneath a symbolic link")
        check(not any(parts[:k] in hardlinks for k in range(1,len(parts))),
              "archive contains an entry beneath a hard link")
    for _,target in resolved_links.items():
        check(not any(target[:i] in symlinks for i in range(1,len(target)+1)),
              "nested symbolic links are not allowed")
    for _,target in hardlinks.items():
        check(kinds.get(target)=="file", "hard link target must be an original regular file")
    return {"member_count":n,"regular_files":regular,
            "declared_uncompressed_bytes":total,"symbolic_links":len(symlinks)}

def audit(release_json,archive_bytes):
    try:
        doc=json.loads(release_json)
    except (UnicodeError,ValueError) as exc:
        raise UnsafeTarError("invalid GitHub release metadata") from exc
    check(type(doc) is dict and doc.get("tag_name")=="nightly" and
          type(doc.get("id")) is int and doc["id"]>0,
          "wrong release metadata")
    assets=doc.get("assets")
    check(type(assets) is list,"missing release assets")
    matches=[a for a in assets if type(a) is dict and a.get("name")==ASSET]
    check(len(matches)==1,"ambiguous exact Linux asset")
    asset=matches[0]
    check(asset.get("state")=="uploaded" and type(asset.get("id")) is int
          and asset["id"]>0 and type(asset.get("size")) is int and
          asset["size"]==len(archive_bytes),"wrong asset state, id or declared byte size")
    sha=hashlib.sha256(archive_bytes).hexdigest()
    advertised=asset.get("digest")
    if advertised is not None:
        check(type(advertised) is str and advertised=="sha256:"+sha,
              "actual archive SHA differs from GitHub release asset")
    members=scan_tar(archive_bytes)
    return {"schema":SCHEMA,"result":RESULT,
            "release_id":doc["id"],"release_asset_id":asset["id"],
            "asset_name":ASSET,"archive_bytes":len(archive_bytes),
            "archive_sha256":sha,"github_advertised_sha256_checked":advertised is not None,
            **members,"ready_for_controlled_extraction":True,
            "nightly_tag_mutable":True,"binary_authenticity_signed":False,
            "hardware_status":"HARDWARE NOT TESTED"}

def main(args=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release",required=True,type=Path)
    parser.add_argument("--archive",required=True,type=Path)
    parser.add_argument("--receipt",required=True,type=Path)
    argv=parser.parse_args(args)
    try:
        check(not argv.receipt.exists() and not argv.receipt.is_symlink(),
              "refuse to overwrite pre-extract receipt")
        report=audit(data_from_file(argv.release,2_000_000),
                     data_from_file(argv.archive,MAX_ARCHIVE))
        argv.receipt.parent.mkdir(parents=True,exist_ok=True)
        with argv.receipt.open("x",encoding="utf-8") as f:
            json.dump(report,f,indent=2,sort_keys=True);f.write("\n")
        print(json.dumps({k:report[k] for k in ("result","archive_sha256","member_count",
                                                "regular_files","symbolic_links")},sort_keys=True))
        return 0
    except (UnsafeTarError,OSError,ValueError,TypeError) as exc:
        # Only fixed audit errors include details; host OS exception messages
        # can contain absolute paths and are intentionally not exposed.
        reason=str(exc) if isinstance(exc, UnsafeTarError) else None
        print(json.dumps({"result":"STAGE385_PREEXTRACT_NOT_VERIFIED",
                          "error_kind":type(exc).__name__,
                          "validation_reason":reason,
                          "hardware_status":"HARDWARE NOT TESTED"}),file=sys.stderr)
        return 2
if __name__=="__main__": raise SystemExit(main())
