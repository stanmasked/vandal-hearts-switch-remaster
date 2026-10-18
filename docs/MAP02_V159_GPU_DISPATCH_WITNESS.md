# MAP02 v159 — native fifth GP0 GPU dispatch proof

Stacked on Draft PR #161, v158 (verified GCC/Clang native fifth-SW GP0 witness).

## What this proves

v158 proved exactly one synthetic MIPS store reached native psxMemWrite32. v159 adds a distinct bounded observer to the pinned native psxHwWrite32 GPU register 0x1810 branch, immediately before its unchanged GPU_writeData(value) call.

Both observers must count exactly one matching synthetic fifth SW, with no mismatches. A deliberately changed fifth opcode must refuse BEFORE either MMIO entry or GPU dispatch, with both counts zero. Source RAM identity, fetched opcodes, four register checkpoints and five-instruction limit remain required.

Additional log markers:
- VH159_NATIVE_GPU_SINK_PASS sink_writes=1 original_retail=0
- VH159_NATIVE_FIFTH_SINK_REFUSED sink_writes=0 original_retail=0

The previous v158 PASS/REFUSED markers are retained byte-for-byte.

## Validation

Standalone C tests on GCC and Clang cover normal GP0 branch entry, duplicate write refusal, wrong PC/opcode/data refusal, inactive observer and GP1 non-match. The full pinned native PCSX ReARMed / Unai matrix must run the v159 observer under both compilers and check positive and fifth-mutation negative results.

## Limits

Observing the dispatch branch *before* GPU_writeData does not demonstrate actual GPU plugin consumption, GPU-state change, pixels, MAP02 runtime or Nintendo Switch HD parity. No proprietary retail assets or BIOS are present or uploaded. Synthetic-only execution, Draft pending CI.
