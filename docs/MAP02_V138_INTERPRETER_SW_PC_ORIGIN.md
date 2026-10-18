# MAP02 v138 — an actual PCSX interpreter MIPS SW PC witness (synthetic only)

Stacked on [v137 Draft PR #128](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/128), whose **31/31 GitHub Actions workflows passed**.

## From claimed instruction PCs to actual interpreter instructions

Previous v137 correlated an operator-supplied JSONL of claimed MIPS PC + GPU/DMA register class against the bytes of a user-owned PS-X EXE and MIPS ELF. It **did not authenticate** the producer of those events. The only reliable way to advance is to record the program-counter origin **inside the emulated CPU instruction dispatch**.

At the pinned upstream PCSX ReARMed revision `8b6c163575e6ce9a0537553e0d4ed4225315955e`, the R3000A interpreter implements:

```c
OP(psxSW) { psxMemWrite32(regs_, _oB_, _rRt_); }
```

The engine increments `regs_->pc` by four **before dispatching** the instruction. Its branch handler also increments `regs_->pc` before executing the actual MIPS delay slot. Thus `regs_->pc - 4` at `OP(psxSW)` is the CPU-origin PC for a normal SW and for a SW in a taken branch delay slot. No DMA callback, guessed post-phase marker, frontend timing, or host-injected GPU command is used to synthesize the PC.

### Implementation

`tools/apply_map02_v138_interpreter_pc_witness.py` patches **only a disposable checkout of the pinned emulator**, after applying all v66–v129 original probes. The observer hooks `OP(psxSW)` and its address-checked variant `OP(psxSWe)`, with no change to the original `psxMemWrite32` behavior. It observes, in-process:

- the actual interpreter PC `regs_->pc-4`;
- the exact fetched source MIPS instruction word `regs_->code`;
- the actual CPU-calculated MMIO address `_oB_`, normalized only across supported PS1 KSEG aliases;
- whether a linked-list DMA2 CHCR write carries the actual `0x01000401` value.

The separately built **source-authored** v129 synthetic MIPS program supplies 12 expected instructions in order: for each of three DMA2 lists, clear CHCR, set MADR, set BCR, start CHCR. The expected PC, fetched word and register class are derived at test/patch construction time from the v132 static scanner. That expected table is compiled into the temporary, private native process. It is **not** a list inferred from the observed CPU stops.

Only after v129 finishes its original GPU/DPCR setup does the frontend enable the SW observer. After three CPU-executed DMA stages it disables the observer. Every missing, reordered, extra or mismatching instruction increments a refusal counter; a valid run requires exactly 12 matches, zero refusals and the unchanged existing 5-sample/4-VBlank native Unai proof. The only public log is:

```text
VH138_CPU_SW_PC_PASS stores=12 dma2_madr=3 dma2_bcr=3 dma2_chcr=6 linked=3 interpreter_origin=1 retail_map02_verified=0
```

No raw PC, MIPS opcode, MMIO address, private EXE/ELF, private paths, source code or VRAM bytes are printed or uploaded.

### Independent negative controls

Standalone GCC and Clang tests compile and execute the **same actual C observer** under UBSan/bounds, first against the complete expected source-authored sequence. Then they mutate the first runtime PC, opcode or register class and require process failure. Source-level tests check exact v129 frontend hook insertion and that the old v129 oracle, five real-VBlank scenarios, v130 C bounds, and v137 private static PC source-validation regressions remain intact.

Full pinned PCSX ReARMed native GCC/Clang workflows run all five 04/13/22/31/40 original synthetic timing modes. For each mode they require both the new actual CPU instruction-origin witness and v129's native four-VBlank/three DMA2/five Unai post-handler witness **from the same source-authored EXE**, with its private SHA-256 verified before and after each process.

## Explicit scope

This **does attest observation inside the actual emulator CPU interpreter for the self-authored synthetic MIPS EXE**, rather than relying on user-authored PC claims. It **does not** establish any actual retail Vandal Hearts instruction was executed, that MAP02 was loaded, physical PS1 timing/equivalence, or Nintendo Switch HD graphic parity. These claims remain false.

The local-only v135–v137 original executable provenance tools are not bypassed or replaced. An eventual retail capture must be separately produced with pinned binary provenance and private safeguards, not inferred from this synthetic test.
