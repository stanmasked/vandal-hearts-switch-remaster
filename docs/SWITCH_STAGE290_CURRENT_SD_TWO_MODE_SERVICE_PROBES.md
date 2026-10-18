# Vandal Hearts Remake — Stage290: same-NRO current-SD idle/switch service probes

[Stage289 real NeXium verification 39087209978](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39087209978)
was successful, including the new original-guest-SD
`audio-audout-probe-*.csv` journal, checked together with the slow,
clock, scene and queue sources. From its immutable archived evidence:

| Measured quantity | Switching music | Idle music |
| --- | ---: | ---: |
| Total submitted calls | 1,941 | 2,221 |
| Existing 1-in-16 pre-submit service probes | 122 | 139 |
| Successful / failed probes | 122 / 0 | 139 / 0 |
| Pre-submit service count = 0 | 122 | 139 |
| Full-session >=40ms software calls | 33 | 47 |
| >=40ms calls that happened on a probed attempt | 6 | 3 |
| Scene-changing INPUTs | 10 | 0 |

These two captures share a SHA-256-verified NRO. Switching was
captured FIRST; idle followed. The sampling is every 16th attempt,
not random, and the unequal durations and host/emulator conditions
mean the slow-call rates are not a causal comparison.

## Stage290 independent current-run audit

`tools/analyze_nexium_idle_switch_service_probes.py` first requires
the independent original-current-guest-SD audit of switching probes
from Stage289 and the successful independent original-SD idle control.

**It also independently reopens the live idle guest SD files** for
scene startup, original queue, clock, latency, slow calls and the new
probe CSV. It demands byte-identical, immutable original-versus-copy
evidence, success receipts for each audout file, SHA-256 agreement
with the earlier idle report, exact per-call slow timestamp
reconciliation and zero genuine music-changing INPUTs.

It then validates all 1-in-16 attempt IDs, recorded timestamps,
pre-submit queue counts and slow-call sampled attempt subset for
BOTH modes and emits one explicitly nonrandomized two-mode
source-bound report. It refuses claim inflation into operating
system scheduler evidence, real DAC starvation or audible sound.

Run within the current NeXium workflow, after the existing idle
control gate:

```sh
python3 tools/analyze_nexium_idle_switch_service_probes.py \
  --switch-probe-report runtime-evidence/scene-soak/soak-audout-probe-verification.json \
  --switch-slow-report runtime-evidence/scene-soak/soak-audout-exact-slow-verification.json \
  --idle-report runtime-evidence/idle-control/idle-audout-verification.json \
  --idle-sd-root "$RUNNER_TEMP/vh-nexium-idle276-$GITHUB_RUN_ID" \
  --idle-evidence runtime-evidence/idle-control \
  --output runtime-evidence/idle-control/idle-switch-service-probe-comparison.json
```

Neither all-zero pre-submit queue-count observations nor the
proportion of probed attempts that were slow gives the actual queue
depth DURING blocking, audio scheduler callback timings, PCM-to-DAC
clock coupling or an audible glitch measurement. Stage290 cannot
supply those missing independent physical/scheduler witnesses.
