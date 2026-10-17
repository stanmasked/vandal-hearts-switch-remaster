# Vandal Hearts Remake — Stage 277: Seven original-SD-audited audio-control pairs

**Accepted in [GitHub Actions 39079521757](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39079521757).**  
**NeXium guest software only; real Nintendo Switch hardware and audible underruns NOT tested.**

## Experimental design

After [Stage 276](SWITCH_STAGE276_NEXIUM_IDLE_AUDOUT_BASELINE.md)
confirmed the first ≥50-second **no-music-switch baseline**, we
collected seven separate GitHub Actions NeXium sessions, each containing
a normal run with ten A/B switches and a distinct isolated guest-SD
run where no A/B inputs were sent. Both halves of every pair execute
the **identical NRO SHA-256**:

`4be7635609589952363d3255e81537343a5893bff3611ecd30df48d39d6f35cb`

For each of seven runs, the live CI previously verified the **original**
guest SD clock origin, exact ≥40 ms audout timestamps, per-second
duration bands, scene trace, producer receipts and individual
`audoutPlayBuffer` counts. This is **observational control data**,
not a randomized or causal experiment.

## Seven full-pair archived runs

| NeXium workflow | Idle audout calls | Switch audout calls | Idle ≥40 ms | Switch ≥40 ms | Idle ≥50 ms | Switch ≥50 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [39077499594](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39077499594) | 2,287 | 1,981 | 33 | 29 | 5 | 1 |
| [39077898370](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39077898370) | 2,222 | 1,949 | 25 | 33 | 3 | 2 |
| [39078007443](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39078007443) | 2,233 | 1,925 | 21 | 22 | 0 | 1 |
| [39078024366](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39078024366) | 2,176 | 1,861 | 41 | 33 | 4 | 5 |
| [39078053051](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39078053051) | 2,227 | 1,944 | 26 | 32 | 1 | 4 |
| [39078369183](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39078369183) | 2,250 | 1,952 | 41 | 24 | 3 | 0 |
| [39078393956](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39078393956) | 2,250 | 1,951 | 28 | 35 | 3 | 2 |
| **Total** | **15,645** | **13,563** | **215** | **208** | **19** | **15** |

The short and long slow-call classifications refer strictly to
**blocking guest `audoutPlayBuffer` call duration**, not PCM underruns
or timestamps of sound emerging from a speaker.

Normalized aggregate rates, per 1,000 guest audout attempts:

| Call duration | No A/B inputs | Ten A/B scene switches |
| --- | ---: | ---: |
| ≥40 ms | **13.742** | **15.336** |
| ≥50 ms | **1.214** | **1.106** |

For ≥40 ms durations, the switching rate is higher in **5/7 pairs**;
for ≥50 ms durations, switching is higher in **3/7 pairs**. This
inconsistency, combined with nonrandomized running order, unequal
session lengths (idle ~61 seconds, switching ~53), emulator CPU/host
scheduling and small ≥50 ms samples, **does not establish a causal
scene-switch effect**.

## Stage 277 independent archive reauditor

`tools/compare_nexium_idle_switch_pairs.py` takes two to twelve
independently audited paired NeXium archive ZIPs:

```bash
python3 tools/compare_nexium_idle_switch_pairs.py \
  --archive paired-run-1.zip \
  --archive paired-run-2.zip \
  --output verified-pairs.json
```

It **fails closed** on duplicate run identifiers, different NRO
hashes, missing or reordered original guest scene and slow-call
records, unrecognized or modified writer receipts, invalid original
SD SHA-256 in previously stored verdicts, inconsistent absolute
audio-clock origin, mismatched per-second latency buckets, incorrectly
paired A/B counters, or forged reports.

On each ZIP it also invokes the independent Stage-275 switching
auditor, rechecks the **actual archived copies** of idle
scene/queue/latency/clock/slow CSV bytes and requires all previous
Stage-276 original SD live audit results. The use of copied bytes in
this retrospective review is explicitly distinguished from actually
reopening the now-deleted original runner SD.

The separate
[Actions workflow `nexium-idle-switch-repeatability.yml`](../.github/workflows/nexium-idle-switch-repeatability.yml)
requires that all seven designated prior workflow runs completed
successfully in this exact GitHub repository and branch, downloads
their real artifacts through GitHub, repackages them without modifying
the source CSV bytes, and generates an independent comparison JSON.

**GitHub Actions run 39079521757: SUCCESS.** Its seven-pair verdict,
repacked archive hashes and source workflow IDs are retained in the
`nexium-verified-seven-idle-switch-pairs` artifact.

The negative unit tests
`tests/test_compare_nexium_idle_switch_pairs.py` use strictly
**synthetic guest evidence** to simulate missing source data, paired
summary tampering, identical-original/copy forged scene INPUT, wrong
receipts, different NROs and duplicate runs.

## Results boundary

This experiment supports a narrower positive conclusion: **slow
guest audout API calls also occur when no music changes**. It
does *not* show that game audio is uninterrupted, playable on
physical hardware, authentic to retail media or immune to timing
problems at music boundaries. It neither measures the physical
Switch's speakers nor records a matched host/guest DAC clock.

The next technically useful test would sample more independent
paired NeXium runs with controlled ordering, rather than adding
more metadata around the same limited set.
