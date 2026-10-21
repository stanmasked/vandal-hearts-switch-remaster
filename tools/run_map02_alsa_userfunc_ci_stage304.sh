#!/usr/bin/env bash
# Stage304 research-only, exact ROM-free user-space ALSA guest run.
set -euo pipefail
: "$VH_HINT" "$GITHUB_RUN_ID" "$RUNNER_TEMP" "$VH_HOST" "$VH_NRO" "$VH_EXACT_HEAD"
[[ "$VH_HINT" == 21 || "$VH_HINT" == 22 ]]
test "$(git rev-parse HEAD)" = "$VH_EXACT_HEAD"
mkdir -p evidence research
chmod +x host/nexium
printf '%s  host/nexium\n' "$VH_HOST" | sha256sum -c -
printf '%s  guest/vandal-hearts-map02-audio.nro\n' "$VH_NRO" | sha256sum -c -

python3 - <<'PY'
from pathlib import Path
import subprocess,json,os,hashlib
parent="c078f481cd9b58450bb2e591d27e6c0c14764736"
observed=set(subprocess.check_output(
 ["git","diff","--name-only",parent,"HEAD"],text=True).splitlines())
allow={".github/workflows/map02-alsa-userfunc-stage304.yml",
 "tools/map02_alsa_avail_preload_stage304.c",
 "tools/run_map02_alsa_userfunc_guest_stage304.sh",
 "tools/audit_map02_alsa_userfunc_stage304.py",
 "tools/run_map02_alsa_userfunc_ci_stage304.sh",
 "tests/test_audit_map02_alsa_userfunc_stage304.py",
 "docs/MAP02_ALSA_USERFUNC_STAGE304.md"}
assert observed and observed<=allow,sorted(observed-allow)
m=json.loads(Path("host/manifest.json").read_text())
g=json.loads(Path("guest/manifest.json").read_text())
h=Path("host/nexium").read_bytes()
n=Path("guest/vandal-hearts-map02-audio.nro").read_bytes()
assert h[:4]==b"\x7fELF" and n[16:20]==b"NRO0"
assert hashlib.sha256(h).hexdigest()==os.environ["VH_HOST"]
assert hashlib.sha256(n).hexdigest()==os.environ["VH_NRO"]
assert m["schema"]=="vh-map02-stage298-nexium-cpal-timestamped-host-build/v1"
assert m["result"]=="STAGE298_OPT_IN_TIMESTAMPED_NEXIUM_LINUX_BINARY_COMPILED"
assert m["research_head_sha"]=="e801588983a866c76dcedb52e818859a68ad113d"
assert m["pinned_upstream_source_sha"]=="089562567a0a8760dfdd8420e1f57c35159a9219"
assert m["cargo_lock_sha256"]=="e6e8fcb90624650afddd1f25327dd4e6b042b094e8336cb5f43d2dc370e28739"
assert m["executable_sha256"]==os.environ["VH_HOST"]
assert g["schema"]=="vh-map02-presubmit-guest-nro/v1"
assert g["source_sha"]=="04b20024a50327091cff430eb5c28e4722d4ec76"
assert g["run_id"]==39460035568 and g["nro_sha256"]==os.environ["VH_NRO"]
assert Path("guest/nro.sha256").read_text().split()[0]==os.environ["VH_NRO"]
Path("evidence/stage298-source-pinned-build-manifest.json").write_text(
 json.dumps(m,sort_keys=True,indent=2)+"\n")
pair={
 "schema":"vh-map02-stage299-pinned-new-elf-and-generated-nro/v1",
 "exact_stage298_elf_sha256":m["executable_sha256"],
 "exact_generated_nro_sha256":g["nro_sha256"],
 "stage298_build_source_sha":m["research_head_sha"],
 "stage298_build_run_id":39509934054,
 "original_nro_artifact_run_id":39460035568,
 "guest_original_research_source_sha":g["source_sha"],
 "hint_ms":int(os.environ["VH_HINT"]),
 "actual_stage299_run_id":int(os.environ["GITHUB_RUN_ID"]),
 "attempt":int(os.environ["GITHUB_RUN_ATTEMPT"]),
 "rom_or_licensed_audio_used":False,
 "physical_switch_speaker_proven":False}
