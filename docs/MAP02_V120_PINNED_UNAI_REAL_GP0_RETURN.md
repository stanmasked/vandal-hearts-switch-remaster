# MAP02 v120 — A–B–C–D–A in the actual pinned PCSX Unai renderer

Stacked after [v119 Draft PR #110](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/110).

## The missing experimental control

v115–v119 proved exact equality of **24 selected native VRAM samples**
over 2–5 consecutive observed Unai GP0 callbacks. Their isolated native C
tests could construct genuine A–B–C–D–A observations, but the earlier
full pinned PCSX synthetic MIPS scene never generated an exact return
to four calls earlier. It would be misleading to claim that that
earlier scene tested successful return behavior inside the emulator.

v120 introduces a separate **host-submitted synthetic GP0 control**
executed by the *actual* pinned PCSX ReARMed Unai GPU plugin. It runs
only in the authenticated `--vh104-double-readback-smoke` opt-in path,
after the four emulator VBlank callbacks and after the existing
v82 private JSONL has been published and v119's ordinary native
aggregate counters have been checked.

The v120 test deliberately does NOT claim that these five commands
came from the interpreted MIPS CPU. They use the normal plugin
`GPU_writeDataMem` submission entry point from the host; this is
separate from the preserved MIPS-authored original synthetic scene.

## In-emulator test sequence

v120 resets only the ephemeral exact-value sidecar and requires its
24-point cache to have been securely erased, then submits five
three-word GP0(60) 4×4 opaque rectangles at x=40, y=160 (one of the
actual 24 existing sample columns and rows).

The colors are all independently distinct for A, B, C and D; the
fifth uses exactly A's RGB color. All GP0 commands therefore run
through Unai's normal native renderer. For **each** command, v120
calls `GPU_freeze`, checks all 16 pixels in the 4×4 region
against the expected GPU 16-bit result and refuses any mismatch.

After the fifth command, the already proven v119 sidecar must report:

- Exactly five native Unai post-handler sample observations.
- Exactly one five-handler sample-value comparison window.
- Exactly one **return to four back** in the zero-VBlank-gap bin.
- Zero counts for every other five-handler outcome and gap bin.
- No artificial VBlank callback, and all four retained 24-value
  buffers erased on reset.

The sequence happens **after the canonical v82 JSONL was published**.
It does not contaminate the earlier original private event stream
or rewrite its immutable publication format. The native smoke emits
only the fixed aggregate `VH120_GP0_RETURN_PASS` marker, without
any pixel values, pixel hashes or captured graphics.

A separate fail-closed verifier checks that marker against the
unmodified, independently validated private v119 runtime/journal,
then uploads only
`proof/public/v120-real-gp0-return-summary.json` when all checks
succeed. The pinned full emulator workflow builds and executes this
source in both GCC and Clang. A dedicated native regression suite
also rejects missing, duplicated, forged or malformed status.

## Interpretive limits

This is the actual software GPU plugin, but the five additional commands
are **host-submitted synthetic fixtures**. They are not MIPS-authored,
not commands extracted from Vandal Hearts and not original retail
MAP02 input. No VBlank is forged to make a return pass; the test is
within one post-capture renderer interval.

The exact return establishes equality of the 24 sampled 16-bit values,
NOT equality or persistence of the entire VRAM, physical PS1 timing,
scanout or Nintendo Switch HD renderer output.

`original_retail_MAP02_verified=false`
`physical_PS1_verified=false`
`HD_replacement_approved=false`

The change is in a stacked Draft PR; `main` remains unchanged.
