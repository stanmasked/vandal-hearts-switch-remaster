# MAP02 v141 — private original MIPS instruction and MMIO claim correlation

Stacked on [v140 Draft PR #132](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/132), which completed **34/34 GitHub Actions** successfully. The v138–v140 native PCSX ReARMed interpreter experiments demonstrated actual execution and accurate matching of 19 PC, 32-bit instruction word, effective MMIO address and stored-value tuples from a source-authored **synthetic** PS-X program; they did **not** run original Vandal Hearts retail content.

## Original-code research preparation

The v137 tool could compare an *externally provided, unauthenticated* list of MIPS PCs and GPU/DMA register classes with byte-identical executable ELF sections extracted from a locally owned US PS-X EXE. The new `tools/verify_map02_v141_private_original_mmio_claims.py` extends the private offline gate to **all four observation dimensions** already tested on the real interpreter under v140:

- exact 32-bit MIPS program counter `pc` within a byte-identical `SHF_ALLOC|SHF_EXECINSTR` MIPS ELF section;
- exact entire **32-bit executable MIPS `SW` word** from the matching address of the local original PS-X EXE, rather than just the `SW` opcode;
- full virtual/effective MMIO `address`, validated against actual PS1 GPU/DMA physical register mappings and the statically inferred destination class (kuseg/kseg0/kseg1 aliases are separately counted);
- claimed `value`. Values for `$zero` stores must be zero; stores with a statically proven DMA2 CHCR linked-list literal must be `0x01000401`. **Other stored values cannot be independently proven without the CPU's runtime register state.**

Each bounded receipt contains canonical JSONL with strictly contiguous event sequence indices. Example **schema only**:

```json
{"address":528486424,"pc":2147549184,"schema":"vh.map02.private-exact-mmio-claim.v1","seq":0,"value":0,"word":2902458544}
```

The numerical example is **illustrative**, not extracted from or asserted to be an original instruction or validated trace. Only synthetically generated receipts are present in CI.

## Private local invocation

Use your own legally obtained US `SLUS_004.47`, the matching extracted original MIPS ELF, and an MMIO-claim JSONL collected under separate local control. Place all files in a private `0700` directory and give each file mode `0600`. No intermediate directory components can be symlinks; the reader forbids hardlinks, unusual file types, FIFO and the `..` component. It reads all inputs twice using no-follow parent-dir file descriptors and checks unchanged bytes again at the end.

```sh
python3 -m tools.verify_map02_v141_private_original_mmio_claims \
  /private/original/SLUS_004.47 \
  /private/original/extracted-mips.elf \
  /private/capture/claimed-mmio.jsonl
```

The historical US MD5 value selects an original edition; MD5 **is not** collision-resistant authentication. Three original data anchors and every selected executable ELF code section must match the supplied EXE. No original executable bytes, instruction addresses, values, private paths, content hashes, individual event records or PC-by-PC diagnoses are emitted; results are coarse counts plus explicit negative evidence flags.

## What this does *not* establish

**No captured-original gameplay execution is attested by this tool.** A JSONL event series may be fabricated. A successful return establishes *only source-code consistency* of the claimed events with verified private bytes. It does not authenticate PCSX as the producer, prove an instruction or GPU command was executed, demonstrate a real MAP02 frame, establish frame identity, or verify physical PS1 or Nintendo Switch GPU parity. A separate, controlled native runtime collector and original assets are still required before such statements become possible.

This v141 stage does **not** silently reinterpret source-generated synthetic tests as original-game execution.

- `trace_producer_authenticated`: false
- `mips_execution_or_reachability_proven`: false
- `original_map02_loaded_or_rendered`: false
- `mmio_value_compared_to_full_cpu_state`: false
- `physical_ps1_parity_verified`: false
- `nintendo_switch_hd_parity_verified`: false

## Public CI

The GCC/Clang jobs generate a synthetic v129 PS-X executable and its corresponding independently generated ELF32 MIPS fixture with byte-matched text and three generated original-address data anchors. They replay the 19 source-generated v140 tuples. They must refuse unknown PC, one-bit altered MIPS codeword, changed executable ELF source, wrong effective MMIO class, unmapped/invalid address, nonzero `$zero`-source store, altered provable DMA2 linked-list literal, malformed/colliding keys, wrong event order, symlink/permissions/FIFO/hardlink and an attempt to classify the synthetic EXE as pinned retail. They also preserve the existing full pinned PCSX GCC/Clang VBlank/Unai original-synthetic regression jobs.
