#!/usr/bin/env bash
# Stage 268: five A/B music cycles in a fresh pinned guest NRO.
# No generated screenshot/PCM can satisfy the subsequent CI audit.
set -euo pipefail
: "${NEXIUM_BIN:?Nexium executable required}"
: "${RUNNER_TEMP:?runner temporary directory required}"
output="${1:-runtime-evidence/scene-soak}"
if [[ -e "$output/soak-events.csv" || -e "$output/soak-optical-trace.png" ]]; then
  echo "Refuse overwrite of an existing scene-soak capture" >&2
  exit 2
fi
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
export NEXIUM_DATA_ROOT="${RUNNER_TEMP}/vh-nexium-stage268-${GITHUB_RUN_ID:-local}"
export SOAK_SD_DIR="$NEXIUM_DATA_ROOT/sdmc/switch/vandal-hearts-remake"
if [[ -e "$NEXIUM_DATA_ROOT" ]]; then
  echo "Refuse to reuse an existing isolated NeXium data directory" >&2
  exit 2
fi
mkdir -p "$SOAK_SD_DIR"
printf '%s\n' "$NEXIUM_DATA_ROOT" > "$output/soak-sd-root.txt"
export SOAK_PCM="$output/soak-monitor-s16le-48k.pcm"
export SOAK_EVENTS="$output/soak-events.csv"
export SOAK_GUEST_LOG="$output/soak-nexium-guest.log"
export SOAK_DIR="$output"
export SOAK_NRO="nros/vandal-hearts-prototype.nro"
: > "$SOAK_PCM"
printf 'scene,serial,pcm_bytes,epoch_ms\n' > "$SOAK_EVENTS"
parec --device=vh_nexium_capture.monitor --rate=48000 \
  --channels=2 --format=s16le --raw > "$SOAK_PCM" \
  2> "$output/soak-parec.log" &
recorder=$!
cleanup() {
  kill -INT "$recorder" 2>/dev/null || true
  wait "$recorder" 2>/dev/null || true
}
trap cleanup EXIT
sleep 1
timeout --kill-after=5s 110s xvfb-run -a -s '-screen 0 1280x720x24' bash -c '
  set -euo pipefail
  "$NEXIUM_BIN" "$SOAK_NRO" >"$SOAK_GUEST_LOG" 2>&1 &
  guest=$!
  trap '\''kill -INT "$guest" 2>/dev/null || true; sleep 1; kill -KILL "$guest" 2>/dev/null || true; wait "$guest" 2>/dev/null || true'\'' EXIT
  window=""
  for i in $(seq 1 25); do
    sleep 1
    window="$(xdotool search --onlyvisible --name NeXium 2>/dev/null | tail -n 1 || true)"
    if [ -n "$window" ]; then break; fi
    kill -0 "$guest"
  done
  test -n "$window"
  xdotool windowfocus --sync "$window"
  snapshot() {
    state="$1"
    number="$2"
    bytes="$(stat -c %s "$SOAK_PCM")"
    bytes="$((bytes / 4 * 4))"
    milliseconds="$(date +%s%3N)"
    printf "%s,%s,%s,%s\n" "$state" "$number" "$bytes" "$milliseconds" >> "$SOAK_EVENTS"
    sleep 0.35
    printf -v image_name "soak-scene-%02d.png" "$number"
    import -window "$window" "$SOAK_DIR/$image_name"
    test -s "$SOAK_DIR/$image_name"
  }
  key_press() {
    xdotool keydown --window "$window" "$1"
    sleep 0.18
    xdotool keyup --window "$window" "$1"
    sleep 0.22
  }
  sleep 1.5
  snapshot field_initial 0
  sleep 3.5
  for i in $(seq 1 10); do
    if (( i % 2 == 1 )); then
      key_press c
      state="focus_$i"
    else
      key_press x
      state="field_$i"
    fi
    snapshot "$state" "$i"
    sleep 3.7
  done
  # A one-shot host Plus press may last LESS than the guest HID poll
  # interval and be missed. Hold the real Plus key across many frames;
  # the original optical/SD/PCM auditors still reject missing proof.
  xdotool keydown --window "$window" v
  sleep 0.4
  xdotool keydown --window "$window" m
  sleep 0.25
  xdotool keyup --window "$window" m
  sleep 1.1
  import -window "$window" "$SOAK_DIR/soak-optical-trace.png"
  test -s "$SOAK_DIR/soak-optical-trace.png"
  xdotool keyup --window "$window" v || true
  sleep 3
