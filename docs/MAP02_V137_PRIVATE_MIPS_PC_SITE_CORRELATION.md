# MAP02 v137 — private source-bound MIPS program-counter / MMIO class correlation

Stacked on [v136 Draft PR #127](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/127), whose full **30/30** GitHub Actions workflows passed. The earlier v136 original-only source validation compared executable ELF32 MIPS instruction bytes with the user-owned original PS-X EXE, excluding MAP32/MAP35/font data from static candidate counts.

## Why precise source instruction addresses matter

A static count of possible GPU/DMA register writes cannot be reconciled with a future MIPS CPU trace: the runtime must identify **the exact originating instruction address (PC)** and the destination **register class**. v137 adds a private, word-aligned site inventory to the existing v132 MIPS-I delay-slot scanner. For every statically resolved store, it associates:

- the exact byte-aligned original MIPS program counter (ELF executable section address plus the instruction offset);
- the register class (DMA2 MADR/BCR/CHCR, DMA DPCR, GPU GP0/GP1);
- whether a DMA2 CHCR source register is statically known to carry the linked-list literal.

Those addresses and instruction words **never appear in public output**, in GitHub artifacts, or in emitted rejection messages.

The separate, local-only tool `tools/verify_map02_v137_private_mips_pc_sites.py` accepts three input files, all held privately (0600, single hardlink, no ancestor symlinks):

1. A user-owned original US PS-X EXE with the existing v135 historical retail MD5 selector.
2. The corresponding extracted MIPS ELF, with v136 exact source-anchored original data and executable-code byte comparison.
3. A separate `0600` bounded JSONL file with **claimed** per-store MIPS PC and register-class pairs, in canonical form:

```json
{"kind":"dma2_chcr","pc":2147549184,"schema":"vh.map02.private-mmio-pc-claim.v1"}
```

The JSON is a **format example only**, not a real PS1 observation or asserted original instruction address. Each record must match the same PC and MMIO register class in verified executable MIPS code. The tool refuses unknown, unaligned/incorrect, aliased or wrong-class PCs, code tampering, invalid private input paths, modified files, duplicate JSON object keys and noncanonical JSONL. Repeated occurrences of the same valid PC are allowed, because one code site can be visited repeatedly.

Run it only on your own locally retained resources:

```sh
python3 -m tools.verify_map02_v137_private_mips_pc_sites \
  /private/original/SLUS_004.47 \
  /private/original/extracted-mips.elf \
  /private/capture/mmio-pc-claims.jsonl
```

The script performs two-pass, inode-bound private reads, then checks the originals and the receipt again after analysis. Success yields only the total number of matching claims, the number of **distinct** matched source sites, counts by register class, and explicit **negative evidence flags**. No original PCs, raw MIPS instructions, file paths, proprietary code, hashes, images or private JSONL are printed.

## Strict evidence boundary

**The supplied event file is not authenticated.** A local operator (or an attacker) could simply write invented PCs that are present in a static code section. Therefore successful correlation is **not** proof that any instruction executed, a DMA channel started, a frame rendered, original MAP02 was reached, or PS1/Switch GPU output is equivalent. This is a source-consistency gate that can become one input to future separately authenticated runtime PC capture. It must not be reported as a gameplay milestone.

- `claim_producer_authenticated`: false
- `execution_or_reachability_proven`: false
- `dma_or_gpu_runtime_execution_proven`: false
- `original_map02_frame_or_rendering_proven`: false
- `physical_ps1_equivalence_proven`: false
- `nintendo_switch_hd_parity_proven`: false

## Public GCC/Clang tests

CI uses **only synthesized v129 PS-X and v136 ELF code/data fixtures**. It proves the callback lists exact instructions (including a genuine MIPS-I delay-slot store), that counts reconcile to v136, that wrong PC, register kind, KSEG alias, changed executable code or malformed claimed-event JSONL are refused, and that the retail original-selector gate rejects the synthetic input. Private FIFO/symlink/permissions protections and the full pinned PCSX MIPS DMA/VBlank/Unai workflow remain unchanged.
