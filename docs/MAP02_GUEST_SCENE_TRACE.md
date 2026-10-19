# NeXium guest scene input → audout owner acceptance → first PCM page

This **diagnostic-only, Draft, DO NOT MERGE** research child of [PR #202](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/202) adds the missing correlation of actual MAP02 A/B button changes to the native audio worker. Previously #202 proved both WET_TAIL modes could boot, register optical A/B game-state changes, and generate independent nonzero PulseAudio PCM; it could **not** prove the worker accepted those scene changes.

The audio engine *already* includes a bounded multithread-safe witness with INPUT, POST, ACCEPT, SUBMIT_CALL and RELEASE_RETURN events. This PR **does not add I/O or blocking to the audout thread**. It reuses the existing optical writer, which is defined to be used only **after the audio owner thread joins** and which encodes up to 64 events with CRC32 into a 112×66 module bitmap. An independent host decoder reads a NeXium PNG screenshot.

## Experimental wiring

- `Makefile.map02-guest-trace` adds `VH_MAP02_AUDIO_TRACE_RECEIPT=1` **only** for builds explicitly requesting it. Both normal MAP02 and original audio-mode NROs are otherwise unchanged.
- The opt-in guarded code at `source/main.c` displays the journal after the user presses Plus and the owner thread has finished; an eight-second display window permits NeXium to take a screenshot. There is **no framebuffer trace rendering during musical playback**.
- The same NeXium runner builds and boots WET_TAIL=0 and 1 independently with A→B→Plus input. A host decoder checks valid magenta optical border, dimensions, exact 924-byte packet, CRC32, unused bits, drop counter and rows.
- For ticket/serial 1 (select hero, scene 2) and 2 (cancel, scene 1), the checker demands the same serial and scene for five ordered events: `INPUT → POST → ACCEPT → SUBMIT_CALL → RELEASE_RETURN`. Timestamps must not run backward.
- Nine synthetic screenshot/trace tests reject forged CRCs, lost slots, wrong serial/scene events, incomplete accepted requests, incomplete PCM page receipts, nonmonotonic timestamps and missing calibration borders.

A valid `RELEASE_RETURN` means **audout submission/recovery returned** after a PCM block rendered for the accepted scene. It is not direct DAC/spoken output timing, and does not establish that the samples in that exact page were nonzero. Actual nonzero **virtual monitor PCM** for both modes was independently confirmed in [NeXium #39210536520](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39210536520).

**Research limits:** independent guest recordings are not sample-aligned; the receipt does not distinguish an isolated wet-tail acoustic difference. That controlled DSP question was answered synthetically at host level in [PR #200](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/200). Original Vandal Hearts SEQ/VAB data and physical Nintendo Switch speakers remain untested.

The normal graphical game, standard NRO, original resources, and `main` are untouched. Do not merge this diagnostic experiment until exact-commit GitHub Actions and emulator evidence are reviewed. All parent PRs remain Draft.
