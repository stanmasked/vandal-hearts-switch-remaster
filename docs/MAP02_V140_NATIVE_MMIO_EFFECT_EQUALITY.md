# MAP02 v140 — exact executed GPU/DMA MMIO addresses and values

Stacked on [v139 Draft PR #131](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/131) (**33/33** workflow runs passed). All CI MIPS programs remain **self-authored synthetic PS-X EXEs**, not retail Vandal Hearts content.

## Extending the real PCSX interpreter evidence

v139 already linked 19 actual MIPS `SW` instructions' current PC, complete 32-bit instruction words, GPU/DMA target classes and four `ExecuteBlock` stage boundaries in the pinned PCSX ReARMed interpreter. A changed source-register value or a KSEG-aliasing effective address could still lead to the same PC, opcode and MMIO class. v140 now checks both raw, effective `psxMemWrite32` arguments against the exact **source-authored synthetic program**:

- All **six GP0 setup values** from the original authored `SETUP` constant.
- **DMA DPCR** enable value `0x00000800`.
- For each of three genuine GPU linked-list DMA2 stages, the **CHCR reset**, **MADR base**, **BCR zero** and final **CHCR linked-list start** `0x01000401`.

The expected 19 effective MMIO address/value pairs are generated independently from the existing v125 synthetic GP0 and DMA2 source constants. They are cross-checked in order against v139's 19 static MIPS program PCs and exact source instruction words. The temporary v140 observer, injected into the pinned native PCSX `psxMemWrite32` **before actual memory dispatch**, verifies **both full effective address and full value**. It records counts of six GPU GP0 writes, three DMA2 starts and three DMA2 resets. The original MIPS code, GPU, DMA, Unai and VBlank routines remain unchanged.

The opt-in flags `--vh140-mmio-values --vh139-codewords --vh138-interpreter-pc --vh129-vblank-04` require an actual signed synthetic MIPS execution. Native success requires this exact aggregate marker:

```text
VH140_NATIVE_MMIO_VALUES_PASS matched=19 gp0=6 dma2_starts=3 stages=4 original_retail=0
```

A second real PCSX process uses `--vh140-corrupt-value-witness` to corrupt only the third **expected GP0 value** in the private observer. It must return exit code **50** and print `VH140_NATIVE_MMIO_VALUE_REFUSED`, not a false pass. No emulated GPU value or CPU register is altered.

### Independently compiled negative controls

A C11 bounds/undefined-behavior-sanitized source-only model, compiled separately with GCC and Clang, requires a positive 19-event sequence and all four mandatory refusals: a changed GP0 value with identical PC and instruction word, an aliased MMIO effective address with identical physical register class, a corrupt expected value, and reordered setup GP0 values with unchanged counts. These adversarial mutations are checked without logging any private values.

### Evidence boundaries

This extends a source-authored **synthetic** instruction runtime test. The original retail US `SLUS_004.47` has **not** been executed in the public workflow, actual MAP02 GPU packets have not been captured, and Nintendo Switch HD parity remains unverified. Private original-code investigation still requires matching user-owned original EXE/ELF and a separately controlled runtime.

- original_retail_MIPS_executed: false
- original_MAP02_frame_captured: false
- physical_PS1_GPU_parity_verified: false
- Nintendo_Switch_HD_parity_verified: false
