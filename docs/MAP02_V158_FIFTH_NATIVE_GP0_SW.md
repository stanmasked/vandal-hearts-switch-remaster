# MAP02 v158 — fifth interpreted MIPS SW reaches the native PlayStation GP0 port

Stacked on [v157 Draft PR #159](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/159), where **all 51/51 GitHub Actions checks succeeded** for the synthetic four-instruction register-integrity investigation.

## First hardware-register effect in the new bounded native path

v158 extends the verified first four LUI/ORI source-authored MIPS instructions with the self-authored v129 program's fifth instruction, an actual **MIPS `SW t1,0(t0)`** to PS1 GPU GP0 at physical address `0x1f801810`. The expected stored value is `0xe3000000`. All five opcode words are independently derived from the public `make_map02_v129_four_vblank_exe.build()` fixture and checked against PS1 guest RAM after the v151 complete 8192-byte SHA-256 preflight.

The opt-in `--vh158-five-instructions` may only be used together with `--vh129-vblank-04 --vh150-bounded-instructions --vh155-four-instructions --vh156-verify-register-effects`. Under this isolated synthetic route, the actual pinned PCSX ReARMed MIPS interpreter is allowed **five** instructions and must refuse instruction six before execution. The existing four-step v155-v157 positive/negative modes remain unchanged when this option is absent.

A new narrow observer in `libpcsxcore/psxmem.c` records whether the fifth interpreted MIPS `SW` reached the **real PS1 MMIO write callback** with source-authored PC, opcode, GP0 port and value. The positive run requires exactly one such write, no unexpected guest memory writes, five source-matching opcodes and a genuine instruction quota stop. Its public marker is `VH158_NATIVE_GP0_FIFTH_PASS opcodes=5 gp0_writes=1 capped=1 original_retail=0`.

A negative test, `--vh158-mutate-fifth`, deliberately changes one byte of the fifth guest instruction **after** the first four valid dispatches and before the fifth native fetch. It must be refused before any GP0 MMIO write, producing `VH158_NATIVE_FIFTH_OPCODE_REFUSED matched=4 attempted=5 gp0_writes=0 original_retail=0` (exit 62). Missing register checks, invalid profiles and mixed earlier mutation modes must refuse before guest execution.

## Native failure diagnosis and fix (18 October 2026)

The first pinned-PCXS tests **failed** despite a correct source-derived opcode `0xAD090000`. A temporary privacy-safe native diagnostic showed `accepted=5 attempts=5 stop=1 fault=0 gp0=0 bad=0 t0_ok=1 t1_ok=1` on both GCC and Clang. This eliminated MIPS opcode, quota and register mismatches as causes. The defect was in the diagnostic observer placement: the v158 GP0 observer call had been inserted **inside** `vh138_pc_observe`, which returns immediately when the independent v138 diagnostic mode is inactive.

The v158 call is now installed **at the unconditional entry to `psxMemWrite32`, ahead of its call to the optional v138 observer**. The existing v138/v139/v140/v142/v147 logic is deliberately unchanged. A new compiled test checks that the GP0 write is recorded with v138 disabled, along with a countercheck when v138 is enabled. This fixes an observability defect without changing the CPU interpreter, GP0 payload, guest RAM or GPU renderer. The final result must still be verified on the actual pinned PCSX native GCC/Clang matrix after the fix.

## Verification and limitations

Independent GCC and Clang C harnesses test actual native five-word source matching, four-word legacy compatibility, exactly one GP0 observer callback and zero callbacks after fifth-word corruption. The full pinned PCSX ReARMed/Unai workflow tests the real native emulator and retains earlier VBlank/DMA/GP0, SHA-256 and MIPS-register regressions.

This proves at most a **source-authored synthetic CPU write reaches the emulator GP0 MMIO path**, not pixels rendered by the original game. It does not authenticate or execute proprietary retail MIPS data, PS1 BIOS/CD content or the original MAP02 battle, nor does it establish Nintendo Switch HD rendering fidelity or sandboxing. No original assets are uploaded to public GitHub. Keep the PR in Draft until real native and GCC/Clang test evidence has been reviewed.
