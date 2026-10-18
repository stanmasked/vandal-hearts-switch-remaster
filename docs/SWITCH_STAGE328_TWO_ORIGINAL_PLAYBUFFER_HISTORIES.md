# Vandal Hearts Remake — Stage328: two genuine original PlayBuffer histories

## Scope

Stage328 advances from **host-clock evidence** to the original
guest-generated software `audoutPlayBuffer` history on two already
successful independent NeXium captures. It does not mix the guest clock
with host clocks or assume either measures physical DAC or speaker audio.

Sources:
- First successful NeXium [#39166023593](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39166023593), original `audio-playbuffer-history-000.csv` SHA-256 `72eb03e4508e2f8f7814f8b059aa5bfba69c71bbdac9f495ffab447d23fc345d`.
- Second successful NeXium [#39167324026](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39167324026), original SHA-256 `795c751e11449b0d0e0938031c540890eac23058e3a50c49ac2be9f622950a07`.

Original Stage320 last-success CSV SHA-256 values are
`fdc3ab8bcc5908ccb61c149ba185435fb5ab4a6409d33a43c02e7a179caf4aec`
(first) and
`2559938d1f86f8812405e2d3b1573398109450663188000bf1d58c8c965031e9`
(second), independently anchored to the exact successful source run logs.

## Original software-call observations

| Source-only guest measurement | First NeXium | Second NeXium |
| --- | ---: | ---: |
| Original retained successful normal calls | 16 | 16 |
| Previously successful normal calls before final | 15 | 15 |
| Last successful `audoutPlayBuffer` software bracket | 11,225,937 ns | 22,352,500 ns |
| Lower median of previous fifteen software brackets | 32,154,011 ns | 31,247,083 ns |
| Last minus earlier median | −20,928,074 ns | −8,894,583 ns |

The second last-call bracket was **11,126,563 ns longer** than the
first. The preceding baseline lower median differed by **−906,928 ns**
between captures. This is *run-to-run variation in retained guest
software-call brackets*; two samples do not establish an audible
glitch, lost samples, a population latency estimate or a direct
response-to-Plus causal timeline.

## Stage328 provenance and CI

The standalone `tools/compare_nexium_stage328_original_playbuffer_histories.py`
locates and uniquely requires four original files per archived
NeXium run:

- `audio-playbuffer-history-000.csv` — preserved byte-exact guest data
- `audio-last-playbuffer-000.csv` — last successful original guest service call
- `guest-last-playbuffer-stage320.json` — original source-bound last-call evidence
- `guest-playbuffer-history-stage322.json` — original bounded sixteen-call audit

It pins the two original history hashes **and independently pins both
original last-call CSV hashes**, checks original last-call source identity,
success and evidence-scope flags, then **re-runs** the pure Stage322
source verifier against each exact original history, requiring the
entire recomputed Stage322 receipt to match the original report
(except its three external original-file-preservation locator flags).
It requires a complete 16-call retained cohort, actual fifteen
previous successes and no fabricated earlier baseline. Source files
that are missing, ambiguous, symlinked, oversized, altered, or have
mismatched Stage320/322 witnesses are rejected.

Thirteen synthetic regression methods cover those acceptance and
rejection conditions, including a forged last-call SHA-256 pin. The independent GitHub Actions workflow
`.github/workflows/stage328-compare-real-playbuffer-histories.yml`
downloads the two **authentic NeXium artifacts** from their pinned
successful workflow IDs. A compact result contains only source hashes,
software-call durations/counts and bounded differences, never original
guest absolute timestamps or PCM, proprietary soundtrack or firmware.

**Verification boundary:** Stage320 was independently source-verified
inside the two original successful NeXium runs. The new independent
runner binds to original Stage320 CSV hashes and replays Stage322
against the original bytes, but does not re-run Stage307–320 from every
guest source file. It is not a physical-console audio test and cannot
verify original PS1 soundtrack fidelity or whether Plus caused an
audible dropout.

The Stage328 workflow's final status must be checked before claiming
that independent cross-run audit has passed.
