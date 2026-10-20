#!/usr/bin/env python3
"""Stage372: independently reparse *archived* Stage371 pair and GitHub source identity.

Runs on original bytes downloaded from the finished GitHub Actions run. The
synthetic unit tests are not independent live guest captures or console audio.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

REPO = "stanmasked/vandal-hearts-switch-remaster"
RUN_ID = 39396243731
ARTIFACT_ID = 12255245917
ARTIFACT_NAME = "stage371-two-guest-exit-original-observations"
HEAD_SHA = "8ccf7b4c354e6a78277a0ffe453e714d8a1a5519"
MERGE_SHA = "7322cd893638bdcbda168242093c7d20a20d5c85"
NRO_SHA = "cfc49a8ac8dcfe4704e697c1bea8fc750ea32d498c2942176c2ca9b9cbcae71b"
ARCHIVE_DIGEST = "sha256:a8382e51c326e64e09f9ae7dedd238d5494b7c95bdb328fab534b2ed0d0e5f3c"
VERDICT = "STAGE372_INDEPENDENTLY_REPARSED_TWO_ORIGINAL_STAGE371_GUEST_WAITS"
SOURCE_FILES = {
    "reason": "audio-exit-tail-reason-000.csv",
    "result": "audio-exit-tail-wait-result-000.csv",
    "descriptor": "audio-exit-wait-descriptor-000.csv",
}
LABELS = {
    "reason": ("software_exit_tail_reason_only", "tail_reason_code", "tail_attempted",
               "tail_descriptor_return_confirmed", "tail_lease_acquired", "lease_pages_acquired",
               "lease_pages_released", "abandoned_sessions"),
    "result": ("software_wait_result_only", "wait_result_observed",
               "audout_wait_result_raw", "stage351_tail_reason_code"),
    "descriptor": ("software_wait_descriptor_only", "wait_observed", "audout_wait_result_raw",
                   "released_count_reported", "returned_pointer_present",
                   "returned_pointer_matches_submitted", "stage351_tail_reason_code",
                   "stage357_raw_result_crosschecked"),
}
SOURCE_SHA = {
    "a": {
        "reason": "463f7abf23c6841b812d07b1fb13e3c428915dc5b649c334b4177afc4eda541b",
        "result": "298997cc46abb7377d106397651b4ed01cd6304690fa6b45b8900231c350d6e0",
        "descriptor": "b1634d381745ccdfa4886d4f58f594cb87a7fd9d0c7f55bc8d357ff67d814009",
    },
    "b": {
        "reason": "f7a8d188828edff8456aa7da0da5787a5e5d73c8809c6b5d6f3c240671494cff",
        "result": "298997cc46abb7377d106397651b4ed01cd6304690fa6b45b8900231c350d6e0",
        "descriptor": "b1634d381745ccdfa4886d4f58f594cb87a7fd9d0c7f55bc8d357ff67d814009",
    },
}
OPTICAL_SHA = {
    "a": "ec9720188debd29be6305848c5302aab3402eb8ef7140586f499d53aa8243f00",
    "b": "2daffa349ab54ce22d53874d80a39f6e49ee1dd22159039707687bac5de9bfea",
}
REQUIRED_STEPS = (
    "Verify same-run source NRO",
    "Run host-only Stage371 anti-fabrication tests",
    "First isolated original guest exit with baseline dwell",
    "Second isolated original guest exit with longer dwell",
    "Reopen BOTH original guest SD source families and bind to same NRO",
    "Upload original source receipts without raw sound assets",
)
OPTIONAL = ("audio-exit-probe-context-000.csv", "audio-lease-reconciliation-000.csv")


def ensure(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def file_bytes(path: Path, maximum: int) -> bytes:
    ensure(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
           "missing/linked original source: " + path.name)
    stat = path.stat()
    ensure(stat.st_nlink == 1 and 0 < stat.st_size <= maximum,
           "linked/oversized original source: " + path.name)
    return path.read_bytes()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_meta(path: Path) -> dict:
    item = json.loads(file_bytes(path, 250000).decode("utf-8"))
    ensure(type(item) is dict, "GitHub metadata not an object")
    return item


def parse_csv(raw: bytes, kind: str) -> dict:
    ensure(len(raw) <= 1024 and raw.startswith(b"scope,value\n") and raw.endswith(b"\n")
           and b"\r" not in raw and b"\x00" not in raw, "noncanonical original CSV")
    lines = raw.decode("ascii").splitlines()
    ensure(len(lines) == len(LABELS[kind]) + 1, "original CSV row count")
    out = {}
    for label, line in zip(LABELS[kind], lines[1:]):
        parts = line.split(",")
        ensure(len(parts) == 2 and parts[0] == label and parts[1].isascii()
               and parts[1].isdecimal() and (len(parts[1]) == 1 or parts[1][0] != "0"),
               "original CSV row noncanonical")
        number = int(parts[1])
        ensure(number <= (2**64 - 1 if label in
               ("lease_pages_acquired", "lease_pages_released") else 2**32 - 1),
               "original unsigned counter overflow")
        out[label] = number
    return out


def png_crc(raw: bytes) -> None:
    ensure(45 <= len(raw) <= 5_000_000 and raw[:8] == b"\x89PNG\r\n\x1a\n",
           "invalid original optical PNG signature")
    offset, ihdr, idat, ended = 8, False, False, False
    while offset + 12 <= len(raw):
        length = struct.unpack_from(">I", raw, offset)[0]
        end = offset + length + 12
        ensure(end <= len(raw), "truncated optical PNG chunk")
        kind = raw[offset+4:offset+8]
        data = raw[offset+4:offset+8+length]
        expected_crc = struct.unpack_from(">I", raw, offset+8+length)[0]
        ensure(zlib.crc32(data) == expected_crc, "original optical PNG CRC invalid")
        if not ihdr:
            ensure(kind == b"IHDR" and length == 13
                   and struct.unpack_from(">II", raw, offset+8) == (1280, 720),
                   "original optical PNG geometry invalid")
            ihdr = True
        elif kind == b"IHDR":
            raise ValueError("duplicate PNG IHDR")
        elif kind == b"IDAT":
            idat = True
        elif kind == b"IEND":
            ensure(length == 0 and idat and end == len(raw),
                   "invalid final optical PNG chunk")
            ended = True
            break
        offset = end
    ensure(ended, "missing optical PNG end")


def verify(archive: Path, run: dict, jobs: dict, artifact: dict,
           merge: dict, *, source_sha: dict | None = None,
           optical_sha: dict | None = None) -> dict:
    """Optional digest overrides are **unit-test only**; CLI never exposes them."""
    source_sha = SOURCE_SHA if source_sha is None else source_sha
    optical_sha = OPTICAL_SHA if optical_sha is None else optical_sha
    ensure(archive.is_dir() and not archive.is_symlink(), "missing original archive")
    ensure(type(run.get("id")) is int and run["id"] == RUN_ID
           and run.get("status") == "completed" and run.get("conclusion") == "success"
           and run.get("event") == "pull_request"
           and run.get("repository", {}).get("full_name") == REPO
           and run.get("head_sha") == HEAD_SHA
           and type(run.get("run_attempt")) is int and run["run_attempt"] == 1,
           "finished original GitHub workflow identity invalid")
    ensure(type(merge.get("parents")) is list and
           [p.get("sha") for p in merge["parents"]] ==
           ["61143dcf3517f1f3ea60bcc5acb8aa9c803ede3c", HEAD_SHA]
           and merge.get("sha") == MERGE_SHA,
           "original PR merge commit not tied to source head")
    ensure(artifact.get("id") == ARTIFACT_ID and type(artifact.get("id")) is int
           and artifact.get("name") == ARTIFACT_NAME and artifact.get("expired") is False
           and artifact.get("digest") == ARCHIVE_DIGEST
           and type(artifact.get("size_in_bytes")) is int and artifact["size_in_bytes"] > 0
           and artifact.get("workflow_run", {}).get("id") == RUN_ID
           and artifact["workflow_run"].get("head_sha") == HEAD_SHA,
           "original Actions artifact digest/run binding failed")
    ensure(type(jobs.get("jobs")) is list, "missing original Actions jobs")
    names = {}
    for job in jobs["jobs"]:
        name = job.get("name")
        ensure(type(name) is str and name not in names, "duplicate original Actions job")
        names[name] = job
    for name in ("Validate Stage371 isolated-source invariants before building NRO",
                 "Build one original libnx NRO without SDL2",
                 "Run two separate NeXium guest exits and audit original CSV files"):
        job = names.get(name)
        ensure(type(job) is dict and job.get("run_id") == RUN_ID
               and job.get("status") == "completed" and job.get("conclusion") == "success",
               "failed/absent original Actions job")
    steps = names["Run two separate NeXium guest exits and audit original CSV files"].get("steps")
    ensure(type(steps) is list, "missing original NeXium job steps")
    step_map = {}
    for step in steps:
        name = step.get("name")
        ensure(type(name) is str and name not in step_map, "duplicate original step")
        step_map[name] = step
    ensure(all(step_map.get(name, {}).get("conclusion") == "success" for name in REQUIRED_STEPS),
           "original NeXium stage or archival step failed")

    report = read_meta(archive / "stage371-two-authentic-guest-exits.json")
    preflight = read_meta(archive / "stage371-nro-preflight.json")
    ensure(report.get("schema") == "vh-stage371-two-isolated-neXium-exit-sessions/v1"
           and report.get("result") ==
           "STAGE371_TWO_SEPARATE_GUEST_WAIT_TUPLES_FROM_SAME_NRO_RECORDED"
           and report.get("source_git_sha") == MERGE_SHA
           and report.get("source_run_id") == RUN_ID
           and report.get("source_run_attempt") == 1
           and report.get("single_verified_nro_sha256") == NRO_SHA
           and report.get("two_isolated_original_guest_roots") is True
           and report.get("two_original_guest_source_families_reopened") is True
           and report.get("old_0xEA01_root_cause_proven") is False
           and report.get("two_dwell_observations_are_not_a_controlled_causal_pair") is True
           and report.get("direct_exit_queue_depth_measured") is False
           and report.get("physical_nintendo_switch_audio_tested") is False,
           "original Stage371 claim/identity invalid")
    ensure(preflight.get("result") == "SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED"
           and preflight.get("git_sha") == MERGE_SHA
           and preflight.get("run_id") == RUN_ID and preflight.get("run_attempt") == 1
           and preflight.get("nro_sha256") == NRO_SHA
           and type(preflight.get("nro_bytes")) is int and preflight["nro_bytes"] >= 1024
           and preflight.get("hardware_status") == "HARDWARE NOT TESTED",
           "original same-workflow NRO preflight invalid")
    captures = report.get("captures")
    ensure(type(captures) is list and len(captures) == 2,
           "not two original guest captures")
    evidence = []
    for index, tag in enumerate(("a", "b")):
        item = captures[index]
        ensure(type(item) is dict and item.get("capture_tag") == tag
               and item.get("exit_dwell_seconds") == (6 if tag == "a" else 12)
               and item.get("guest_source_run_id") == RUN_ID
               and item.get("source_guest_sd_root", "").endswith(
                   f"/vh-nexium-stage266-{RUN_ID}-{tag}")
               and item.get("optical_content_independently_decoded") is False
               and item.get("original_guest_speaker_audio_observed") is False
               and item.get("supplemental_telemetry_interpreted_as_exit_queue") is False,
               "wrong guest trial/session identity")
        original_dir = archive / "stage371-originals" / tag
        ensure(original_dir.is_dir() and not original_dir.is_symlink(),
               "missing original preserved guest directory")
        found = {p.name for p in original_dir.iterdir()}
        ensure(found == set(SOURCE_FILES.values()) | set(OPTIONAL) | {"scene-optical-trace.png"},
               "unexpected original file family or omitted witness")
        parsed = {}
        sha = {}
        for kind, name in SOURCE_FILES.items():
            raw = file_bytes(original_dir / name, 1024)
            sha[kind] = digest(raw)
            ensure(sha[kind] == source_sha[tag][kind], "original CSV digest pin mismatch")
            parsed[kind] = parse_csv(raw, kind)
        ensure(item.get("source_guest_csv_sha256") == sha,
               "reported guest CSV SHA not from preserved bytes")
        for name in OPTIONAL:
            raw = file_bytes(original_dir / name, 2048)
            detail = item.get("optional_original_telemetry", {}).get(name)
            ensure(detail == {"present": True, "parsed": False, "sha256": digest(raw)}
                   and raw.startswith(b"scope,value\n") and raw.endswith(b"\n"),
                   "optional guest software telemetry invalid")
        reason, raw_result, desc = parsed["reason"], parsed["result"], parsed["descriptor"]
        ensure(reason["tail_reason_code"] == raw_result["stage351_tail_reason_code"]
               == desc["stage351_tail_reason_code"] == item["source_guest_reason_code"] == 7
               and reason["software_exit_tail_reason_only"] == 1
               and reason["tail_attempted"] == 1
               and reason["tail_descriptor_return_confirmed"] == 1
               and reason["tail_lease_acquired"] == 1
               and reason["lease_pages_acquired"] > 0
               and reason["lease_pages_acquired"] == reason["lease_pages_released"]
               and reason["abandoned_sessions"] == 0
               and raw_result["software_wait_result_only"] == 1
               and raw_result["wait_result_observed"] == 1
               and desc["software_wait_descriptor_only"] == 1
               and desc["stage357_raw_result_crosschecked"] == 1
               and desc["wait_observed"] == 1
               and raw_result["audout_wait_result_raw"] == desc["audout_wait_result_raw"]
               == item["original_service_result"] == 0
               and desc["released_count_reported"] == item["reported_return_count"] == 1
               and desc["returned_pointer_present"] == 1
               and desc["returned_pointer_matches_submitted"] == 1
               and item["reported_pointer_present"] is True
               and item["reported_pointer_matches_submitted"] is True,
               "original Stage351/357/368 software tuple contradicts original CSV")
        optical = file_bytes(original_dir / "scene-optical-trace.png", 5_000_000)
        png_crc(optical)
        ensure(item.get("original_optical_frame_sha256") == digest(optical)
               == optical_sha[tag], "original optical hash mismatch")
        evidence.append({"trial": tag, "exit_dwell_seconds": item["exit_dwell_seconds"],
                         "original_csv_sha256": sha,
                         "optical_sha256": digest(optical),
                         "software_wait_result": 0,
                         "released_descriptors": 1,
                         "guest_pcm_lease_pages_acquired": reason["lease_pages_acquired"],
                         "guest_pcm_lease_pages_released": reason["lease_pages_released"],
                         "abandoned_sessions": 0})
    ensure(evidence[0]["original_csv_sha256"]["reason"] !=
           evidence[1]["original_csv_sha256"]["reason"]
           and evidence[0]["optical_sha256"] != evidence[1]["optical_sha256"],
           "reused pair of guest sources")
    return {
        "schema": "vh-stage372-independent-finished-original-stage371-pair/v1",
        "result": VERDICT,
        "source_run_id": RUN_ID,
        "source_pr_head_sha": HEAD_SHA,
        "source_workflow_merge_sha": MERGE_SHA,
        "source_artifact_id": ARTIFACT_ID,
        "github_reported_archive_digest": ARCHIVE_DIGEST,
        "single_nro_sha256": NRO_SHA,
        "original_runs_replayed": evidence,
        "direct_exit_queue_depth_measured": False,
        "historical_0xEA01_root_cause_proven": False,
        "pixel_content_semantically_decoded": False,
        "physical_switch_speaker_audio_tested": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "run-json", "jobs-json", "artifact-json", "merge-commit-json", "output"):
        p.add_argument("--" + name, required=True, type=Path)
    a = p.parse_args(argv)
    try:
        ensure(not a.output.exists() and not a.output.is_symlink(),
               "refuse overwrite of Stage372 verdict")
        result = verify(a.archive, read_meta(a.run_json), read_meta(a.jobs_json),
                        read_meta(a.artifact_json), read_meta(a.merge_commit_json))
        a.output.parent.mkdir(parents=True, exist_ok=True)
        with a.output.open("x", encoding="utf-8") as f:
            json.dump(result, f, indent=2, sort_keys=True)
            f.write("\n")
        print(json.dumps({"result": VERDICT, "results": [0, 0],
                          "descriptor_counts": [1, 1],
                          "physical_sound_tested": False}, sort_keys=True))
        return 0
    except (ValueError, KeyError, OSError, TypeError, UnicodeError) as exc:
        print(json.dumps({"result": "STAGE372_SOURCE_PAIR_NOT_VERIFIED",
                          "error_kind": type(exc).__name__,
                          "historical_timeout_cause_proven": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
