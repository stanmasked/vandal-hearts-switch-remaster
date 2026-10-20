# MAP02 Stage294 — capture the real NeXium GUI FileLogger in 21/22ms guest trials

**Research-only Draft; DO NOT MERGE.** Child of [Stage293 Draft PR #362](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/362), source pinned to `6df078f7dc5d72ff39d2eac43452d5fa75232966`. No original PS1 ROM, soundtrack, artwork, production Nintendo Switch game code or upstream NeXium repository changes.

## Confirmed reason the old stdout was empty

[Stage293 independent Actions #39500177577](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39500177577) **SUCCESS**, all **19/19** synthetic tests and independent source-pinned raw guest/PNG/PCM/lifecycle-CSV auditor passed. The archived `nexium-guest-stdout.log` and redirected stderr were **zero bytes** for BOTH requested 21 and 22ms trials, even though the 22ms CPAL error callback count increased **36**. Therefore no actual error message text was preserved by those old archives.

Source inspection of immutable NeXium `nexium-emu/nexium@089562567a0a8760dfdd8420e1f57c35159a9219` establishes the immediate explanation:

- `nexium-gui/src/main.rs` installs `nexium_common::FileLogger`, not `env_logger` to stdout/stderr.
- `nexium-common/src/file_logger.rs` writes `nexium-YYYYMMDD-HHMMSS.log` into `nexium_common::paths::root().join("logs")`. It immediately flushes Error and Warning entries. This internal log path is **not** the redirected stdout/stderr file.
- `nexium-common/src/paths.rs` resolves the root from `NEXIUM_DATA_ROOT` when explicitly set, otherwise Linux user config `$HOME/.config/NeXium`.
- The historical Stage290/291 runtime wrappers set a temporary `HOME` per experiment and never copied the generated `$HOME/.config/NeXium/logs/nexium-*.log` into the evidence archive. Therefore **there is no evidence that the original Error message text can be reconstructed from historical evidence**; future experiments must capture the logger itself.

## New actual matched guest experiment, with no new binary or ROM

This Stage294 matrix launches **two separate real Linux guests** on independent GitHub runners for requested `PULSE_LATENCY_MSEC=21` and `22`. It reuses exact archived Stage287 lifecycle NeXium ELF SHA-256 `c3803abd7a06fd4081d7d49367cfbd2cedc4bb1650996f1e09fca5788c881b65`, same original ROM-free generated NRO SHA `371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b`, Rustarmic, virtual Pulse null sink, 48k stereo PCM, GUI input sequence and guest optical screenshots. Only the requested hint and stage-scoped temp/evidence paths change from the prior validated guest route.

The new helper script **does not redirect or alter GUI FileLogger configuration**. After the guest exits, it locates the real `nexium-*.log` in the stage-specific temp HOME default configuration directory. The separate `tools/audit_map02_filelogger_guest_stage294.py` requires exactly one original file, verifies its bounded content and independently redecodes the real guest prejoin/final PNG, strict original eight-page guest CRC outcome, monotonic CPAL lifecycle/error `L` CSV and raw virtual PCM sample count/SHA. It enforces exact current GitHub run ID, requested hint, source receipt, ELF and NRO SHA-256. It extracts CPAL error message groups through the already-tested Stage293 sanitizer, including only short redacted exemplars, error line counts and original log SHA/size.

**Original raw host GUI log files remain exclusively on each ephemeral GitHub runner.** They are **not uploaded**: the artifact includes only sanitized JSON and ROM-free generated guest/CPAL/PCM evidence. No user personal data or original game assets are intentionally captured. Synthetic tests check fail-closed behavior and guard against incorrectly classifying guest CRC, CPAL callbacks or virtual PCM.

## Limits and next criterion

The GUI FileLogger records wall-clock timestamps but those are not independently correlated with per-callback monotonic guest input events. Counted whole-session `cpal stream error:` message lines must not be falsely equated to the **guest-window CPAL error callback counter**. This experiment may recover *reason text*, not its exact event order or causal role.

If the 22ms log provides a specific CPAL error description, it is still a **successful guest CRC/PCM 22ms** trial and the error text must not automatically be blamed for the missing callback entries at 21ms. A 21ms run may again show no new CPAL errors, even if it has a finite pending guest `audoutPlayBuffer` snapshot. The requested PulseAudio latency hint is not a measured ALSA hardware period. No permanent deadlock, precise root cause, original game's soundtrack fidelity, physical Nintendo Switch output, or game fix is proven.

Keep Stage283/284 old-ELF six-run baseline and Stage290/291 new-ELF initial pair intact. All experimental PRs remain Draft / DO NOT MERGE.
