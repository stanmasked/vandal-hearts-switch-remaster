# MAP02 v156 — validate actual MIPS register effects, not only instruction bytes

Stacked on [v155 Draft PR #155](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/155), which already confirms four genuine native PCSX ReARMed **synthetic** MIPS instructions and a stop before instruction five.

## Source-derived register checkpoints

The same four opcodes are derived from the repository-authored `make_map02_v129_four_vblank_exe.build()` test. This source program begins with MIPS-I `LUI` and `ORI` operations, allowing independent expected values to be calculated without copying any original PlayStation game code:

| Before instruction | Expected t0 (R8) | Expected t1 (R9) |
|---|---|---|
| Second | `0x1f800000` | Not checked |
| Third | `0x1f801810` | Not checked |
| Fourth | `0x1f801810` | `0xe3000000` |
| After all four | `0x1f801810` | `0xe3000000` |

The opt-in `--vh156-verify-register-effects` flag is allowed only in the v155 four-instruction diagnostic with the original v129 profile and the existing SHA-256 authenticated, source-generated synthetic guest RAM. The PCSX interpreter checks the **actual** general-purpose CPU registers `regs->GPR.r[8]` and `regs->GPR.r[9]` at successive fetch boundaries. After the fourth instruction, the native frontend verifies both final registers and the v150 instruction quota. The positive result is `VH156_NATIVE_REGISTER_EFFECTS_PASS matched=4 capped=1 original_retail=0`.

For the negative experiment, `--vh156-corrupt-t0-second` deliberately flips one bit of **t0** at the entry of the second instruction, after the first opcode has been executed. The native interpreter must reject the second opcode **before dispatch**, with exactly one accepted word, two attempted steps and the marker `VH156_NATIVE_REGISTER_CORRUPTION_REFUSED matched=1 attempted=2 original_retail=0` (exit 60). Mixing this register mode with earlier opcode-corruption modes or omitting the register-verification flag must refuse early.

Independent GCC/Clang C tests verify the source-decoded LUI/ORI expected values, all register checkpoints, injected and unexpected corruption, and the latch after refusal. The pinned PCSX/Unai GCC/Clang workflow runs both scenarios on the **actual native interpreter** and retains the older synthetic VBlank, DMA, MMIO, SHA-256 and opcode-integrity regressions. Public outputs are aggregate status markers only; user-owned original PS1 files are never uploaded.

## Limitations

v156 observes **four straight-line synthetic MIPS operations**, not the commercial game's real CPU startup, BIOS/CD stack, maps, enemy logic or graphics. It is not a general sandbox and does not prove MAP02 gameplay or Nintendo Switch image parity. Keep the PR Draft until the actual native and compiled CI workflows pass.
