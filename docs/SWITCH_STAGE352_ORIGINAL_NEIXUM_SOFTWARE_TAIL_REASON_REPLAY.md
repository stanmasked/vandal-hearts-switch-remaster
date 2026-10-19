# Vandal Hearts Remake — Stage352 independent replay of original successful exit-tail source

## Grounded original NeXium observation

Real [NeXium CI #39308380160](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39308380160) **completed successfully**, including the full source-verification step for the first actual Stage351 exit-tail classification captured from the compiled game NRO.

Within that same run the **original guest software sources** reported:

| Witness (same NeXium run) | Observed software-only value | Original SHA-256 |
|---|---|---|
| Stage313 bounded exit tail | attempted; exact release confirmed | `761810a3ef96e551beebebc92e7f4ea369379b38914a33ef515cc5795bc79fb8` |
| Stage348 exact PCM descriptor ownership | acquired **1441** / released **1441** / abandoned **0** | `bfe73361a817cba4155fb103088e4da4b9511c6860484a62c9005e4e9555918a` |
| Stage351 exit-tail branch | code **7** = `return_confirmed` | `1e49059bf105690b45fd63b41923726fde330f9c330b5b0fd62f914084a91b58` |

The successful original guest Stage351 check was integrated into the full run, not merely a host-generated model. The specific original guest raw sources and prior original JSON receipts are archived in the workflow's `nexium-runtime-evidence` artifact. This was the branch from before subsequent extra Stage351 original ancestor-link hardening.

## Stage352 independent replay from persisted artifacts

`tools/audit_nexium_stage352_three_original_tail_sources.py` reopens exactly **three original guest CSV files** and four prior-stage JSON receipts. It pins the original SHA-256 values above, audits canonical rows, independently revalidates Stage313 and Stage348 originals and their receipts, and re-decodes the original Stage351 eight-row reason. It rejects forged flags, source/receipt mismatches, symlinked files/directories and duplicate or missing source files; it never trusts the previous successful CI status as a substitute for source bytes.

`tests/test_audit_nexium_stage352_three_original_tail_sources.py` contains 15 positive and negative cases, including a *synthetically consistent* failed-return branch (code 4 and one abandoned session). Such synthetic branches are protection tests, **never observations of the older actual NeXium failure**.

The [dedicated Stage352 workflow](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/workflows/stage352-original-tail-reason-replay.yml) independently downloads the completed NeXium #39308380160 artifact and refuses any conclusion unless the three SHA-pinned original files and receipts all agree on **code 7, 1441/1441/0**. The workflow produces only a compact JSON outcome and never republishes copyrighted PCM samples, banks or original music. Report the independent replay as complete **only after both jobs pass**.

## Strict interpretation

Earlier real Stage350 source pairs included a failed tail return with one abandoned descriptor, but those older captures **preceded** the Stage351 0–7 reason classifier. Therefore this successful run does **not retroactively tell us** whether their failure was `audoutAppendAudioOutBuffer`, `audoutWaitPlayFinish`, an empty wait or a mismatched descriptor. A new true failed-return source captured under Stage351 is required to attribute its distinct branch.

A returned buffer proves software ownership release, not queue drain, audible continuity, DAC/speaker playback, original PS1 sound fidelity or hardware Nintendo Switch performance. No gameplay, PS1 resource, audio service call, SPU, PCM producer or existing Stage313/348 data format was changed by Stage352.
