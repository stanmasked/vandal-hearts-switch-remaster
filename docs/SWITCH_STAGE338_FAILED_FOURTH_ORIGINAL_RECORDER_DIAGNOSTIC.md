# Vandal Hearts Remake — Stage338: diagnose rejected original fourth recorder stop source

The fourth real [NeXium run #39177437951](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39177437951) **did not pass**. The NRO build and original guest audio/host-clock capture were performed; earlier Stage299–302 analyses succeeded, but the unchanged strict Stage303 recorder SIGINT lifecycle verifier returned `STAGE303_RECORDER_STOP_NOT_VERIFIED` before Stage304/305 and Stage334/336 could run. The original `nexium-runtime-evidence` archive was still uploaded using `if: always()`. This capture **must not** be counted as an independently verified fourth success.

`tools/audit_nexium_stage338_failed_stage303_diagnostic.py` is a **separate read-only diagnostic**, not a replacement for Stage303 or an alternate pass policy. An independent GitHub Actions workflow downloads the exact failed run #39177437951 archive, replays Stage299–302 from its original PCM bytes, source-snapshot receipts and event records, then checks original `scene-recorder-stop.csv` snapshots before repeating strict Stage303. The diagnostic reports only an allowlisted *first failing gate*, signed byte-size discrepancy if present and source SHA digests, and never saves PCM, absolute guest timestamps, host clock epochs or soundtrack material in its compact report.

Fifteen synthetic tests cover canonical lifecycle, after-wait file-size over/under-run, wrong Stage302 frame count or source SHA, rejected recorder-stop signal, changed event order, and privacy/no hardware-claim limits. Successful completion of the diagnostic workflow **does not mean Stage303, Stage304, Stage305, Stage334 or Stage336 passed**.

Once the exact gate is identified, fix the data capture lifecycle only if the source evidence demonstrates a production-side defect. Do **not** relax the strict recorder source audit or merge the rejected fourth capture into Stage335/337 successful cohorts. Existing first three genuine NeXium sources remain unchanged.

## Stage338 result and exact reject-gate refinement

[Independent diagnostic #39178525841](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39178525841) completed successfully with ten original synthetic tests and re-read the original failed fourth-run artifact. Its first failing strict source stage was **`stage303_stop_csv_invalid`**: strict Stage299–302 checks reproduced the saved originals. The fourth capture remains **rejected**.

The refined read-only diagnostic distinguishes a wrong event schema/order, noncanonical numeric input, missing/failed SIGINT-success flag, host wall-clock reversal, and PCM byte-count regression within the original `scene-recorder-stop.csv`. It publishes only event flags and *relative* wall/PCM deltas, never absolute wall times or PCM content. This refinement does not alter or weaken `tools/audit_nexium_pcm_recorder_stop.py`; its successful diagnostic CI will not make the original failed capture valid.

## Precise original recorder-stop failure confirmed

The refined [Stage338 diagnostic #39178879129](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39178879129) **passed 15/15 tests**, recovered the original failed fourth-run `scene-recorder-stop.csv`, and independently pinpointed `stop_csv_host_wall_clock_regression`:

- Original SIGINT source event flags **1 / 1**: both signal operations were reported successful.
- Original post-wait minus pre-SIGINT PCM size **0 bytes**: no source size regression in this stopped recorder snapshot pair.
- Original wall-clock delta from `before_sigint` to `after_wait`: **−87 ms**: the system wall clock regressed and violates the immutable Stage303 monotonic host-time requirement.

**Action:** The fourth archive stays rejected. A separate read-only pre-Stage303 diagnostic for subsequent fresh NRO captures prints only relative wall and PCM deltas so this source failure is visible immediately. The existing Stage303 original source audit remains unchanged; a new actual NeXium NRO run is needed to obtain valid independent fourth evidence. Monotonic clock telemetry elsewhere cannot override a backwards legacy wall source when strict original chronology requires it.
