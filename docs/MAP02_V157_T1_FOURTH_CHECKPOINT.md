# MAP02 v157 — t1 register integrity before the fourth synthetic MIPS opcode

Stacked on [v156 Draft PR #156](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/156), whose 50/50 workflows passed.

This deliberately extends the native PCSX ReARMed four-instruction LUI/ORI diagnostics without enabling any retail-original game execution.

## Native checkpoint

The v156 mechanism validates the first four MIPS source-authored opcode words and their register effects. The new **opt-in** `--vh157-corrupt-t1-fourth` flag can only be combined with:

`--vh129-vblank-04 --vh150-bounded-instructions --vh155-four-instructions --vh156-verify-register-effects`

The first three synthetic instructions execute normally (LUI/ORI on t0 and LUI on t1). Just before PC `0x8001000c`, the observer intentionally flips one bit in native register **t1 / R9**. The source-derived expected register value is `0xe3000000`, so the changed value `0xe3000001` is refused by the real PCSX interpreter **before** dispatching the fourth ORI instruction. The bounded positive run and original t0-corruption negative run are retained.

The required precise negative marker is `VH157_NATIVE_T1_FOURTH_REFUSED matched=3 attempted=4 original_retail=0` with exit code 61. Separate test-only arguments without the full register-check mode, or attempts to combine t0 and t1 corruption flags, must be rejected before execution with `VH157_INVALID_MODE_REFUSED` and exit 61.

Compiled GCC/Clang C tests verify the exact native GPR checkpoint, three accepted source-derived words, the fourth rejection, the latched fault state, and preservation of the v156 legitimate four-word path. The full pinned PCSX/Unai matrix runs the actual emulator with the same synthetic EXE and retains all earlier SHA-256/VBlank/DMA/MMIO tests. No raw guest traces or user-owned PlayStation data are published.

## Limits

Only four self-authored synthetic MIPS opcodes have been investigated. These checks do not prove BIOS/CD startup, full PlayStation behavior, the original MAP02 battle, Nintendo Switch graphical parity or OS process-level isolation. Keep this PR in Draft pending successful GCC/Clang native and compiled CI.
