# MAP02 v135 — source-aligned local-only original US executable and MIPS ELF binding

Stacked after [v134 Draft PR #125](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/125), which successfully passed 28/28 workflow checks.

The original PC-port branch [PR #91](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/91) already records source-pinned regions of the original US `SLUS_004.47` and corresponding extracted MIPS ELF. This stage **bridges that original extraction research to the local GPU/DMA MIPS static candidate audit** without copying private executable data into CI or claiming MAP02 gameplay execution.

## Local original-source gate

`tools/analyze_map02_v135_original_us_elf_pair.py` accepts two separate private 0600 files:

1. User-owned, legitimately obtained US PS-X executable (PS-X header, correct RAM bounds, source load `0x80010000`).
2. Independently extracted little-endian ELF32 PS1 MIPS image with allocated, file-backed PROGBITS sections.

The original US executable is selected with the historical `596bb082a2de5f1fe977dd3d7e160b03` MD5 value recorded in PR #91. **MD5 is not collision-resistant authentication**, and a matching value does not alone prove provenance. The tool independently requires three byte-for-byte matching **original-source-anchored data ranges** in the extracted ELF:

| Public source anchor | Original PS1 address | Bytes |
|---|---:|---:|
| MAP32 original data | `0x801009bc` | 32 |
| MAP35 original data | `0x80100e9c` | 32 |
| Original ASCII font bitmap | `0x801012e4` | 1,152 |

The whole original ELF is **not** claimed to match every executable instruction: only those three unique source-pinned allocated regions are checked. The original PS-X code section is independently read and statically analyzed with the v132 MIPS-I delay-slot-aware candidate scanner. It counts possible static writes to DMA2 MADR/BCR/CHCR/DPCR and GPU GP0/GP1, as in v131–v132, without claiming that the code ran.

The EXE and extracted ELF each use the v134 no-follow `openat`-style directory-FD walk, nonblocking leaf, same-owner private 0600 single-hardlink checks, two-pass SHA-256 byte identity and unchanged inode metadata. After analysis, both are read again and compared with their original snapshots.

### Local opt-in command

Prepare **your own** original US game executable and corresponding MIPS ELF in a private 0700 directory. Ensure each file has mode 0600, and run:

```sh
python3 -m tools.analyze_map02_v135_original_us_elf_pair \
  /private/original/SLUS_004.47 \
  /private/original/extracted-mips.elf
```

Success produces only numeric MMIO-candidate counts, source anchor labels, and explicit nonproof flags. No original EXE/ELF bytes, decoded GPU words, paths or MD5/SHA256 values are printed. Refusal uses a generic path-free error.

## What public CI verifies — and what it does not

Public CI builds a self-authored extended synthetic PS-X EXE and self-authored ELF32 MIPS image with matching *generated* data at the same three addresses. It checks full and byte-corrupted anchor comparisons, missing/overlapping sections, invalid ELF machine, malformed headers, linked parent/leaf, permissions and generic CLI refusal. The final legacy retail MD5 gate must **reject** this synthetic pair. There is no positive original retail identity verification in CI because no retail assets are available in the public workflow.

A valid local run would establish that the analyzed private EXE matches the *historical MD5 selector* and that three ELF data regions are byte-identical. It would **not** establish a complete matching decompilation, instruction reachability, original MAP02 scene execution, PS1 GPU timing/parity, or Switch HD correctness.

- original_map02_gameplay_executed: false
- private_extracted_elf_complete_code_equivalence_verified: false
- hardware_ps1_gpu_equivalence_verified: false
- nintendo_switch_hd_equivalence_verified: false