Path("evidence/stage299-pinned-new-host-guest.json").write_text(
 json.dumps(pair,sort_keys=True,indent=2)+"\n")
PY

python3 -m unittest discover -s tests -p 'test_audit_map02_alsa_userfunc_stage304.py' -v
gcc -O2 -fPIC -shared -std=gnu11 -Wall -Wextra -Werror \
  -o research/libvh_map02_alsa_stage304.so tools/map02_alsa_avail_preload_stage304.c -ldl -pthread
nm -D --defined-only research/libvh_map02_alsa_stage304.so | grep -F snd_pcm_avail_delay
ldd research/libvh_map02_alsa_stage304.so >evidence/research-also-library-links.txt
! grep -F "not found" evidence/research-also-library-links.txt
sha256sum research/libvh_map02_alsa_stage304.so | cut -d' ' -f1 >evidence/research-alsa-preload-sha256.txt

export MAP02_HOST="$PWD/host/nexium"
export MAP02_NRO="$PWD/guest/vandal-hearts-map02-audio.nro"
export MAP02_EVIDENCE="$PWD/evidence"
export MAP02_ALSA_SHIM="$PWD/research/libvh_map02_alsa_stage304.so"
export VH_MAP02_CPAL_LIFETIME_PATH="$MAP02_EVIDENCE/host-cpal-lifetime-p.csv"
if ! bash tools/run_map02_alsa_userfunc_guest_stage304.sh; then
 python3 - <<'PY'
