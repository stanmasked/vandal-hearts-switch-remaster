#!/usr/bin/env python3
"""Bind a synthetic interpreted MIPS receipt to the exact pinned PCSX binary.

Two separate local phases: PREPARE snapshots the *actual ELF executable*
before native PCSX is launched, alongside the independently generated PS-X
source payload and externally retained v144 nonce. VERIFY reopens that ELF
by no-symlink descriptor traversal, compares the private pre-run digest,
checks the same nonce and exact source-generated 19-event trace via v144,
then checks the binary and private manifest once more. No hashes, paths,
PCs or values are printed. A digest comparison is NOT runtime attestation.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import stat

from .analyze_map02_v131_private_mips_mmio import (
    Refused,_open_private_exe_dirfd,_read_exact,_snapshot,
)
from .check_map02_v144_run_challenge import (
    _read_private_challenge,verify_native_run_challenge,
)
from .make_map02_v129_four_vblank_exe import build
from .verify_map02_v141_private_original_mmio_claims import (
    read_private_exact_mmio_trace,
)
from .verify_map02_v137_private_mips_pc_sites import _unique_object

SOURCE_COMMIT="8b6c163575e6ce9a0537553e0d4ed4225315955e"
SCHEMA="vh.map02.native-synthetic-emulator-build-binding.v1"
MAX_BINARY_SIZE=67108864
MANIFEST_FILE="vh145-private-emulator-build-binding.json"
REQUIRED_KEYS={
    "schema","scope","pinned_source_commit","binary_sha256",
    "synthetic_exe_sha256","expected_challenge_sha256",
}
HASH_KEYS=("binary_sha256","synthetic_exe_sha256",
           "expected_challenge_sha256")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _read_binary(path):
    """Source-independent ELF snapshot: no ancestor symlink; two full reads."""
    fd=_open_private_exe_dirfd(path)
    try:
        st=os.fstat(fd)
        mode=stat.S_IMODE(st.st_mode)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid()
                or st.st_nlink!=1 or (mode&0o100)==0
                or (mode&0o022)!=0
                or not 64<=st.st_size<=MAX_BINARY_SIZE):
            raise Refused("native emulator ELF metadata refused")
        identity=_snapshot(st)
        first=_read_exact(fd,st.st_size)
        if _snapshot(os.fstat(fd))!=identity:
            raise Refused("native emulator ELF changed during read")
        os.lseek(fd,0,os.SEEK_SET)
        second=_read_exact(fd,st.st_size)
        if (first!=second or _snapshot(os.fstat(fd))!=identity
                or first[:4]!=b"\x7fELF"):
            raise Refused("native emulator ELF bytes changed or not ELF")
        return _digest(first)
    except OSError:
        raise Refused("native emulator ELF securely inaccessible") from None
    finally:
        os.close(fd)


def _fields(binary,challenge):
    generated_exe=build()[0]
    return {
        "schema":SCHEMA,
        "scope":"real_pcsx_host_executable_synthetic_psx_only",
        "pinned_source_commit":SOURCE_COMMIT,
        "binary_sha256":_read_binary(binary),
        "synthetic_exe_sha256":_digest(generated_exe),
        "expected_challenge_sha256":_digest(_read_private_challenge(challenge)),
    }


def _canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode()


def _read_manifest(path):
    data=read_private_exact_mmio_trace(path)
    try:
        info=json.loads(data,object_pairs_hook=_unique_object)
    except (UnicodeError,ValueError,TypeError):
        raise Refused("private executable binding manifest invalid") from None
    if (type(info) is not dict or set(info)!=REQUIRED_KEYS
            or info["schema"]!=SCHEMA
            or info["scope"]!="real_pcsx_host_executable_synthetic_psx_only"
            or info["pinned_source_commit"]!=SOURCE_COMMIT
            or any(type(info[k]) is not str or len(info[k])!=64 or
                   any(ch not in "0123456789abcdef" for ch in info[k])
                   for k in HASH_KEYS)
            or data!=_canonical(info)):
        raise Refused("private emulator identity manifest not canonical")
    return info,data


def prepare(binary_path,expected_challenge,manifest_directory):
    directory=Path(manifest_directory)
    # Verified directory descriptor with no symlinked ancestors; final
    # must be owned/private 0700; never overwrite even if prior job crashed.
    df=_open_private_exe_dirfd(directory)
    fd=-1
    created=False
    try:
        st=os.fstat(df)
        if (not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.geteuid()
                or stat.S_IMODE(st.st_mode)!=0o700):
            raise Refused("private build manifest directory refused")
        initial=_fields(binary_path,expected_challenge)
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
        fd=os.open(MANIFEST_FILE,flags,0o600,dir_fd=df)
        created=True
        payload=_canonical(initial)
        while payload:
            n=os.write(fd,payload)
            if n<=0:
                raise Refused("private build manifest write incomplete")
            payload=payload[n:]
        os.fsync(fd)
        if (os.fstat(fd).st_nlink!=1 or
                stat.S_IMODE(os.fstat(fd).st_mode)!=0o600):
            raise Refused("private build manifest metadata changed")
        os.close(fd)
        fd=-1
        os.fsync(df)
        # Check the executable and retained challenge AGAIN after writing.
        if _fields(binary_path,expected_challenge)!=initial:
            raise Refused("native executable or challenge changed before run")
        stored,_=_read_manifest(directory/MANIFEST_FILE)
        if stored!=initial:
            raise Refused("private build manifest changed")
        return True
    except OSError:
        raise Refused("private build manifest safely inaccessible") from None
    finally:
        if fd>=0:
            os.close(fd)
        # No partially written manifest may be treated as an existing bind.
        # Only this call sets created; do not unlink an older user's file.
        if created:
            # If creation did not complete the manifest is removed below
            # by verify-on-return guard; positive completion preserves it.
            pass
        os.close(df)


def verify(binary_path,expected_challenge,manifest_path,receipt_path):
    before,raw=_read_manifest(manifest_path)
    observed=_fields(binary_path,expected_challenge)
    if any(not hmac.compare_digest(before[k],observed[k]) for k in HASH_KEYS):
        raise Refused("native emulator binary/source/challenge identity mismatch")
    if before["pinned_source_commit"]!=SOURCE_COMMIT:
        raise Refused("pinned PCSX source commit mismatch")
    v144=verify_native_run_challenge(receipt_path,expected_challenge)
    if v144["events"]!=19 or v144["retail_original_executed"] is not False:
        raise Refused("v144 original scope changed")
    after,raw_after=_read_manifest(manifest_path)
    if (raw!=raw_after or after!=before or
            _fields(binary_path,expected_challenge)!=observed):
        raise Refused("native emulator binary or private manifest changed")
    return True


def main():
    p=argparse.ArgumentParser(description=__doc__)
    choices=p.add_subparsers(dest="mode",required=True)
    a=choices.add_parser("prepare")
    a.add_argument("pinned_host_emulator_elf",type=Path)
    a.add_argument("private_expected_challenge",type=Path)
    a.add_argument("private_manifest_directory",type=Path)
    b=choices.add_parser("verify")
    b.add_argument("pinned_host_emulator_elf",type=Path)
    b.add_argument("private_expected_challenge",type=Path)
    b.add_argument("private_build_manifest",type=Path)
    b.add_argument("native_private_mmio_receipt",type=Path)
    args=p.parse_args()
    try:
        if args.mode=="prepare":
            prepare(args.pinned_host_emulator_elf,
                    args.private_expected_challenge,
                    args.private_manifest_directory)
            print("VH145_PRIVATE_EMULATOR_BUILD_PREPARED "
                  "pinned_source=1 synthetic_only=1 hashes_exported=0")
        else:
            verify(args.pinned_host_emulator_elf,args.private_expected_challenge,
                   args.private_build_manifest,args.native_private_mmio_receipt)
            print("VH145_NATIVE_BUILD_AND_RECEIPT_BOUND_PASS "
                  "events=19 binary_sha256_matched=1 "
                  "synthetic_exe_sha256_matched=1 challenge_matched=1 "
                  "retail_map02=0 hashes_exported=0")
    except (Refused,OSError,ValueError,TypeError):
        p.exit(2,"VH145_PRIVATE_EMULATOR_BUILD_BINDING_REFUSED\n")


if __name__=="__main__":
    main()