' > "$output/soak-runner.log" 2>&1
cleanup
trap - EXIT
find "$SOAK_SD_DIR" -maxdepth 1 -type f -name 'audio-scene-trace-*.csv' \
  -print | sort > "$output/soak-sd-locations.txt"
# Store a clearly UNVERIFIED original guest SD candidate even when
# the strict optical/PCM audit fails. The auditor still independently
# rereads the original guest SD file and never treats this copy as proof.
mapfile -t captures < "$output/soak-sd-locations.txt"
if (( ${#captures[@]} == 1 )) && [[ ! -e "$output/soak-sd-unverified.csv" ]]; then
  cp --no-clobber -- "${captures[0]}" "$output/soak-sd-unverified.csv"
fi

# Independent guest-only audout evidence, not an optical trace.
# Capture the original SD candidate without asserting validity here.
find "$SOAK_SD_DIR" -maxdepth 1 -type f -name 'audio-audout-queue-*.csv' \
  -print | sort > "$output/soak-audout-sd-locations.txt"
mapfile -t queue_captures < "$output/soak-audout-sd-locations.txt"
if (( ${#queue_captures[@]} == 1 )) && \
   [[ ! -e "$output/soak-audout-sd-unverified.csv" ]]; then
  cp --no-clobber -- "${queue_captures[0]}" \
    "$output/soak-audout-sd-unverified.csv"
fi

# Distinct failure witness for an SD export that never published CSV.
# Never replace a missing successful CSV with this status receipt.
if [[ -f "$SOAK_SD_DIR/audio-audout-export-failure.txt" ]]; then
  cp --no-clobber -- "$SOAK_SD_DIR/audio-audout-export-failure.txt" \
    "$output/soak-audout-export-failure.txt"
fi

# Always preserve the producer's own post-join export result; positive
# and negative verdicts are kept distinct from the actual CSV bytes.
if [[ -f "$SOAK_SD_DIR/audio-audout-export-result.txt" &&
      ! -L "$SOAK_SD_DIR/audio-audout-export-result.txt" ]]; then
  cp --no-clobber -- "$SOAK_SD_DIR/audio-audout-export-result.txt" \
    "$output/soak-audout-export-result.txt"
fi
# Stage 272: retain independent per-CALL latency histogram producer
# evidence. Neither an old queue CSV nor a status receipt substitutes.
find "$SOAK_SD_DIR" -maxdepth 1 -type f -name 'audio-audout-latency-*.csv' \
  -print | sort > "$output/soak-audout-latency-locations.txt"
mapfile -t latency_captures < "$output/soak-audout-latency-locations.txt"
if (( ${#latency_captures[@]} == 1 )) && \
   [[ ! -e "$output/soak-audout-latency-unverified.csv" ]]; then
  cp --no-clobber -- "${latency_captures[0]}" \
    "$output/soak-audout-latency-unverified.csv"
fi
if [[ -f "$SOAK_SD_DIR/audio-audout-latency-export-result.txt" &&
      ! -L "$SOAK_SD_DIR/audio-audout-latency-export-result.txt" ]]; then
  cp --no-clobber -- "$SOAK_SD_DIR/audio-audout-latency-export-result.txt" \
    "$output/soak-audout-latency-export-result.txt"
fi

# Names and sizes are diagnostic only. They never satisfy the audit.
find "$SOAK_SD_DIR" -maxdepth 1 -type f \
  -printf '%f,%s\n' | LC_ALL=C sort > "$output/soak-sd-directory-inventory.csv"
