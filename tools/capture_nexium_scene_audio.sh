#!/usr/bin/env bash
# Two A/B focus transitions while capturing a PulseAudio virtual-sink monitor.
# Expects the isolated PulseAudio setup from emulator-smoke.yml earlier in job.
set -euo pipefail
: "${NEXIUM_BIN:?NeXium executable required}"
: "${RUNNER_TEMP:?runner temporary directory required}"
output="${1:-runtime-evidence}"
# Existing capture remains identical by default. The optional experimental
# mode must use a different NRO and SD root to avoid evidence crossover.
: "${SCENE_NRO:=nros/vandal-hearts-prototype.nro}"
: "${SCENE_CAPTURE_TAG:=}"
case "$SCENE_CAPTURE_TAG" in
  ""|wet-tail) ;;
  *) echo "Invalid experimental scene capture tag" >&2; exit 2 ;;
esac
test -s "$SCENE_NRO"
export SCENE_NRO
mkdir -p "$output"
export XDG_RUNTIME_DIR="$RUNNER_TEMP/vh-pulse-runtime"
export PULSE_SERVER="unix:$XDG_RUNTIME_DIR/pulse/native"
export ALSA_CONFIG_PATH="$RUNNER_TEMP/vh-asound.conf"
export SDL_AUDIODRIVER=pulse
icd="$(find /usr/share/vulkan/icd.d -maxdepth 1 -name 'lvp_icd*.json' -print -quit)"
test -n "$icd"
export VK_ICD_FILENAMES="$icd"
pactl info >/dev/null
pactl set-default-sink vh_nexium_capture
# An isolated, runner-local emulated SD root is authoritative for this
# session. It cannot pick up traces from previous CI runs or user data.
# NeXium resolves guest sdmc:/ under NEXIUM_DATA_ROOT/sdmc.
export NEXIUM_DATA_ROOT="${RUNNER_TEMP}/vh-nexium-stage266-${GITHUB_RUN_ID:-local}${SCENE_CAPTURE_TAG:+-$SCENE_CAPTURE_TAG}"
export SCENE_SD_DIR="$NEXIUM_DATA_ROOT/sdmc/switch/vandal-hearts-remake"
mkdir -p "$SCENE_SD_DIR"
printf '%s\n' "$NEXIUM_DATA_ROOT" > "$output/guest-sd-root.txt"
export SCENE_PCM="$output/nexium-scenes-s16le-48k.pcm"
export SCENE_EVENTS="$output/scene-events.csv"
export SCENE_LOG="$output/nexium-scenes-run.log"
export SCENE_DIR="$output"
: > "$SCENE_PCM"
printf 'scene,pcm_bytes,epoch_ms\n' > "$SCENE_EVENTS"
parec --device=vh_nexium_capture.monitor --rate=48000 \
  --channels=2 --format=s16le --raw > "$SCENE_PCM" \
  2> "$output/scene-parec.log" &
recorder=$!
cleanup() {
  kill -INT "$recorder" 2>/dev/null || true
  wait "$recorder" 2>/dev/null || true
}
trap cleanup EXIT
sleep 1
timeout --kill-after=5s 65s xvfb-run -a -s '-screen 0 1280x720x24' bash -c '
  set -euo pipefail
  "$NEXIUM_BIN" "$SCENE_NRO" >"$SCENE_LOG" 2>&1 &
  guest=$!
  trap '\''kill -INT "$guest" 2>/dev/null || true; sleep 1; kill -KILL "$guest" 2>/dev/null || true; wait "$guest" 2>/dev/null || true'\'' EXIT
  window=""
  for i in $(seq 1 20); do
    sleep 1
    window="$(xdotool search --onlyvisible --name NeXium 2>/dev/null | tail -n 1 || true)"
    if [ -n "$window" ]; then break; fi
    kill -0 "$guest"
  done
  test -n "$window"
  xdotool windowfocus --sync "$window"
  snapshot() {
    label="$1"
    bytes="$(stat -c %s "$SCENE_PCM")"
    bytes="$((bytes / 4 * 4))"
    millis="$(date +%s%3N)"
    printf "%s,%s,%s\n" "$label" "$bytes" "$millis" >> "$SCENE_EVENTS"
    sleep 0.5
    import -window "$window" "$SCENE_DIR/scene-$label.png"
    test -s "$SCENE_DIR/scene-$label.png"
  }
  key_press() {
    xdotool keydown --window "$window" "$1"
    sleep 0.15
    xdotool keyup --window "$window" "$1"
    sleep 0.2
  }
  snapshot field_initial
  sleep 6
  key_press c; snapshot focus_1
  sleep 7
  key_press x; snapshot field_1
  sleep 7
  key_press c; snapshot focus_2
  sleep 7
  key_press x; snapshot field_2
  sleep 6
  # Optical diagnostic shutdown: hold controller X (NeXium V),
  # press Plus (NeXium M), then screenshot the post-join framebuffer.
  # A normal Plus alone preserves immediate exit semantics. The
  # framebuffer receipt must be decoded from its actual CRC-protected
  # pixels; a generated fixture is never an acceptable CI substitute.
  # A one-shot host Plus press may last LESS than the guest HID poll
  # interval and be missed. Hold the real Plus key across many frames;
  # the original optical/SD/PCM auditors still reject missing proof.
  xdotool keydown --window "$window" v
  sleep 0.4
  xdotool keydown --window "$window" m
  sleep 0.25
  xdotool keyup --window "$window" m
  sleep 1.1
  import -window "$window" "$SCENE_DIR/scene-optical-trace.png"
  test -s "$SCENE_DIR/scene-optical-trace.png"
  xdotool keyup --window "$window" v || true
  sleep 3
' > "$output/scene-runner.log" 2>&1
cleanup
trap - EXIT
python3 tools/analyze_nexium_scene_audio.py "$SCENE_PCM" "$SCENE_EVENTS" \
  --output "$output/scene-audio-report.json"
python3 -m json.tool "$output/scene-audio-report.json" > /dev/null
# Keep the original guest-exported CSV in the isolated filesystem until
# the workflow inspects it. Copy a single unmodified file into evidence;
# zero/multiple matches must not silently become a passing guest trace.
find "$SCENE_SD_DIR" -maxdepth 1 -type f -name 'audio-scene-trace-*.csv' \
  -print | sort > "$output/guest-sd-csv-locations.txt"
