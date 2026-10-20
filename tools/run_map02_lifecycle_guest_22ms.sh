#!/usr/bin/env bash
# Opt-in ROM-free MAP02 guest positive control on a verified NeXium ELF.
set -euo pipefail
: "$MAP02_HOST" "$MAP02_NRO" "$MAP02_EVIDENCE" "$RUNNER_TEMP"
[[ "$MAP02_HOST" = /* && "$MAP02_NRO" = /* && "$MAP02_EVIDENCE" = /* ]]
[[ -x "$MAP02_HOST" && -s "$MAP02_NRO" ]]
mkdir -p "$MAP02_EVIDENCE"
export XDG_RUNTIME_DIR="$RUNNER_TEMP/vh-map02-stage290-runtime"
mkdir -p "$XDG_RUNTIME_DIR"; chmod 700 "$XDG_RUNTIME_DIR"
export HOME="$RUNNER_TEMP/vh-map02-stage290-home"
mkdir -p "$HOME"
pulseaudio --daemonize=yes --exit-idle-time=-1 \
  --log-target=file:"$MAP02_EVIDENCE/pulseaudio.log"
export PULSE_SERVER="unix:$XDG_RUNTIME_DIR/pulse/native"
pactl load-module module-null-sink sink_name=vh_map02_stage290 \
  rate=48000 channels=2 >"$MAP02_EVIDENCE/pulse-module-id.txt"
pactl set-default-sink vh_map02_stage290
pactl list short sources >"$MAP02_EVIDENCE/pulse-sources.txt"
grep -F vh_map02_stage290.monitor "$MAP02_EVIDENCE/pulse-sources.txt"
printf 'pcm.!default { type pulse }\nctl.!default { type pulse }\n' >"$RUNNER_TEMP/stage290-alsa.conf"
export ALSA_CONFIG_PATH="$RUNNER_TEMP/stage290-alsa.conf"
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
parec --device=vh_map02_stage290.monitor --format=s16le \
  --rate=48000 --channels=2 \
  >"$MAP02_EVIDENCE/virtual-pulse-48k-stereo-s16le.pcm" \
  2>"$MAP02_EVIDENCE/parec.log" &
capture=$!
trap 'kill -KILL "$capture" 2>/dev/null || true' EXIT
sleep 1; kill -0 "$capture"
export PULSE_LATENCY_MSEC=22
export VH_MAP02_CPAL_TRACE_PATH="$MAP02_EVIDENCE/host-cpal-audioout-timeline.csv"
timeout --kill-after=5s 75s xvfb-run -a -s "-screen 0 1280x720x24" bash -c '
  set -euo pipefail
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
  pactl list sink-inputs >"$MAP02_EVIDENCE/pulse-sink-inputs-during.txt" || true
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
  pactl list sink-inputs >"$MAP02_EVIDENCE/pulse-sink-inputs-after.txt" || true
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
trap - EXIT
test -s "$MAP02_EVIDENCE/virtual-pulse-48k-stereo-s16le.pcm"
