# Vandal Hearts Remake — Stage 275: compare same-NRO exact slow calls

**Experimental guest-emulator observations only. HARDWARE NOT TESTED.**

## Motivation

Stage 274 accepted the independent original-SD audit of exact
≥40 ms \`audoutPlayBuffer\` begin/end timestamps. Once two completed
runs with that same acceptance gate exist, compare them **without**
assuming that a slow API call, a scene INPUT or a host PCM marker
establishes an audible glitch.

\`tools/compare_nexium_verified_slow_runs.py\` accepts two to twelve
completed evidence ZIPs, each saved from GitHub Actions. Example:

\`\`\`bash
python3 tools/compare_nexium_verified_slow_runs.py \
  --archive nexium-run-one.zip \
  --archive nexium-run-two.zip \
  --output independent-guest-slow-runs.json
\`\`\`

It requires each ZIP to contain the **same-workflow Stage-274 accepted
original-SD verifier result**, the NRO preflight, clock origin, scene
optical CSV, latency CSV, exact slow-call CSV, export receipt and
their stored audit reports. It refuses missing source bytes, different
NRO SHA-256 values, duplicate workflow IDs, changed hashes, invalid
preflight, dropped slow-call samples, wrong attempt/timestamp
ordering and inconsistent 40/50 ms bins. Exact scene INPUT
before/overlap/after comparisons are recomputed independently and
must match the stored stage-274 verdict. Unverified earlier ZIPs
cannot be silently promoted to original-SD acceptance.

The comparison only examines *archived copies*. It cannot reopen the
runner's ephemeral original guest SD or authenticate a downloaded ZIP
against GitHub's server on its own. The original-SD status is based
on the prior independently successful workflow job; the JSON report
plainly retains that scope. ZIP data by itself is not a
cryptographic signature of actual emulation.

The test suite uses synthetic valid and tampered ZIPs, never labels
them real emulator evidence, and rejects mismatched NROs, duplicate
runs, swapped stage-274 reports and changed individual source files.

## Two fully accepted same-NRO NeXium observations

| Measurement | NeXium [39072903722](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39072903722) | NeXium [39073836066](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39073836066) |
| --- | ---: | ---: |
| Original isolated guest SD Stage-274 auditor | PASS | PASS |
| Individual audout calls | 1,942 | 1,990 |
| Audout second windows | 53 | 53 |
| 40–<50 ms calls | 20 | 13 |
| ≥50 ms calls | 2 | 0 |
| Maximum API call (μs) | 53,503 | 45,942 |
| Missing/overflowed exact slow-call records | 0 | 0 |
| Ten guest scene INPUT events | PASS | PASS |

**Both runs used NRO SHA-256
\`4be7635609589952363d3255e81537343a5893bff3611ecd30df48d39d6f35cb\`.**

The fully audited Stage-274 report in run 39072903722 identified
20 calls 40–<50 ms and two ≥50 ms calls. Calls whose **start** was
±500 ms from a scene INPUT were observed around scene serials
1, 9 and 10, and all four such API calls completed **before** the
respective INPUT. Neither ≥50 ms call began in any scene-INPUT
±500 ms window.

Run 39073836066 independently captured 13 calls ≥40 ms, none
≥50 ms. The slow calls selected by the same ±500 ms rule
fell near INPUT serials **1, 6, 8, 9**: one began **280.778 ms after**
serial 1; three calls **spanned** the exact INPUT instant at
serials 6, 8 and 9 (began 0.043, 18.297 and 24.386 ms before it).
Even for straddling, timestamps establish temporal overlap only;
they cannot prove that the scene switch produced the blocking call.
The longer ≥50 ms calls disappeared in this run, so a
fixed-scene association is not reproducible.

These observations do **not** verify device DAC queue depth,
audible underruns, actual input-to-speaker latency, physical Switch
performance or source soundtrack fidelity.

## Validation status

- Stage 274: **accepted**, both source GitHub Actions NeXium runs
  with exact original-SD auditor passed.
- Offline cross-run comparison: byte-rechecked on both archived
  evidence files, matching the original-SD verifier receipts.
- Reusable Stage-275 cross-run comparison tool and synthetic negative
  tests: **host CI passed** in [39075155491](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39075155491), and the pinned NeXium
  runtime passed in [39075005998](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39075005998).
- Independent real-archive comparison workflow: **passed** in
  [39075889640](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39075889640), which downloaded source artifacts
  from GitHub Actions runs 39072903722 and 39073836066, rechecked
  hashes and archived its JSON verdict. This workflow now accepts
  four actual source runs, with new four-run CI acceptance tracked separately.


## Four same-binary original-SD accepted observations

Two additional workflows independently completed the full exact
original-SD slow-call gate:

- [39074970372](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39074970372)
- [39075005998](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39075005998)

All four releases had **identical NRO SHA-256**
\`4be7635609589952363d3255e81537343a5893bff3611ecd30df48d39d6f35cb\`.
An additional offline archival audit rechecked source copied CSVs,
call timestamps, queue/latency aggregates and earlier original-SD
verdicts for the four successful runs:

| NeXium run | Total audout calls | Calls ≥40 ms | Calls ≥50 ms | Exact slow events lost |
| --- | ---: | ---: | ---: | ---: |
| 39072903722 | 1,942 | 22 | 2 | 0 |
| 39073836066 | 1,990 | 13 | 0 | 0 |
| 39074970372 | 1,920 | 28 | 4 | 0 |
| 39075005998 | 1,963 | 23 | 4 | 0 |
| **Combined observations** | **7,815** | **86** | **10** | **0** |

At least one ≥50 ms call began within ±500 ms of scene INPUTs
in the third and fourth runs, at serials {2,4} and {2,9}
respectively. The first two runs had no ≥50 ms call beginning
within that window around any scene INPUT. Differences between
NeXium runs must not be treated as proof of a cause, a deterministic
audio-quality threshold, a particular scene defect, a device underrun
or a Nintendo Switch hardware result.

The dedicated
[\`.github/workflows/nexium-slow-runs-comparison.yml\`](../.github/workflows/nexium-slow-runs-comparison.yml)
now obtains four prior completed successful runs directly from
GitHub's own Actions artifacts (read-only \`actions:read\` token),
checks distinct run IDs, re-packages source bytes without modifying
them, runs the reusable comparer and preserves the result. Its
report states clearly that the original transient guest SD cannot
be reopened during retrospective comparison; the original-SD status
comes from each source workflow's previously completed audit.
The first **two-run** comparison in Actions 39075889640 was
successful. **Acceptance of the expanded four-run GitHub Actions
comparison is separate** until that newer workflow finishes.
