# MAP02 v136 — compare original ELF .text instructions, not data-as-code

Stacked on [v135 Draft PR #126](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/126). The full v135 revision passed 29/29 GitHub Actions workflows under GCC and Clang.

## Correct an important limitation of the previous static investigation

The v135 local-only provenance tool compared three original US data anchors (MAP32, MAP35 and font) with an independently extracted MIPS ELF and checked a pinned historic retail MD5 selector. But it then analyzed **every 32-bit word in the PS-X loaded payload** as though it were executable MIPS. Source data, fonts, static pointers, constants and compressed resources may accidentally contain words resembling GPU DMA register stores.

That can inflate a static candidate count. It still would not prove an instruction ran, but it unnecessarily confounds analysis.

The new v136 tool `tools/analyze_map02_v136_original_code_sections.py` requires:

1. The same private, no-symlink, 0600, two-pass-verified US PS-X executable and original little-endian MIPS ELF pair.
2. The historical pinned US retail MD5 selector and the three exact data-anchor byte comparisons from v135. MD5 remains an **identity hint**, not collision-resistant cryptographic proof.
3. At least one unique, allocated, executable, file-backed ELF32 MIPS PROGBITS section with SHF_ALLOC and SHF_EXECINSTR; aligned start, size and file offset; bounded to PS1 RAM and mapped into the PS-X declared load.
4. **Byte-for-byte comparison of every selected MIPS executable section against the corresponding PS-X EXE range.** A mismatch in even a single instruction refuses the entire analysis, even when all three data anchors still match.
5. Executable section address ranges may not overlap each other or any known MAP32/MAP35/font original data range. Missing or ambiguous executable code sections refuse.
6. A fresh two-pass read of both private files after the full analysis, checking byte identity with the original snapshots.

Only these verified executable code sections are passed to the MIPS-I delay-slot-aware scanner. State is reset between independently declared code sections. The aggregate result contains code-section count, scanned instruction-word count and possible GP0/GP1/DMA2/DPCR store counts, never original code bytes, file paths, original image offsets, private hashes or GPU textures.

### Why this is a better check but is not gameplay proof

ELF SHF_EXECINSTR is a **classification from the independently extracted ELF**; the comparison proves that those exact bytes are also present at those addresses in the private PS-X image. It does not prove complete classification of every real code path, absence of inline data, the correctness of the full extracted ELF, reachability of any instruction, that MAP02 was ever loaded, or that any GPU/DMA command was executed. It cannot demonstrate physical PS1 or Switch HD parity.

## Public CI negative controls (no retail input)

The tests generate their own v129 synthetic PS-X EXE plus a newly generated MIPS ELF with one byte-identical code section and three synthetic data anchors. They require:

- Code-only GP0/DMA candidate counts match original source-authored synthetic MIPS.
- Changing a single code byte fails while all original-address data anchors continue to pass.
- A fake three-instruction DMA2 CHCR write embedded in MAP32 **data** increases the broad static count but must **never** increase the new verified-code-only count.
- Wrong SHF_EXECINSTR/SHF_ALLOC flags, unaligned or truncated code, code mapped outside the PS-X image, and overlap with an original data anchor or another executable section fail.
- The synthetic EXE must still fail the real retail MD5 selector with only a generic, path-free CLI refusal.
- Original v130-v135 native PCSX ReARMed VBlank/Unai and private-file tests remain part of the full GCC/Clang workflow.

### Local use

With your user-owned pinned original US EXE and matching extracted private MIPS ELF, both mode 0600 in a private directory:

```sh
python3 -m tools.analyze_map02_v136_original_code_sections \
  /private/original/SLUS_004.47 \
  /private/original/extracted-mips.elf
```

Only coarse diagnostic counts and explicit nonproof flags appear in the response. Original retail input is **never** uploaded to GitHub Actions.

- actual_original_mips_execution_verified: false
- retail_map02_frame_or_gpu_runtime_verified: false
- ps1_hardware_parity_verified: false
- nintendo_switch_hd_parity_verified: false
