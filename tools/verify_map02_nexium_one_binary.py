#!/usr/bin/env python3
"""Verify identical host NeXium SHA in six *actual* same-run guest archives.

Host binary identity is a necessary control, NOT evidence of a CPAL root
cause, guest deadlock, Nintendo Switch speaker audio or upstream revision.
"""
import argparse
import hashlib
import json
from pathlib import Path

from audit_map02_cpal_alsa_boundary import audit, require

SCHEMA = "vh-map02-nexium-six-guest-host-identity/v1"
HOST_SCHEMA = "vh-map02-nexium-one-host-binary/v1"


def read(path):
    v = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(v, dict), f"Not an object: {path}")
    return v


def verify_host_links(root, source, run_id):
    host_dir = root / "map02-nexium-once-binary"
    host = read(host_dir / "manifest.json")
    archive = (host_dir / "nexium-linux-x86_64.tar.gz").read_bytes()
    require(host.get("schema") == HOST_SCHEMA, "Wrong host manifest schema")
    require(host.get("source_sha") == source and
            host.get("run_id") == run_id,
            "Wrong original source SHA or Actions run")
    require(type(host.get("attempt")) is int and host["attempt"] > 0,
            "Host run attempt not recorded")
    require(type(host.get("upstream_asset_id")) is int and
            host["upstream_asset_id"] > 0 and
            type(host.get("upstream_release_id")) is int and
            host["upstream_release_id"] > 0,
            "Missing release/asset identity")
    digest = host.get("host_executable_sha256")
    require(isinstance(digest, str) and len(digest) == 64 and
            all(ch in "0123456789abcdef" for ch in digest),
            "Invalid NeXium executable SHA-256")
    require(archive and
            hashlib.sha256(archive).hexdigest() ==
            host.get("host_archive_sha256"), "NeXium archive SHA-256 mismatch")
    require(host.get("upstream_source_commit_verified") is False and
            host.get("cross_run_release_immutability_proven") is False,
            "Do not imply upstream commit/release immutability")
    trials = []
    for ms in (21, 22):
        for repetition in (1, 2, 3):
            name = f"map02-presubmit-nexium-guest-proof-{ms}-r{repetition}"
            trial_dir = root / name
            require(trial_dir.is_dir(), f"Missing independent guest {name}")
            copied = read(trial_dir / "nexium-host-build.json")
            require(copied == host, f"Host manifest mismatch in {name}")
            original = read(trial_dir / "pulse-client-trial.json")
            require(original.get("source_sha") == source and
                    original.get("run_id") == run_id and
                    original.get("attempt") == host["attempt"] and
                    original.get("variant") == str(ms) and
                    original.get("independent_repeat") == repetition,
                    f"Wrong guest trial provenance {name}")
            require(original.get("same_run_host_binary_sha256_verified") is True
                    and original.get("host_binary_sha256") == digest,
                    f"Host executable identity unverified in {name}")
            trials.append({"hint_ms": ms, "repeat": repetition,
                           "name": name, "host_executable_sha256": digest})
    require(len(trials) == 6, "Six independent host confirmations required")
    return {
        "schema": SCHEMA, "run_id": run_id, "source_sha": source,
        "upstream_release_id": host["upstream_release_id"],
        "upstream_asset_id": host["upstream_asset_id"],
        "host_archive_sha256": host["host_archive_sha256"],
        "host_executable_sha256": digest,
        "same_host_executable_sha256_all_six_verified": True,
        "upstream_source_commit_verified": False,
        "cross_run_release_immutability_proven": False,
        "cpal_alsa_root_cause_proven": False,
        "physical_nintendo_switch_speaker_proven": False,
        "guest_trials": trials,
    }



def verify_evidence_attempts(root, source, run_id):
    """All original NRO and guest artifacts must originate in one attempt.

    GitHub run ID alone is insufficient when jobs from a rerun can retain
    artifacts from a previous attempt. No SHA equality may override this.
    """
    host = read(root / "map02-nexium-once-binary" / "manifest.json")
    attempt = host["attempt"]
    files = [root / "map02-audout-presubmit-research-nro" / "manifest.json"]
    files.extend(root / f"map02-presubmit-nexium-guest-proof-{ms}-r{rep}"
                 / "manifest.json" for ms in (21, 22) for rep in (1, 2, 3))
    for file in files:
        data = read(file)
        require(data.get("schema") == "vh-map02-presubmit-guest-nro/v1" and
                data.get("source_sha") == source and
                data.get("run_id") == run_id and
                type(data.get("attempt")) is int and
                data["attempt"] == attempt,
                f"Cross-attempt research NRO or guest artifact: {file}")
    return attempt


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--source-sha", required=True)
    ap.add_argument("--run-id", required=True, type=int)
    ap.add_argument("--output", required=True, type=Path)
    opts = ap.parse_args()
    try:
        identity = verify_host_links(opts.root,opts.source_sha,opts.run_id)
        identity["verified_run_attempt"] = verify_evidence_attempts(
            opts.root,opts.source_sha,opts.run_id)
        # Don't claim audit complete from copied manifests alone: CRC-8
        # PNGs, real PCM bytes and NRO digest must all independently match.
        evidence = audit(opts.root,opts.source_sha,opts.run_id)
        require(evidence["all_six_artifact_provenance_and_pcm_integrity_verified"],
                "Independent six-run audit missing")
        require(evidence["same_guest_nro_sha256_all_six_verified"],
                "Same guest NRO not proven")
        require(len(evidence["trials"]) == 6,
                "Six original guest screenshots and PCM recordings required")
        identity["same_guest_nro_sha256_all_six_verified"] = True
        identity["six_raw_guest_evidence_sets_verified"] = True
        identity["trials"] = evidence["trials"]
        identity["result"] = "SAME_RUN_HOST_BINARY_AND_GUEST_NRO_VERIFIED"
        code = 0
    except (OSError,UnicodeError,ValueError,KeyError,TypeError) as exc:
        identity = {
            "schema":SCHEMA,"result":"UNVERIFIED","reason":str(exc),
            "same_host_executable_sha256_all_six_verified":False,
            "same_guest_nro_sha256_all_six_verified":False,
            "six_raw_guest_evidence_sets_verified":False,
            "cpal_alsa_root_cause_proven":False,
            "physical_nintendo_switch_speaker_proven":False
        }
        code=1
    opts.output.parent.mkdir(parents=True,exist_ok=True)
    opts.output.write_text(json.dumps(identity,indent=2,sort_keys=True)+"\n",
                           encoding="utf-8")
    print(json.dumps(identity,indent=2,sort_keys=True))
    return code


if __name__=="__main__":
    raise SystemExit(main())
