#!/usr/bin/env bash
# Opt-in ROM-free MAP02 guest positive control on a verified NeXium ELF.
set -euo pipefail
: "$MAP02_HOST" "$MAP02_NRO" "$MAP02_EVIDENCE" "$RUNNER_TEMP"
[[ "$MAP02_HOST" = /* && "$MAP02_NRO" = /* && "$MAP02_EVIDENCE" = /* ]]
[[ -x "$MAP02_HOST" && -s "$MAP02_NRO" ]]
mkdir -p "$MAP02_EVIDENCE"
export XDG_RUNTIME_DIR="$RUNNER_TEMP/vh-map02-stage294-runtime"
mkdir -p "$XDG_RUNTIME_DIR"; chmod 700 "$XDG_RUNTIME_DIR"
export HOME="$RUNNER_TEMP/vh-map02-stage294-home"
mkdir -p "$HOME"
pulseaudio --daemonize=yes --exit-idle-time=-1 \
  --log-target=file:"$MAP02_EVIDENCE/pulseaudio.log"
export PULSE_SERVER="unix:$XDG_RUNTIME_DIR/pulse/native"
pactl load-module module-null-sink sink_name=vh_map02_stage294 \
  rate=48000 channels=2 >"$MAP02_EVIDENCE/pulse-module-id.txt"
pactl set-default-sink vh_map02_stage294
pactl list short sources >"$MAP02_EVIDENCE/pulse-sources.txt"
grep -F vh_map02_stage294.monitor "$MAP02_EVIDENCE/pulse-sources.txt"
printf 'pcm.!default { type pulse }\nctl.!default { type pulse }\n' >"$RUNNER_TEMP/stage294-alsa.conf"
export ALSA_CONFIG_PATH="$RUNNER_TEMP/stage294-alsa.conf"
export SDL_AUDIODRIVER=pulse
export NEXIUM_X11=1
# NeXium app settings default to Dynarmic, but Stage276 ELF deliberately
# compiled ONLY backend-rustarmic. Force its supported CPU variant.
# Otherwise the GUI/audio CPAL can run without launching the research NRO.
export NEXIUM_CPU_BACKEND=rustarmic
export NEXIUM_LOG_LEVEL=info
export LIBGL_ALWAYS_SOFTWARE=1
export WGPU_BACKEND=vulkan
icd="$(find /usr/share/vulkan/icd.d -maxdepth 1 -name 'lvp_icd*.json' -print -quit)"
test -n "$icd"
export VK_ICD_FILENAMES="$icd"
# ALSA Stage305 experimental userspace shim: ONLY the NeXium child inherits
# LD_PRELOAD. The Python observer never runs inside CPAL callbacks.
: "${MAP02_STAGE305_SHIM:?Stage305 compiled shim absolute path required}"
[[ "$MAP02_STAGE305_SHIM" = /* && -s "$MAP02_STAGE305_SHIM" ]]
python3 tools/capture_map02_alsa_userspace_stage305.py \
  --init --source "$MAP02_EVIDENCE/alsa-userspace-counter-PRIVATE.bin"
python3 -u tools/capture_map02_alsa_userspace_stage305.py \
  --source "$MAP02_EVIDENCE/alsa-userspace-counter-PRIVATE.bin" \
  --output "$MAP02_EVIDENCE/alsa-userspace-anonymous-atomic.csv" \
  --ready "$MAP02_EVIDENCE/alsa-userspace-observer-ready-ns.txt" &
alsawatch=$!
for i in $(seq 1 25); do
  test -s "$MAP02_EVIDENCE/alsa-userspace-observer-ready-ns.txt" && break
  sleep 0.1
done
test -s "$MAP02_EVIDENCE/alsa-userspace-observer-ready-ns.txt"
kill -0 "$alsawatch"
# Stage301 opt-in non-host / non-guest research recorder: start AFTER Pulse
# setup but BEFORE the unchanged NeXium GUI startup and guest input.
python3 -u tools/capture_map02_pulse_events_stage301.py \
  --output "$MAP02_EVIDENCE/pulse-sink-input-events-monotonic.csv" \
  --ready "$MAP02_EVIDENCE/pulse-event-subscriber-ready-ns.txt" &
observer=$!
for i in $(seq 1 20); do
  test -s "$MAP02_EVIDENCE/pulse-event-subscriber-ready-ns.txt" && break
  sleep 0.1
done
test -s "$MAP02_EVIDENCE/pulse-event-subscriber-ready-ns.txt"
kill -0 "$observer"
# A readiness marker proves the watcher launched, NOT that Pulse subscribed
# instantaneously. Preserve this pre-guest interval as possible blind spot.
sleep 0.5
parec --device=vh_map02_stage294.monitor --format=s16le \
  --rate=48000 --channels=2 \
  >"$MAP02_EVIDENCE/virtual-pulse-48k-stereo-s16le.pcm" \
  2>"$MAP02_EVIDENCE/parec.log" &
capture=$!
trap 'kill -TERM "$alsawatch" 2>/dev/null || true; kill -TERM "$observer" 2>/dev/null || true; kill -KILL "$capture" 2>/dev/null || true' EXIT
sleep 1; kill -0 "$capture"
# Exact same Stage290 guest route; ONLY requested Pulse hint is matrix-controlled.
: "${VH_HINT:?21 or 22 requested hint required}"
[[ "$VH_HINT" = 21 || "$VH_HINT" = 22 ]]
export PULSE_LATENCY_MSEC="$VH_HINT"
# Use the documented NeXium root override to pin the GUI FileLogger
# to the SAME isolated per-run directory already expected by the auditor.
# Do not change the immutable guest NRO, ELF or audio parameters.
export NEXIUM_DATA_ROOT="$HOME/.config/NeXium"
mkdir -p "$NEXIUM_DATA_ROOT"
export VH_MAP02_CPAL_TRACE_PATH="$MAP02_EVIDENCE/host-cpal-audioout-timeline.csv"
timeout --kill-after=5s 75s xvfb-run -a -s "-screen 0 1280x720x24" bash -c '
  set -euo pipefail
  # Only this NeXium process is interposed, never PulseAudio or the tools.
  env LD_PRELOAD="$MAP02_STAGE305_SHIM" \
    VH_STAGE305_ALSA_COUNTER_PATH="$MAP02_EVIDENCE/alsa-userspace-counter-PRIVATE.bin" \
    "$MAP02_HOST" "$MAP02_NRO" >"$MAP02_EVIDENCE/nexium-guest-stdout.log" 2>&1 &
  guest=$!
  trap "kill -KILL $guest 2>/dev/null || true" EXIT
  window=""
  for i in $(seq 1 35); do
    sleep 1
    window="$(xdotool search --onlyvisible --name NeXium 2>/dev/null | tail -n1 || true)"
    [[ -z "$window" ]] || break
    kill -0 "$guest" 2>/dev/null || exit 1
  done
  test -n "$window"
  sleep 4
  python3 -c "import time;print(time.monotonic_ns())" >"$MAP02_EVIDENCE/pulse-snapshot-during-start-ns.txt"
  pactl list sink-inputs >"$MAP02_EVIDENCE/pulse-sink-inputs-during.txt" || true
  python3 -c "import time;print(time.monotonic_ns())" >"$MAP02_EVIDENCE/pulse-snapshot-during-end-ns.txt"
  import -window "$window" "$MAP02_EVIDENCE/guest-before-input.png" || true
  timeout 3 xdotool windowfocus --sync "$window" || true
  python3 -c "import time;print(time.monotonic_ns())" >"$MAP02_EVIDENCE/guest-first-input-monotonic-ns.txt"
  for button in c x m; do
    timeout 3 xdotool keydown --window "$window" "$button"
    sleep 0.15
    timeout 3 xdotool keyup --window "$window" "$button"
    sleep 3
  done
  import -window "$window" "$MAP02_EVIDENCE/guest-prejoin.png" || true
  sleep 9
  import -window "$window" "$MAP02_EVIDENCE/guest-final.png"
  test -s "$MAP02_EVIDENCE/guest-final.png"
  sleep 5
  import -window "$window" "$MAP02_EVIDENCE/guest-late.png" || true
  python3 -c "import time;print(time.monotonic_ns())" >"$MAP02_EVIDENCE/pulse-snapshot-after-start-ns.txt"
  pactl list sink-inputs >"$MAP02_EVIDENCE/pulse-sink-inputs-after.txt" || true
  python3 -c "import time;print(time.monotonic_ns())" >"$MAP02_EVIDENCE/pulse-snapshot-after-end-ns.txt"
  python3 -c "import time;print(time.monotonic_ns())" >"$MAP02_EVIDENCE/guest-final-observation-monotonic-ns.txt"
  kill -INT "$guest" 2>/dev/null || true
  sleep 1
  kill -KILL "$guest" 2>/dev/null || true
  wait "$guest" 2>/dev/null || true
'
kill -TERM "$capture" 2>/dev/null || true
sleep 1
kill -KILL "$capture" 2>/dev/null || true
wait "$capture" 2>/dev/null || true
kill -TERM "$observer" 2>/dev/null || true
wait "$observer" 2>/dev/null || true
kill -TERM "$alsawatch" 2>/dev/null || true
wait "$alsawatch" 2>/dev/null || true
test -s "$MAP02_EVIDENCE/alsa-userspace-anonymous-atomic.csv"
test -s "$MAP02_EVIDENCE/pulse-sink-input-events-monotonic.csv"
trap - EXIT
test -s "$MAP02_EVIDENCE/virtual-pulse-48k-stereo-s16le.pcm"

# GUI FileLogger does NOT write to stdout. Its real configured location is
# nexium_common::paths::root()/logs, with the temp HOME above on this runner.
# Do not publish raw host logs; the separate audit will scan and sanitize them.
logroot="$HOME/.config/NeXium/logs"
if [[ ! -d "$logroot" ]]; then
  echo "ERROR: pinned NeXium GUI FileLogger directory is absent" >&2
  exit 1
fi
find "$logroot" -maxdepth 1 -type f -name 'nexium-*.log' -print -quit |
  grep -q 'nexium-'
