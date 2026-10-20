#!/usr/bin/env python3
"""Prepare a non-invasive, offline-verifiable physical Switch test kit.

Produces only public homebrew NRO, SHA-256 manifest and operator checklist.
Does not read personal keys or console identifiers, write to SD or claim boot.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

NAME = "vandal-hearts-prototype.nro"
EXPECTED = "564c29e4c6c47eaf80e356733b8bdb8e298f1e0c938575b20be0ae9d48680539"
CHECKS = ("nro_launch", "minus_legacy", "zr_optional", "l_arenas",
          "r_rosters", "bow_invalid", "bow_valid", "guard",
          "medic", "victory", "defeat", "y_reset", "return_legacy",
          "plus_exit", "suspend_resume", "handheld_display", "docked_display")


class KitError(ValueError):
    pass


def digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise KitError("NRO must be a regular file, not a symlink")
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def prepare(nro: Path, output: Path) -> dict:
    if nro.name != NAME:
        raise KitError("unexpected NRO filename")
    actual = digest(nro)
    if actual != EXPECTED:
        raise KitError(f"unverified NRO digest: {actual}")
    if output.is_symlink():
        raise KitError("test-kit destination is a symlink")
    output.mkdir(parents=True, exist_ok=True)
    if (output / NAME).is_symlink():
        raise KitError("existing NRO destination is a symlink")
    if output.resolve() == nro.parent.resolve():
        raise KitError("source and destination directories must differ")
    shutil.copyfile(nro, output / NAME)
    if digest(output / NAME) != EXPECTED:
        raise KitError("copied NRO digest changed")
    manifest = {
        "schema_version": 1,
        "artifact": NAME,
        "sha256": EXPECTED,
        "size_bytes": (output / NAME).stat().st_size,
        "source": "original-asset-free MAP02 Nintendo Switch prototype",
        "emulator_validated": True,
        "physical_switch_validated": False,
        "test_results": {step: "not_tested" for step in CHECKS},
    }
    target = output / "physical_test_manifest.json"
    if target.is_symlink():
        raise KitError("manifest destination is a symlink")
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    (output / "SHA256SUMS").write_text(f"{EXPECTED}  {NAME}\n", encoding="ascii")
    return manifest


def verify(output: Path) -> dict:
    manifest_file = output / "physical_test_manifest.json"
    if manifest_file.is_symlink():
        raise KitError("manifest is a symlink")
    m = json.loads(manifest_file.read_text(encoding="utf-8"))
    if (m.get("schema_version") != 1 or m.get("artifact") != NAME or
        m.get("sha256") != EXPECTED or m.get("physical_switch_validated") is not False or
        list(m.get("test_results", {})) != list(CHECKS) or
        any(v != "not_tested" for v in m["test_results"].values())):
        raise KitError("test kit manifest has been modified or falsely claims hardware tests")
    if digest(output / NAME) != EXPECTED:
        raise KitError("test kit NRO mismatch")
    if m.get("size_bytes") != (output / NAME).stat().st_size:
        raise KitError("test kit byte count mismatch")
    if (output / "SHA256SUMS").read_text(encoding="ascii") != f"{EXPECTED}  {NAME}\n":
        raise KitError("SHA256SUMS mismatch")
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["prepare", "verify"])
    ap.add_argument("--nro", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    try:
        if args.action == "prepare":
            if args.nro is None:
                raise KitError("--nro required")
            prepare(args.nro, args.output)
        else:
            verify(args.output)
        print("VH_MAP02_HARDWARE_KIT_PASS sha256_verified=1 "
              "physical_switch_validated=0 retail=0", flush=True)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("VH_MAP02_HARDWARE_KIT_FAIL: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
