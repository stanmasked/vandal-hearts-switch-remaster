#!/usr/bin/env python3
"""Stage 233: safe host capture of numbered audio CSV from an operator's SD root.

Reads an explicitly selected, ordered list of source CSV files on an operator
mounted SD path; validates the source NRO against an already pinned SD transfer
plan; copies exact raw bytes into a new evidence bundle. All originals are
read-only. The export is first prepared in a private temporary sibling tree,
all hashes and CSV formats are independently rechecked, and the new directory
is published only if it does not already exist.

A second 'verify' mode compares the captured bundle to *fresh reads* of the
original selected SD files. Host paths, hashes and declared CI links do not
authenticate physical SD, sessions, audible sound or power-loss durability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

import analyze_switch_audio_log as audio
import verify_switch_audio_bundle as bundle
import verify_switch_audio_sd_transfer as transfer

SCHEMA = "vh-switch-audio-sd-csv-capture/v1"
AUDIO_DIR = "switch/vandal-hearts-remake"
NRO_PATH = "nro/vandal-hearts-prototype.nro"
CSV_NAME = re.compile(r"audio-diagnostics-[0-9]{4,6}\.csv\Z")
MAX_SESSIONS = 64
MAX_CSV_BYTES = 4 * 1024 * 1024
MAX_NRO_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 192 * 1024 * 1024


class CaptureError(ValueError):
    """Unsafe source path, incomplete copy, changing SD bytes or output collision."""


def require(condition: bool, error: str) -> None:
    if not condition:
        raise CaptureError(error)


def safe_source(root: Path, name: str) -> Path:
    require(isinstance(name, str) and CSV_NAME.fullmatch(name) is not None,
            "CSV name must be an original numbered audio-diagnostics-XXXX.csv")
    current = root
    for bit in (*AUDIO_DIR.split("/"), name):
        current = current / bit
        require(not current.is_symlink(), "SD CSV path contains symbolic link")
    require(current.is_file() and
            current.resolve().is_relative_to(root.resolve()),
            "original SD CSV is missing or outside requested SD root")
    require(stat.S_ISREG(current.stat().st_mode), "SD CSV is not a regular file")
    require(0 < current.stat().st_size <= MAX_CSV_BYTES,
            "original SD CSV is empty or exceeds the 4 MiB size cap")
    return current


def csv_selection(names: list[str]) -> list[str]:
    require(isinstance(names, list) and 1 <= len(names) <= MAX_SESSIONS,
            "select between 1 and 64 original SD CSV names")
    require(all(isinstance(s, str) and
                CSV_NAME.fullmatch(s) is not None for s in names),
            "only numbered audio-diagnostics CSV filenames are accepted")
    require(len(set(names)) == len(names), "duplicate CSV session was selected")
    return names


def check_incomplete_exports(root: Path) -> None:
    directory = root / AUDIO_DIR
    require(directory.is_dir() and not directory.is_symlink(),
            "Switch audio SD directory is missing or symbolic link")
    require(not any(p.name.startswith("audio-diagnostics-") and
                    p.name.endswith((".tmp", ".partial")) for p in directory.iterdir()),
            "INCOMPLETE_SD_EXPORT: temporary/partial audio CSV exists on SD")


def fingerprint(path: Path) -> dict:
    size, sha = bundle.digest_file(path)
    return {"size": size, "sha256": sha}


def copy_strict(source: Path, destination: Path, cap: int, expected: dict) -> None:
    require(not destination.exists() and not destination.is_symlink(),
            "copy target exists; never replace evidence")
    before = fingerprint(source)
    require(before == expected and 0 < before["size"] <= cap,
            "SOURCE_CHANGED_BEFORE_COPY")
    size = 0
    digest = hashlib.sha256()
    with source.open("rb") as input_file, destination.open("xb") as output_file:
        while block := input_file.read(1024 * 1024):
            size += len(block)
            require(size <= cap, "source grew beyond bounded copy limit")
            output_file.write(block)
            digest.update(block)
        output_file.flush()
        os.fsync(output_file.fileno())
    require(size == before["size"] and digest.hexdigest() == before["sha256"],
            "SOURCE_CHANGED_DURING_COPY")
    require(fingerprint(destination) == before,
            "DESTINATION_COPY_INTEGRITY_MISMATCH")
    require(fingerprint(source) == before,
            "SOURCE_CHANGED_AFTER_COPY")


def source_records(source_bundle: Path, sd_root: Path, plan: Path,
                   filenames: list[str]) -> tuple[dict, dict, list[tuple[str, Path, dict]]]:
    names = csv_selection(filenames)
    src_root, mounted = transfer.roots(source_bundle, sd_root)
    require(not plan.is_symlink() and plan.is_file(), "missing source SD transfer plan")
    # This step validates the *installed* NRO against the original plan,
    # not merely the unsigned source Git SHA string.
    copied_nro = transfer.verify(src_root, mounted, plan)
    manifest = bundle.read_manifest(src_root)
    require(manifest["ci_run_url"].startswith(
                "https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/"),
            "source bundle must include an actual project GitHub run URL")
    require(copied_nro["source_git_sha_self_reported"] == manifest["git_sha"],
            "NRO plan and source manifest disagree on Git commit")
    check_incomplete_exports(mounted)
    sd_dir = mounted / AUDIO_DIR
    listed = sorted(p.name for p in sd_dir.iterdir()
                    if CSV_NAME.fullmatch(p.name) is not None)
    # Unselected numbered CSV files may be from other sessions/builds. They
    # remain on SD and are NEVER auto-included as hardware evidence.
    observed = []
    total = copied_nro["nro_size"]
    for name in names:
        source = safe_source(mounted, name)
        audio.load_csv(source)
        item = fingerprint(source)
        total += item["size"]
        require(total <= MAX_TOTAL_BYTES, "selected evidence exceeds 192 MiB")
        observed.append((name, source, item))
    require(copied_nro["nro_size"] <= MAX_NRO_BYTES,
            "SD NRO exceeds 128 MiB")
    return manifest, copied_nro, observed


def layout(index: int, filename: str) -> str:
    return f"session-{index:02d}/{filename}"


def validate_export(captured: Path, manifest: dict,
                    installed: dict, originals: list[tuple[str, Path, dict]]) -> dict:
    report = bundle.inspect(captured)
    inventory = bundle.read_manifest(captured)
    require(report["hardware_status"] == bundle.HARDWARE_STATUS and
            inventory["git_sha"] == manifest["git_sha"] and
            inventory["ci_run_url"] == manifest["ci_run_url"],
            "CAPTURED_BUILD_IDENTITY_MISMATCH")
    require(inventory["nro"]["path"] == NRO_PATH and
            inventory["nro"]["size"] == installed["nro_size"] and
            inventory["nro"]["sha256"] == installed["nro_sha256"],
            "CAPTURED_NRO_IDENTITY_MISMATCH")
    require(len(inventory["sessions"]) == len(originals),
            "CAPTURED_SESSION_COUNT_MISMATCH")
    for n, ((name, source, initial), entry) in enumerate(
            zip(originals, inventory["sessions"]), 1):
        require(entry["path"] == layout(n, name) and
                entry["size"] == initial["size"] and
                entry["sha256"] == initial["sha256"],
                "CAPTURED_CSV_IDENTITY_MISMATCH")
        require(fingerprint(source) == initial,
                "SD_CSV_CHANGED_SINCE_INITIAL_SCAN")
        target = bundle.safe_member(captured, entry["path"], ".csv")
        require(fingerprint(target) == initial,
                "CAPTURED_CSV_BYTES_CHANGED")
    return report


def capture(source_bundle: Path, sd_root: Path, plan: Path,
            filenames: list[str], output: Path) -> dict:
    manifest, installed, originals = source_records(
        source_bundle, sd_root, plan, filenames)
    output = output.absolute()
    source = source_bundle.resolve()
    sd = sd_root.resolve()
    require(output.parent.is_dir() and not output.parent.is_symlink(),
            "capture destination parent is missing or symbolic link")
    require(not output.exists() and not output.is_symlink(),
            "destination evidence bundle already exists; refusing overwrite")
    require(not output.parent.resolve().is_relative_to(source) and
            not output.parent.resolve().is_relative_to(sd) and
            not source.is_relative_to(output) and not sd.is_relative_to(output),
            "capture must be outside source evidence and mounted SD")
    temp = Path(tempfile.mkdtemp(prefix=".vh-audio-capture-",
                                 dir=output.parent))
    try:
        (temp / "nro").mkdir()
        nro = transfer.destination(sd, transfer.read_plan(plan)["sd_destination"],
                                   must_exist=True)
        installed_fp = {"size": installed["nro_size"],
                        "sha256": installed["nro_sha256"]}
        copy_strict(nro, temp / NRO_PATH, MAX_NRO_BYTES, installed_fp)
        for index, (name, path, item) in enumerate(originals, 1):
            relative = layout(index, name)
            (temp / f"session-{index:02d}").mkdir()
            copy_strict(path, temp / relative, MAX_CSV_BYTES, item)
        bundle.create(temp, NRO_PATH,
                      [layout(i, item[0]) for i, item in enumerate(originals, 1)],
                      manifest["git_sha"], manifest["ci_run_url"])
        validate_export(temp, manifest, installed, originals)
        require(not output.exists() and not output.is_symlink(),
                "destination appeared during capture; refusing overwrite")
        os.rename(temp, output)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return {
        "schema": SCHEMA,
        "result": "RAW_SD_CSV_COPIES_CAPTURED_AND_RECHECKED",
        "hardware_status": bundle.HARDWARE_STATUS,
        "destination": str(output),
        "git_sha_self_reported": manifest["git_sha"],
        "nro_sha256": installed["nro_sha256"],
        "session_count": len(originals),
        "source_csv": [
            {"source_sd_relative": AUDIO_DIR + "/" + name,
             "captured_relative": layout(i, name), **item}
            for i, (name, _, item) in enumerate(originals, 1)
        ],
        "source_sd_medium": "NOT_ATTESTED",
        "physical_session_independence": "NOT_ATTESTED",
        "hardware_execution": "HARDWARE NOT TESTED",
        "limitations": (
            "The operator selected which numbered CSV files to copy. Other CSVs "
            "on SD may belong to other sessions/builds; all selected originals "
            "remain untouched. Distinct files are not proof of independent "
            "Switch launches or audible music. This is only a file copy check."
        ),
    }


def verify(source_bundle: Path, sd_root: Path, plan: Path,
           captured: Path) -> dict:
    require(captured.is_dir() and not captured.is_symlink(),
            "captured bundle missing or symbolic link")
    inventory = bundle.read_manifest(captured)
    names = []
    for index, item in enumerate(inventory["sessions"], 1):
        relative = item["path"]
        require(isinstance(relative, str) and
                relative.startswith(f"session-{index:02d}/"),
                "captured CSV path sequence was changed")
        name = relative.split("/")[-1]
        require(relative == layout(index, name),
                "captured CSV is outside the expected session layout")
        names.append(name)
    manifest, installed, originals = source_records(
        source_bundle, sd_root, plan, names)
    require(not captured.resolve().is_relative_to(sd_root.resolve()) and
            not captured.resolve().is_relative_to(source_bundle.resolve()),
            "captured bundle must be outside source and SD")
    validate_export(captured, manifest, installed, originals)
    source_nro = transfer.destination(
        sd_root.resolve(), transfer.read_plan(plan)["sd_destination"],
        must_exist=True)
    require(fingerprint(source_nro) == fingerprint(captured / NRO_PATH),
            "CAPTURED_NRO_DOES_NOT_MATCH_CURRENT_SD")
    return {
        "schema": SCHEMA,
        "result": "CAPTURED_RAW_BYTES_MATCH_FRESH_SD_READBACK",
        "hardware_status": bundle.HARDWARE_STATUS,
        "captured_manifest_sha256": bundle.digest_file(
            captured / bundle.MANIFEST_NAME)[1],
        "session_count": len(originals),
        "raw_csv_sha256": [item["sha256"] for _, _, item in originals],
        "source_sd_medium": "NOT_ATTESTED",
        "hardware_execution": "HARDWARE NOT TESTED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("capture", "verify"):
        cmd = sub.add_parser(mode)
        cmd.add_argument("--source-bundle", required=True, type=Path)
        cmd.add_argument("--sd-root", required=True, type=Path)
        cmd.add_argument("--transfer-plan", required=True, type=Path)
        if mode == "capture":
            cmd.add_argument("--csv", required=True, action="append",
                             help="selected numbered SD CSV file basename")
            cmd.add_argument("--output", required=True, type=Path)
        else:
            cmd.add_argument("--captured", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.mode == "capture":
            result = capture(args.source_bundle, args.sd_root,
                             args.transfer_plan, args.csv, args.output)
        else:
            result = verify(args.source_bundle, args.sd_root,
                            args.transfer_plan, args.captured)
    except (CaptureError, transfer.TransferError,
            bundle.BundleError, audio.LogFormatError,
            OSError, TypeError, KeyError, ValueError) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE",
                          "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
