# Vandal Hearts Remake — Stage324: independent second original 16-call PlayBuffer cohort

## Confirmed starting point

Original Stage322 NeXium capture [39159226320](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39159226320) succeeded, and an **independent** Stage323 runner [39160645756](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39160645756) successfully replayed the authentic original guest CSV/optical CRC sources and all 16 source-adversarial tests. In that ONE original capture:

- Final normal `audoutPlayBuffer` software-call duration: **18,385,781 ns**
- Lower median of preceding 15 authentic successful calls: **31,775,052 ns**
- Final-minus-own-prior median: **−13,389,271 ns**
- Prior shorter / tied / longer normal calls: **3 / 0 / 12**
- Final call rank among all 16 durations ascending: **4th shortest**
- Post-main-stop portion inside final software call: **4,609,427 ns**

This is a single original **guest software** call window, not physical playback or a population-level latency result.

## New second independently executed original capture

A separate branch commit
[584a9909](https://github.com/stanmasked/vandal-hearts-switch-remaster/commit/584a99096a23ffb7f4b1dadd85310e5148ee1754)
changes **only a GitHub workflow comment** to trigger a new standalone
[NeXium run 39162251380](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39162251380).
It uses exactly the same executable/audio instrumentation as Stage323;
no changes to music, game logic, SPU, buffering or output pacing.

The new original run must **successfully complete** all the same
runtime evidence stages before being accepted. A partial or
failed archive is never treated as a full independent capture.

## Stage324 independent source comparison

The standalone
`.github/workflows/stage324-two-original-playbuffer-windows.yml`
is run on **another** GitHub Actions runner. It:

1. Requires both exact original NeXium source run IDs **39159226320**
   and **39162251380** to have completed **successfully**.
2. Downloads each distinct original `nexium-runtime-evidence` artifact.
3. Independently replays the **full Stage323 byte-original source chain
   separately for each run**: original guest exit CSV, original last
   normal PCM page-return CSV, original worker-stop CSV, original final
   service-call CSV, original last16 service-call history CSV and
   original CRC-protected optical framebuffer PNG; all Stage307–Stage322
   source SHA/receipt constraints remain strict.
4. Requires distinct real original workflow IDs and distinct guest
   history, exit and optical SHA-256 digests to prevent a duplicated
   capture from being mistaken for a second independent execution.
5. Computes, for each capture on its **own guest software clock**,
   final call duration, preceding lower median, final-minus-own-median,
   and rank among up to 16 actual original successful call records.
6. Reports whether **both** final calls lie below each respective
   same-run prior median. A disagreement is a valid outcome; it is
   never hidden or declared a CI failure.

New report (no raw music/audio data published):

`independent-stage324-comparison/dual-playbuffer-windows-stage324.json`

## Source attack tests and strict limits

Fifteen synthetic unit tests reject duplicate original workflows,
duplicate optical/history/exit source hashes, forged prior-call
medians and ranks, missing source-backed baselines, missing/invalid
capture identity, guest-to-host PCM overclaims and invalid success
counts. The tests run in the main Host SPU suite and the separate
Stage324 original-archive workflow.

**Two captures are still not a representative latency distribution.**
A guest service call's begin/end/lease-return software clock does
**not** measure the last audible PCM sample, hardware DAC, speaker
output, original retail PlayStation soundtrack or the cause of any
Plus-related acoustic issue.
