#!/usr/bin/env python3
"""Run MAP02 compile, sealed link and ELF inspection in one receipt session.

Immutable memfds bind each intermediate canonical JSON receipt in this
process. Final SHA-256 values are correlators, not external signatures.
"""
import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
from tools import build_map02_private_gpu_make_overlay as primary_builder
from tools import consume_map02_sealed_gpu_objects as linker
from tools import verify_map02_linked_gpu_object as inspector

SCHEMA = "vh.map02.sealed-gpu-receipt-chain.v1"
LIMIT = 1024 * 1024


def _canonical(obj):
    try:
        raw = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                         allow_nan=False, ensure_ascii=True).encode("ascii")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError("MAP02 receipt cannot be serialized canonically") from exc
    if not 0 < len(raw) <= LIMIT:
        raise ValueError("MAP02 receipt size invalid")
    return raw


def _pin(obj, stack, label):
    raw = _canonical(obj)
    fd = primary_builder._sealed_fd(raw, "vh-map02-" + label + "-receipt")
    stack.callback(os.close, fd)
    return fd, len(raw), hashlib.sha256(raw).hexdigest()


def _read_pin(pin):
    fd, length, expected = pin
    if fcntl.fcntl(fd, fcntl.F_GET_SEALS) & primary_builder.SEALS != primary_builder.SEALS:
        raise ValueError("MAP02 receipt memfd not sealed")
    raw = os.pread(fd, length + 1, 0)
    if len(raw) != length or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("MAP02 sealed receipt bytes changed")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("MAP02 duplicate JSON receipt keys")
            result[key] = value
        return result

    obj = json.loads(raw.decode("ascii"), object_pairs_hook=unique)
    if _canonical(obj) != raw:
        raise ValueError("MAP02 receipt canonical encoding changed")
    return obj


def _verify_chain(primary, linked, inspection):
    if (primary.get("schema") != "vh.map02.sealed-gpu-make-objects.v1" or
            linked.get("schema") != "vh.map02.sealed-linked-gpu-object.v1" or
            inspection.get("schema") != "vh.map02.sealed-linked-gpu-consumption.v1"):
        raise ValueError("MAP02 chain schema inconsistent")
    original = primary.get("objects_sha256")
    if (not isinstance(original, dict) or
            set(original) != set(linker.OBJECT_NAMES) or
            linked.get("source_objects_sha256") != original or
            inspection.get("source_objects_sha256") != original or
            linked.get("linked_object_sha256") != inspection.get("linked_object_sha256")):
        raise ValueError("MAP02 chain receipt hashes inconsistent")
    if (primary.get("actual_make_children_kernel_attested") is not True or
            linked.get("binutils_consumed_sealed_objects") is not True or
            inspection.get("linked_hash_verified_against_receipt") is not True or
            inspection.get("linked_bytes_sealed_before_binutils") is not True):
        raise ValueError("MAP02 chain receipt provenance incomplete")
    if any(x.get("hd_replacement_authorized") is not False for x in
           (primary, linked, inspection)):
        raise ValueError("MAP02 receipt chain HD gate invalid")


def run_chain(upstream, output, manifest, *, build_dir):
    if sys.platform != "linux" or not hasattr(os, "memfd_create"):
        raise ValueError("MAP02 receipt chain requires Linux memfd")
    pc = Path(upstream) / "platform" / "pc"
    with ExitStack() as stack:
        primary = primary_builder.compile_overlay(
            upstream, output, manifest, build_dir=build_dir)
        first = _pin(primary, stack, "primary")
        primary_copy = _read_pin(first)
        linked = linker.verify_and_link(pc, build_dir, primary_copy)
        if _canonical(primary_copy) != _canonical(_read_pin(first)):
            raise ValueError("MAP02 primary receipt modified by link stage")
        second = _pin(linked, stack, "linked")
        primary_copy, linked_copy = _read_pin(first), _read_pin(second)
        inspected = inspector.verify_and_inspect(
            pc, build_dir, primary_copy, linked_copy)
        if (_canonical(primary_copy) != _canonical(_read_pin(first)) or
                _canonical(linked_copy) != _canonical(_read_pin(second))):
            raise ValueError("MAP02 receipt modified by inspection stage")
        third = _pin(inspected, stack, "inspection")
        a, b, c = _read_pin(first), _read_pin(second), _read_pin(third)
        _verify_chain(a, b, c)
        return {
            "schema": SCHEMA,
            "primary": a, "linked": b, "inspection": c,
            "receipt_sha256": {"primary": first[2], "linked": second[2],
                               "inspection": third[2]},
            "sealed_receipt_snapshots": 3,
            "receipt_chain_consistent": True,
            "intermediate_receipt_files_written": False,
            "externally_authenticated": False,
            "hd_replacement_authorized": False,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_public_pc_checkout")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--build-dir", required=True)
    args = parser.parse_args()
    try:
        result = run_chain(args.pinned_public_pc_checkout, args.output_dir,
                           args.manifest, build_dir=args.build_dir)
    except (OSError, ValueError, UnicodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
