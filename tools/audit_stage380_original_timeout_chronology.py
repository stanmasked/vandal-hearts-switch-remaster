#!/usr/bin/env python3
"""Stage380: source-pinned replay of two original NeXium exit timelines.

Software evidence only; no DAC, hardware, or causal timeout conclusions.
"""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

REPO = "stanmasked/vandal-hearts-switch-remaster"
SOURCE = (
    ("historical_timeout", 39325440778, "39325440778.zip",
     "757c1146043804b443c8cddd5020a8f8d73b839ba01e82efea4e001daf17755f", 0xEA01, 4),
    ("later_success", 39388027581, "39388027581.zip",
     "d495d5d38be6f40c7fb7a6bfa152c8a33e579a488771bdcf00e2c9063bdbf8a7", 0, 7),
)
SOURCE_IDENTITY = {
    39325440778: {"head":"3ecf5933d913b449148edd510f21e7bde7af4e90",
                  "artifact":12223136961,
                  "nro_sha256":"ebe78e3ea9c0d3791431c462620b171a04e830d0dca1c8d2a45f51ab24786e3a"},
    39388027581: {"head":"323a408431509924865b751b9677d2dafdde64c3",
                  "artifact":12249301260,
                  "nro_sha256":"cfc49a8ac8dcfe4704e697c1bea8fc750ea32d498c2942176c2ca9b9cbcae71b"},
}
NAMES = (
    "audio-exit-tail-reason-000.csv", "audio-exit-tail-wait-result-000.csv",
    "audio-exit-output-000.csv", "audio-exit-timeline-000.csv",
    "audio-exit-worker-stop-000.csv", "audio-last-playbuffer-000.csv",
    "audio-lease-reconciliation-000.csv", "audio-playbuffer-history-000.csv",
)
RESULT = "STAGE380_ORIGINAL_TIMEOUT_AND_SUCCESS_CHRONOLOGY_VERIFIED"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parse_csv(raw):
    require(raw.endswith(b"\n") and b"\r" not in raw, "invalid CSV framing")
    rows = raw.decode("ascii").splitlines()
    require(rows and rows[0] in (
        "scope,value", "event,value", "event,guest_monotonic_ns",
        "total_attempts,sequence,begin_guest_ns,end_guest_ns,lease_returned"),
        "invalid CSV header")
    cells = [x.split(",") for x in rows[1:]]
    if rows[0].startswith("total_attempts,"):
        require(all(len(x)==5 and all(p.isdecimal() for p in x) for x in cells),
                "invalid buffer history")
        return [tuple(map(int,x)) for x in cells]
    require(all(len(x)==2 and x[1].isdecimal() for x in cells), "invalid CSV cell")
    require(len({x[0] for x in cells})==len(cells), "duplicate CSV key")
    return {k:int(v) for k,v in cells}


def check_origin(run, artifact, jobs, spec, archive_size):
    _, rid, _, zipsha, _, _ = spec
    pin = SOURCE_IDENTITY[rid]
    require(run.get("id")==rid and run.get("head_sha")==pin["head"] and
        run.get("event")=="push" and run.get("run_attempt")==1 and
        run.get("name")=="Experimental NRO runtime smoke test" and
        run.get("status")=="completed" and run.get("conclusion")=="success" and
        run.get("repository",{}).get("full_name")==REPO, "wrong original run")
    require(artifact.get("id")==pin["artifact"] and
        artifact.get("name")=="nexium-runtime-evidence" and
        artifact.get("digest")=="sha256:"+zipsha and
        artifact.get("size_in_bytes")==archive_size and
        artifact.get("expired") is False and
        artifact.get("workflow_run",{}).get("id")==rid and
        artifact.get("workflow_run",{}).get("head_sha")==pin["head"],
        "wrong original artifact")
    expected={"Build libnx NRO for runtime smoke test",
              "Launch current-workflow audout NRO in NeXium"}
    actual=[j for j in jobs.get("jobs",[]) if j.get("name") in expected]
    require(len(actual)==2 and {j.get("name") for j in actual}==expected and
        all(j.get("run_id")==rid and j.get("status")=="completed" and
            j.get("conclusion")=="success" for j in actual),
        "wrong original build/guest jobs")