import hashlib,json,re
from pathlib import Path
root=Path("evidence")
log=root/"nexium-guest-stdout.log"
raw=log.read_bytes() if log.is_file() else b""
body=raw.decode("utf-8",errors="replace").lower()
patterns={
  "panic":r"\bpanic\b|panicked",
  "segmentation_fault":r"segmentation fault|sigsegv|segfault",
  "illegal_instruction":r"illegal instruction|sigill",
  "symbol_lookup":r"undefined symbol|symbol lookup error|relocation error",
  "library_load":r"error while loading shared libraries|cannot open shared object",
  "rust_error":r"rustarmic|backtrace",
  "graphics_initialization":r"vulkan|xcb|x11|winit|egl|gtk",
  "alsa_or_cpal":r"alsa|cpal|snd_pcm|audio",
  "generic_failure":r"\bfailed\b|\berror\b|fatal",
  "early_exit_without_gui":r"no window|no such window",
}
counts={k:len(re.findall(p,body)) for k,p in patterns.items()}
# Strictly diagnostic, bounded, redacted *only* matching failure lines.
# No unfiltered stdout, paths, TIDs, PIDs, hostnames or environment values.
safe=[]
for original in raw.decode("utf-8",errors="replace").splitlines():
 if not re.search(r"error|failed|panic|vulkan|display|render|window",original,re.I):
  continue
 value=re.sub(r"(?:/[-_A-Za-z0-9.]+){2,}", "<PATH>",original)
 value=re.sub(r"[A-Za-z0-9_.%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "<EMAIL>",value)
 value=re.sub(r"0x[0-9a-fA-F]+", "<ADDR>",value)
 value=re.sub(r"\b\d{5,}\b", "<NUM>",value)
 value=re.sub(r"[\x00-\x1f\x7f]", " ",value)
 safe.append(value[:180])
 if len(safe)>=4:break
exit_path=root/"host-early-exit-code.txt"
exit_code=None
if exit_path.is_file():
 try: exit_code=int(exit_path.read_text().strip())
 except ValueError: exit_code=None
out={
 "schema":"vh-map02-stage304-sanitized-launch-failure/v1",
 "result":"NE_XIUM_CHILD_ENDED_BEFORE_GUEST_WINDOW",
 "child_exit_code_if_observed":exit_code,
 "raw_stdout_sha256":hashlib.sha256(raw).hexdigest(),
 "raw_stdout_size_bytes":len(raw),
 "sanitized_error_category_counts":counts,
 "redacted_failure_lines":safe,
 "raw_stdout_or_private_host_log_uploaded":False,
 "no_alsa_root_cause_or_hardware_audio_proven":True}
(root/"stage304-sanitized-early-exit.json").write_text(
 json.dumps(out,indent=2,sort_keys=True)+"\n")
print(json.dumps(out,indent=2,sort_keys=True))
PY
 exit 1
fi
test -s evidence/host-alsa-avail-delay-usertrace.csv

python3 tools/audit_map02_cpal_lifecycle_snapshots.py \
 --trace evidence/host-cpal-audioout-timeline.csv \
 --first-input-marker evidence/guest-first-input-monotonic-ns.txt \
 --final-observation-marker evidence/guest-final-observation-monotonic-ns.txt \
 --output evidence/host-cpal-lifecycle-audit.json
python3 tools/audit_map02_cpal_lifetime_stage299.py \
 --p evidence/host-cpal-lifetime-p.csv --l evidence/host-cpal-audioout-timeline.csv \
 --first-input-marker evidence/guest-first-input-monotonic-ns.txt \
 --final-observation-marker evidence/guest-final-observation-monotonic-ns.txt \
 --output evidence/host-cpal-lifetime-audit.json
python3 tools/decode_map02_prejoin_stage.py \
 --image evidence/guest-prejoin.png --output evidence/guest-prejoin-stage.json
if python3 tools/decode_map02_audout_presubmit.py \
 --image evidence/guest-final.png --output evidence/guest-final-receipt.json; then
 echo "True 8/8 research guest CRC PASS"
else
 echo "Actual final optical guest unverified; not fabricated as success"
fi

python3 - <<'PY'
from pathlib import Path
import hashlib,json,sys
from array import array
p=Path("evidence/virtual-pulse-48k-stereo-s16le.pcm")
data=p.read_bytes()
assert len(data)>100000 and len(data)%4==0
a=array("h");a.frombytes(data)
if sys.byteorder!="little":a.byteswap()
health={"schema":"vh-map02-stage299-virtual-pcm/v1",
 "raw_sha256":hashlib.sha256(data).hexdigest(),
 "bytes":len(data),"valid_pcm16le_stereo":True,
 "nonzero_pcm16_samples":sum(x!=0 for x in a),
 "physical_switch_dac_proven":False}
Path("evidence/virtual-pcm-health.json").write_text(
 json.dumps(health,sort_keys=True,indent=2)+"\n")
print(json.dumps(health,sort_keys=True))
PY

python3 tools/audit_map02_cpal_lifetime_guest_stage299.py \
 --evidence evidence --logdir "$RUNNER_TEMP/vh-map02-stage294-home/.config/NeXium/logs" \
 --hint "$VH_HINT" --run-id "$GITHUB_RUN_ID" \
 --output evidence/stage299-source-pinned-real-lifetime-receipt.json
python3 tools/audit_map02_pulse_event_clocks_stage301.py \
 --evidence evidence --hint "$VH_HINT" --run-id "$GITHUB_RUN_ID" \
 --output evidence/stage301-pulse-subscribe-verified.json
python3 tools/audit_map02_alsa_userfunc_stage304.py \
 --evidence evidence --hint "$VH_HINT" --run-id "$GITHUB_RUN_ID" \
 --output evidence/stage304-real-alsa-userfunc-receipt.json
python3 - <<'PY'
from pathlib import Path
import json,os
r=json.loads(Path("evidence/stage304-real-alsa-userfunc-receipt.json").read_text())
assert r["result"]=="REAL_STAGE304_GUEST_USERSPACE_ALSA_AVAIL_DELAY_REPARSED"
assert r["requested_pulse_latency_hint_ms"]==int(os.environ["VH_HINT"])
assert r["actual_stage298_nexium_elf_sha256"]==os.environ["VH_HOST"]
assert r["unchanged_generated_rom_free_guest_nro_sha256"]==os.environ["VH_NRO"]
assert r["no_alsa_root_cause_or_physical_switch_output_proven"] is True
with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:
 print("### Stage304 genuine userspace ALSA observation",file=f)
 print("Result: **"+r["result"]+"**",file=f)
 for k in ("requested_pulse_latency_hint_ms","source_guest_post_input_CPAL_callback_entries",
           "source_guest_research_optical_CRC_8_of_8","source_virtual_48k_PCM_nonzero_samples",
           "preload_reporter_interceptor_symbol_resolved","intercepted_ALSA_avail_delay_guest_counts"):
  print(k+": "+str(r[k]),file=f)
 print("Interposition can miss internal calls and perturbs scheduling; no cause or Switch DAC proven.",file=f)
PY
