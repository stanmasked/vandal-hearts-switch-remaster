#!/usr/bin/env python3
"""Compare independently captured NeXium audout CI artifacts of identical NRO bytes.

A cross-run *software diagnostic* only. Passing does not show real DAC
behavior, physical Switch playback or absence of audible underruns.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

from audit_nexium_audout_queue import parse_telemetry, HEADER

PREFIX = "runtime-evidence/scene-soak/"
MEMBERS = {
    "build": "integrated-nro-preflight.json",
    "scene": PREFIX + "soak-verification.json",
    "queue": PREFIX + "soak-audout-verification.json",
    "csv": PREFIX + "soak-audout-sd-unverified.csv",
    "receipt": PREFIX + "soak-audout-export-result.txt",
}
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RepeatabilityError(ValueError):
    pass


def unique_json(data: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RepeatabilityError("duplicate JSON property: " + key)
            result[key] = value
        return result
    try:
        out = json.loads(data.decode("ascii"), object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RepeatabilityError("invalid JSON") from exc
    if not isinstance(out, dict):
        raise RepeatabilityError("JSON root must be an object")
    return out


def read_run(archive: Path) -> dict:
    if archive.is_symlink() or not archive.is_file():
        raise RepeatabilityError("run artifact is missing or symlinked")
    with zipfile.ZipFile(archive) as zipped:
        observed = {}
        for member in zipped.infolist():
            name = member.filename
            safe = PurePosixPath(name)
            if (not name or safe.is_absolute() or ".." in safe.parts
                    or "\\" in name):
                raise RepeatabilityError("unsafe artifact ZIP member")
            if name in observed:
                raise RepeatabilityError("duplicate artifact member")
            observed[name] = member
        for name in MEMBERS.values():
            if name not in observed:
                raise RepeatabilityError("missing evidence member: " + name)
        raw = {}
        for key, name in MEMBERS.items():
            member = observed[name]
            mode = member.external_attr >> 16
            if member.is_dir() or stat.S_IFMT(mode) == stat.S_IFLNK:
                raise RepeatabilityError("nonregular evidence member")
            cap = 1024 * 1024 if key == "csv" else 32 * 1024
            if member.file_size <= 0 or member.file_size > cap:
                raise RepeatabilityError("invalid evidence member size")
            raw[key] = zipped.read(member)
    build, scene, queue = (unique_json(raw[x]) for x in ("build", "scene", "queue"))
    if (build.get("result") != "SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED"
            or not isinstance(build.get("nro_sha256"), str)
            or not SHA256.fullmatch(build["nro_sha256"])
            or not isinstance(build.get("git_sha"), str)
            or not FULL_SHA.fullmatch(build["git_sha"])
            or type(build.get("run_id")) is not int or build["run_id"] <= 0
            or type(build.get("run_attempt")) is not int
            or build["run_attempt"] <= 0):
        raise RepeatabilityError("untrusted same-run NRO preflight")
    if (scene.get("result") != "TEN_GUEST_SCENE_TRANSITIONS_DUAL_TRANSPORT_VERIFIED"
            or scene.get("guest_nro_sha256") != build["nro_sha256"]
            or scene.get("guest_event_rows") != 53
            or scene.get("hardware_status") != "HARDWARE NOT TESTED"):
        raise RepeatabilityError("scene evidence not bound to NRO and 53 events")
    if (queue.get("result") != "GUEST_SD_AUDOUT_TELEMETRY_CONSISTENT"
            or queue.get("sd_binding") != "GUEST_ORIGINAL_AND_COPY_BYTE_IDENTICAL"
            or queue.get("guest_export_receipt") != "GUEST_WRITER_SUCCEEDED_AND_STAT_VISIBLE"
            or queue.get("hardware_tested") is not False
            or queue.get("underruns_measured") is not False):
        raise RepeatabilityError("audout guest SD gate missing or misclassified")
    receipt = (f"export_status=0\npath_present=1\n"
               f"file_size={len(raw['csv'])}\n").encode("ascii")
    if raw["receipt"] != receipt:
        raise RepeatabilityError("guest export receipt mismatch")
    try:
        recomputed = parse_telemetry(raw["csv"])
    except (ValueError, UnicodeError, csv.Error) as exc:
        raise RepeatabilityError("invalid original-copy telemetry CSV") from exc
    digest = hashlib.sha256(raw["csv"]).hexdigest()
    match = (
        "attempts", "releases", "failed_attempts", "max_call_us",
        "windows", "queue_probes_ok", "queue_probes_failed",
        "overwritten_windows", "clock_errors",
        "queue_min_pre_submit", "queue_max_pre_submit",
    )
    if (any(queue.get(k) != recomputed[k] for k in match)
            or queue.get("sd_copy_sha256") != digest
            or queue.get("sd_original_sha256") != digest
            or queue.get("sd_copy_bytes") != len(raw["csv"])
            or queue.get("guest_export_receipt_sha256") !=
            hashlib.sha256(raw["receipt"]).hexdigest()):
        raise RepeatabilityError("telemetry CSV, SD verdict or receipt hash differs")
    if (recomputed["failed_attempts"] != 0
            or recomputed["clock_errors"] != 0
            or recomputed["overwritten_windows"] != 0
            or recomputed["queue_probes_failed"] != 0):
        raise RepeatabilityError("audout baseline had failed calls or incomplete buckets")
    return {
        "run_id": build["run_id"],
        "run_attempt": build["run_attempt"],
        "git_sha": build["git_sha"],
        "nro_sha256": build["nro_sha256"],
        "pcm_duration_seconds": scene.get("pcm_duration_seconds"),
        "audout_attempts": recomputed["attempts"],
        "audout_releases": recomputed["releases"],
        "audout_max_call_us": recomputed["max_call_us"],
        "audout_window_count": recomputed["windows"],
        "pre_submit_probes": recomputed["queue_probes_ok"],
        "queue_csv_sha256": digest,
        "note": "pre-submit queue values do not measure audible underruns",
    }


def compare(archives: list[Path]) -> dict:
    if len(archives) < 2:
        raise RepeatabilityError("at least two independent runs required")
    runs = [read_run(path) for path in archives]
    identities = [(r["run_id"], r["run_attempt"]) for r in runs]
    if len(set(identities)) != len(identities):
        raise RepeatabilityError("duplicate workflow run and attempt")
    hashes = {r["nro_sha256"] for r in runs}
    if len(hashes) != 1:
        raise RepeatabilityError("NRO binary hashes differ: cannot compare one build")
    attempts = [r["audout_attempts"] for r in runs]
    # This is a descriptive software-baseline gate, not a real-time SLA.
    if min(attempts) < 1000 or max(attempts) > min(attempts) * 1.10:
        raise RepeatabilityError("audout attempt counts not comparable")
    return {
        "schema": "vh-nexium-audout-cross-run/v1",
        "result": "SAME_NRO_GUEST_AUDOUT_REPEATABILITY_VERIFIED",
        "run_count": len(runs),
        "nro_sha256": runs[0]["nro_sha256"],
        "attempts_min": min(attempts),
        "attempts_max": max(attempts),
        "call_max_us_min": min(r["audout_max_call_us"] for r in runs),
        "call_max_us_max": max(r["audout_max_call_us"] for r in runs),
        "runs": sorted(runs, key=lambda x: (x["run_id"], x["run_attempt"])),
        "source": "previously verified CI guest SD copies, per-run reports and same-run NRO manifests",
        "independent_original_sd_reopened": False,
        "audible_underruns_measured": False,
        "physical_switch_tested": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifact", type=Path, required=True, action="append")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        result = compare(args.artifact)
        if args.output.exists() or args.output.is_symlink():
            raise RepeatabilityError("refuse to overwrite prior repeatability report")
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                               encoding="utf-8")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (RepeatabilityError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"result": "AUDOUT_REPEATABILITY_NOT_VERIFIED",
                          "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
