# MAP02 Stage286 — opt-in CPAL lifecycle state probe

**Research-only Draft. Do not merge into game code.** Parent is [PR #335](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/335), with six-archive callback boundary audit successful in [Actions #39486131186](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39486131186).

The Stage285 recordings established that no new CPAL callback entries occurred after game input in all three requested 21 ms trials, whereas all three 22 ms trials continued for 123 sampled intervals. These existing archives cannot show CPAL stream lifecycle or errors; the precise mechanism remains undetermined.

Stage286 prepares a **new, separately built** opt-in NeXium research host. It builds upon the unchanged Stage274 atomic callback overlay and adds Linux-only atomic lifecycle states: 1 attempting stream build, 2 built, 3 stream.play returned success, 4 build failed, 5 play failed; alongside an incrementing CPAL stream error-callback counter. The existing 200 ms reporter is changed to emit lines prefixed `L` with monotonic time, lifecycle state, error count and all prior counters. No audio bytes or game content are logged.

A separate workflow reuses the exact source-pinned upstream NeXium and existing overlay before applying the lifecycle probe, runs adversarial synthetic source-patch tests and attempts a real Cargo Rust type check. It does not run the guest or establish a binary SHA until a separate controlled binary build. Source identity and installation are intended to fail closed when upstream anchors change.

**Limitations:** The reporter samples state; it does not itself capture precise error timestamps, per-callback clocks or proof of ALSA wakeup mechanics. The lifecycle states only distinguish build/play outcomes and **count** error callback invocations: they cannot prove stream pause, drop, starvation or an exact transition instant. Stream lifecycle signals can also perturb runtime. Any new host needs its own SHA and matched 21/22 tests before comparison to the frozen original six-trial baseline.

No original game ROM, music or physical Nintendo Switch audio are involved. **No production fix is claimed.**
