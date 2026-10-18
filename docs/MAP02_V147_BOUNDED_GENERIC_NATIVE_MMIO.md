# MAP02 v147 — bounded general-purpose MIPS GPU/DMA MMIO collection

Builds on [v146 Draft PR #138](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/138), with **40/40** green GitHub Actions. Previous native PCSX ReARMed execution verified 19 *source-authored synthetic* MIPS events, exact host ELF inode, fresh challenge and byte-identical synthetic EXE/ELF.

## Concrete obstacle

The v142–v146 native observer is hardcoded to **exactly 19 known source-authored MIPS stores in a fixed order**, making it unsuitable even as a diagnostic capture component for the original Vandal Hearts executable. Real original GPU/DMA code could execute repeated `SW` PCs in loops, with different program counters, order and effects.

## Implemented change

New `tools/apply_map02_v147_generic_native_mmio.py` adds an **independent** buffer/capture hook to the *real pinned PCSX* `psxMemWrite32` interpreter pathway:

- Captures ordered, actual `(pc, full executed SW instruction word, full effective MMIO address, stored value)` tuples when written to six PS1 GPU/DMA MMIO registers (GPU GP0/GP1, DMA2 MADR/BCR/CHCR and DMA DPCR).
- Contains **no embedded MIPS source PC, instruction word, expected register address sequence, expected command value or fixed 19-event acceptance rule**. Repeated static sites are valid and retain event order.
- Maximum **1024 events**; a 1025th event triggers a persistent error and the writer refuses completely rather than silently producing a truncated or misleading successful receipt. A zero-event result also refuses. Memory use and output size remain bounded.
- Uses the existing *root-to-leaf no-symlink* directory walker, prewritten `0600` staging, full-write and `fsync`, fresh independent `VH144_RECEIPT_CHALLENGE_HEX` sidecar, atomic `linkat` publication, no-overwrite and directory sync. The generic leaf is `vh147-original-mips-events.jsonl` inside a **separate** pre-created private `0700` output directory selected by `VH147_PRIVATE_TRACE_DIR`.
- Observer never mutates emulated MIPS registers, GP0 commands, DMA payloads, VBlank or Unai. Native console prints only an aggregate count and explicit `original_retail=0`.

**Important stage boundary:** `--vh147-bounded-mmio` is **currently deliberately permitted only with the v142 synthetic test mode**, inside the four proven native CPU stages. The original retail executable is **not** wired into the native collector in this PR, and is **not executed** in public CI. The generic capture code can be integrated into a separately controlled private retail boot mode in a subsequent stage, once the original guest's startup/BIOS/memory loading is established.

## Original executable analysis now accepts variable-length claims

New `tools/check_map02_v147_native_generic_mmio.py` has two distinctly scoped offline paths:

- **Public synthetic:** independently regenerate the source-authored v129 PS-X EXE, matching MIPS ELF and exact native 19-event tuple trace; verify independent run challenge and whole-event SHA-256 with the existing v144/v141 safeguards.
- **Local private original:** supply privately owned US `SLUS_004.47`, matching extracted ELF, variable-length JSONL receipt and separate fresh external challenge. The existing v141 original selector, three original data anchors and all executable MIPS section/word/PC/MMIO source checks must match. Results still explicitly mark `runtime_retail_execution_authenticated=false`, `original_map02_rendered=false`, `gpu_hd_parity_proven=false`. An arbitrary hand-crafted JSONL can look source-consistent; source matching **does not prove** execution or a genuine game frame.

For a private offline **source-consistency** check after collecting or receiving an independently generated trace:

```sh
python3 -m tools.check_map02_v147_native_generic_mmio \
  /private/run/vh147-original-mips-events.jsonl \
  /private/expected-run-challenge.hex \
  --private-original-exe /private/original/SLUS_004.47 \
  --private-original-elf /private/original/extracted-mips.elf
```

All private files must be user-owned, without symlinked components, and mode `0600`; independent private directory mode `0700`. **Do not upload copyrighted files, private PC/word/value traces or challenge contents.** No private bytes or individual PC/word/value pairs are emitted by the CLI.

## Actual public synthetic validation

The standalone GCC/Clang jobs compile **the same C collector** under `-fsanitize=undefined,bounds`, verify 19 synthetic events, **two events from the same PC**, 1025-event overflow refusal, empty-refusal, protected mode-0600 atomic output and prevented overwrites/symlinked directories. The full pinned GCC/Clang native PCSX jobs opt in to the new generic recorder **in addition** to v142's original 19-event strict synthetic observer and independently validate the newly emitted private JSONL against source-generated EXE/ELF and challenge. Five genuine v129 four-VBlank profiles, three DMA2 starts, five Unai samples and earlier v138–v146 native privacy checks must stay green.

**No retail MAP02 execution, original PS1 image capture, physical hardware parity, or Nintendo Switch HD graphics equivalence is claimed.** PR remains Draft; `main` unchanged.
