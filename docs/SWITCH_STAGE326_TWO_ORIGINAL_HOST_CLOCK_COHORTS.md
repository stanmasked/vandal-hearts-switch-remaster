# Vandal Hearts Remake — Stage326: two independent real NeXium host clock captures

Stage326 compares **two distinct original successful host-capture sources**;
it does not add guest instrumentation, change PCM, alter SPU, or infer DAC
output timing.

## Source cohorts

| Evidence | First original capture | Second original capture |
| --- | --- | --- |
| NeXium GitHub Actions run | [39166023593](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39166023593) | [39167324026](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39167324026) |
| Actual NRO + source host clocks | passed | passed |
| Strict original Stage304 | passed | passed |
| Strict original Stage305 | passed | passed |
| Post-Stage305 Stage325 unchanged-source recheck | not present in initial script | passed |
| Legacy Plus-control CSV SHA-256 | `cd3b6a7e42d531310ae930969c3612b63697c13b840726056bde701ceffe3f2d` | `ed94e89f82c9f705f1b04bf7851d9f22f01a41bafccec55e328a8e37e0b425ed` |
| Monotonic companion CSV SHA-256 | `302efc3b5c722f70956a0a6208c8e0b5e3e375aaa89fee73f6fff78b38f4d4c4` | `b6041ca452f4f0ab7d678587007ebb45b8e6ef5bc630478fc6612d75ede16d22` |

## Directly recorded host intervals

| Same host-control event pair | First run wall | Second run wall | Difference | First run monotonic | Second run monotonic | Difference |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `before_plus_down` → `after_plus_up` | 357 ms | 358 ms | +1 ms | 357,687,151 ns | 357,696,182 ns | +9,031 ns |
| `after_plus_up` → `control_sequence_end` | 4,270 ms | 4,286 ms | +16 ms | 4,269,790,190 ns | 4,285,779,743 ns | +15,989,553 ns |

For the same intervals the original buffered host PCM-file **size
increased**, respectively, by **70,128 / 827,164 bytes** in the first
capture and **69,144 / 832,548 bytes** in the second. These sizes are
buffered host file snapshots, not sample-exact evidence of what the
emulator's guest or a physical device played.

Both original captures are successful and have **positive monotonic host
intervals**. The different intervals reflect the two observed host
capture sessions, **not** a measured audio-call latency distribution.
Two samples do not establish any population reliability guarantee or
rule out the historical archived −347 ms wall-clock reversal.

## Independent Stage326 CI

`tools/compare_nexium_stage326_original_host_clocks.py` requires
unambiguous, nonsymlink original source files and strictly pinned
SHA-256 digests from both different capture archives. It then:

1. Recomputes each Stage325 result **from the original two host CSVs**.
2. Requires its exact reproduction of the original Stage325 receipt.
3. Replays the unchanged legacy Stage304 control CSV parser and checks
   event/byte/epoch identity against its original successful Stage304
   report, with proven source provenance flags.
4. Requires the original successful Stage305 report and scope flags.
5. Emits **only** control event names, source hashes, host buffered file
   size deltas and host wall/monotonic interval differences in a compact
   Stage326 JSON receipt; no original PCM or game data are uploaded
   in the **Stage326 output artifact**.

`tests/test_compare_nexium_stage326_original_host_clocks.py`
supplies 12 synthetic acceptance and rejection tests. The independent
GitHub Actions workflow
`.github/workflows/stage326-compare-original-host-clocks.yml`
downloads the **two actual NeXium artifacts**, not fabricated timing
inputs. It **passed** in the independent [Stage326 GitHub Actions
#39168578569](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39168578569):
all **12 synthetic tests** passed; both independently successful original
NeXium archives were downloaded; all four original CSV SHA-256 values
matched exactly; both Stage325 receipts were recomputed from the actual
CSV bytes; Stage304 original legacy event records and successful
Stage305 receipts were verified. The compact Stage326 artifact
`stage326-two-original-host-clock-cohorts` contains only hashes, event
names, buffered PCM file-length **deltas** and host clock **deltas**,
not actual PCM bytes or original copyrighted assets.

Stage326 replays Stage304's **legacy host controls**, not the entire
Stage299–305 PCM analysis chain on the second runner; the original
NeXium runs passed that full chain separately. Guest-to-host clock
alignment, real audio glitches, musical fidelity, Nintendo Switch
speakers and hardware timing remain **unverified**.