def replay(spec, originals):
    kind, rid, name, zipsha, code, reason_code = spec
    archive=originals/name
    require(archive.is_file() and digest(archive.read_bytes())==zipsha,
            "incorrect original ZIP SHA256")
    with ZipFile(archive) as z:
        require(z.testzip() is None and len(z.namelist())==len(set(z.namelist())),
                "invalid ZIP entries")
        data={}
        hashes={}
        for name in NAMES:
            raw=z.read("runtime-evidence/"+name)
            data[name]=parse_csv(raw)
            hashes[name]=digest(raw)
        receipt=json.loads(z.read("integrated-nro-preflight.json"))
        pin=SOURCE_IDENTITY[rid]
        require(receipt.get("run_id")==rid and receipt.get("git_sha")==pin["head"]
                and receipt.get("nro_sha256")==pin["nro_sha256"] and
                receipt.get("run_attempt")==1 and
                receipt.get("result")=="SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED" and
                receipt.get("hardware_status")=="HARDWARE NOT TESTED",
                "wrong NRO provenance")
    reason,wait,output,time,worker,play,lease,hist=(data[name] for name in NAMES)
    require(wait["audout_wait_result_raw"]==code and
            wait["stage351_tail_reason_code"]==reason["tail_reason_code"]==reason_code,
            "guest wait outcome mismatch")
    require(reason["tail_attempted"]==reason["tail_lease_acquired"]==1 and
            reason["lease_pages_acquired"]==lease["lease_pages_acquired"] and
            reason["lease_pages_released"]==lease["lease_pages_released"] and
            reason["abandoned_sessions"]==lease["abandoned_sessions"],
            "PCM ownership mismatch")
    require(lease["mismatched_releases"]==lease["submit_failures"]==
            lease["busy_begin_rejections"]==play["failures"]==0,
            "unexpected regular buffer errors")
    require(play["attempts"]==play["successes"]==output["page_return_count"],
            "regular buffer totals mismatch")
    require(len(hist)==16 and
        all(x[0]==play["attempts"] and x[1]==play["attempts"]-15+i and
            x[4]==1 and x[3]>x[2] for i,x in enumerate(hist)),
        "invalid last sixteen buffer calls")
    require(all(hist[i][3]<hist[i+1][2] for i in range(15)) and
        hist[-1][2]==play["last_success_begin_guest_ns"] and
        hist[-1][3]==play["last_success_end_guest_ns"],
        "incorrect source buffer chronology")
    require(time["plus_observed"]<time["stop_requested"] and
        play["last_success_begin_guest_ns"]<time["stop_requested"]<
        play["last_success_end_guest_ns"]<=output["last_page_return_guest_ns"]<
        worker["worker_stop_observed"]<=time["worker_cleanup_entered"]<
        output["tail_attempt_guest_ns"]<time["audout_closed"]<time["worker_joined"],
        "invalid original exit chronology")
    if code:
        require(reason["tail_descriptor_return_confirmed"]==0 and
            output["tail_success_return_guest_ns"]==0 and
            lease["lease_pages_acquired"]-lease["lease_pages_released"]==1 and
            lease["abandoned_sessions"]==1, "failed wait released unsafe page")
    else:
        require(reason["tail_descriptor_return_confirmed"]==1 and
            output["tail_success_return_guest_ns"]>output["tail_attempt_guest_ns"] and
            lease["lease_pages_acquired"]==lease["lease_pages_released"] and
            lease["abandoned_sessions"]==0, "successful wait lacked release")
    def millis(v): return round(v/1e6,6)
    gap=output["tail_attempt_guest_ns"]-output["last_page_return_guest_ns"]
    return {"classification":kind,"source_run_id":rid,
        "source_zip_sha256":zipsha,"original_guest_csv_sha256":hashes,
        "raw_service_result":code,"stage351_tail_reason_code":reason_code,
        "pcm_pages_acquired":lease["lease_pages_acquired"],
        "pcm_pages_released":lease["lease_pages_released"],
        "abandoned_sessions":lease["abandoned_sessions"],
        "guest_chronology_ms":{
          "last_page_return_to_tail_attempt_ms":millis(gap),
          "last_normal_playbuffer_call_ms":millis(play["last_success_end_guest_ns"]-play["last_success_begin_guest_ns"]),
          "tail_attempt_to_audout_close_ms":millis(time["audout_closed"]-output["tail_attempt_guest_ns"]),
          "tail_attempt_to_positive_ack_ms":millis(output["tail_success_return_guest_ns"]-output["tail_attempt_guest_ns"]) if not code else None}}


def read_json(path):
    require(path.is_file() and not path.is_symlink() and
            0<path.stat().st_size<=500000, "invalid original metadata")
    return json.loads(path.read_text(encoding="utf-8"))


def audit(originals,metadata):
    source=[]
    for spec in SOURCE:
        _,rid,name,*_=spec
        archive=originals/name
        require(archive.is_file() and not archive.is_symlink() and
                20000<archive.stat().st_size<=40000000,"missing source artifact")
        check_origin(read_json(metadata/f"{rid}-run.json"),
                     read_json(metadata/f"{rid}-artifact.json"),
                     read_json(metadata/f"{rid}-jobs.json"),spec,archive.stat().st_size)
        source.append(replay(spec,originals))
    gap=abs(source[0]["guest_chronology_ms"]["last_page_return_to_tail_attempt_ms"]-
            source[1]["guest_chronology_ms"]["last_page_return_to_tail_attempt_ms"])
    return {"schema":"vh-stage380-original-timeout-vs-success/v1","result":RESULT,
      "source_run_ids":[spec[1] for spec in SOURCE],
      "original_guest_software_wait_results":[59905,0],
      "source_runs":source,"nominal_exit_pcm_frames":96,
      "output_sample_rate_hz":48000,"nominal_exit_pcm_duration_ms":2.0,
      "bounded_wait_limit_ms":12.0,
      "prior_return_to_tail_gap_difference_us":round(gap*1000,3),
      "historical_timeout_root_cause_proven":False,
      "physical_nintendo_switch_speaker_audio_tested":False,
      "direct_exit_queue_depth_observed":False,
      "cross_revision_comparison_is_not_causal":True}


def main(argv=None):
    parser=argparse.ArgumentParser()
    for key in ("originals","metadata","output"):
        parser.add_argument("--"+key,type=Path,required=True)
    opts=parser.parse_args(argv)
    try:
        require(not opts.output.exists() and not opts.output.is_symlink(),
                "refusing to overwrite original source receipt")
        report=audit(opts.originals,opts.metadata)
        opts.output.parent.mkdir(parents=True,exist_ok=True)
        opts.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print(json.dumps({"result":RESULT,"original_wait_results":[59905,0],"physical_audio_tested":False}))
        return 0
    except (ValueError,KeyError,TypeError,OSError,UnicodeError,RuntimeError) as e:
        print(json.dumps({"result":"STAGE380_SOURCE_CHRONOLOGY_NOT_VERIFIED",
                          "error_kind":type(e).__name__,"hardware_status":"HARDWARE NOT TESTED"}))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
