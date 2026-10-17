# MAP02 v131 — local private PS-X EXE MIPS GPU/DMA register candidate inventory

This stage is stacked on [v130 Draft PR #121](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/121). It does not reuse or claim the original retail CD/GPU/MAP02 runtime witnesses from the separate local PC-build research.

## Purpose

Earlier stages v125–v130 verified genuine MIPS-originated linked-list GPU DMA commands, five ordered Unai post-draw observations, and 0–4 real VBlank callbacks **inside a source-authored synthetic PS-X EXE**. That evidence says nothing about whether the original retail PS1 program performs the same writes during MAP02.

The new tool `tools/analyze_map02_v131_private_mips_mmio.py` is a **read-only, local-only static candidate inventory**. Given a user-owned and lawfully obtained PS-X EXE, it checks the 2048-byte EXE header, bounds the declared MIPS text and entry point to PS1 RAM, and scans source MIPS instructions for conservative constant-propagated 32-bit stores to exact GPU/DMA memory-mapped hardware addresses.

The scanner recognizes LUI, ORI, ADDI/ADDIU, ANDI/XORI, SW and a small subset of register-register operations. It invalidates constants across branch/jump boundaries and unknown instructions. It does **not** execute MIPS, disassemble all possible code paths, identify MAP02 gameplay, decode GPU packet values or certify that a static instruction is reachable.

Six separate MMIO candidate classes are counted: DMA2 MADR, BCR, CHCR, DMA DPCR, GPU GP0 and GPU GP1. A narrower seventh count records a CHCR store where the source register is statically known to contain the PS1 linked-list DMA flag `0x01000401`. A candidate count is **not** proof that this DMA transfer actually ran.

## Local use, not CI use of the original disc

Users may run locally with their **own** PS1 executable after ensuring it is a regular, single-link, current-user-owned file accessible only to that user (`chmod 600`):

```sh
python3 -m tools.analyze_map02_v131_private_mips_mmio /path/to/private/SLUS_004.47
```

The tool opens the input with no-symlink protection and performs two bounded complete reads of the same file descriptor. Both reads must match by SHA-256 internally, with unchanged inode, size and nanosecond timestamps. The SHA-256 value and input pathname are never printed. No EXE/ROM bytes, MMIO addresses, instruction payloads or private paths are exported. Only class counts and explicit unverified flags appear in JSON. Failure uses a generic path-free refusal marker.

Public CI never obtains the user's retail executable. Instead, it uses the already source-authored 10,240-byte v129 EXE, verifying three candidate DMA2 MADR/BCR stores, six CHCR stores (including three literal linked-list values), and separate GP0 command sites. Tests also reject malformed headers, owner/mode/link violations, symlinks, truncated binaries, unrecognized MMIO addresses, register clobbers and control-flow misclassification.

## Same-binary synthetic static/runtime binding

The pinned GCC/Clang PCSX ReARMed workflow also runs the **v131 static
candidate inventory on the exact v129 synthetic EXE that is then passed
to each of the five real-VBlank emulator runs**. The generated EXE is
restricted to mode 0600; its SHA-256 is recorded only in a private CI
file and rechecked before and after each of the five native processes.
The aggregate public v129 report records only that both bounded audits
succeeded; it does not contain the EXE hash, raw MIPS words or VRAM data.
This tightens the synthetic regression without confusing its generated
EXE with user-owned retail gameplay or validating retail MAP02.

## Explicit evidence limits

The static inventory cannot assert that the original user-owned EXE is the correct region/version, that any instruction executed, that any executable refers to MAP02, that any VRAM pixels match, or that a frame runs on original hardware. Connecting it to the separate original CD/GPU branch requires independent provenance checks and private runtime evidence, not matching public counts.

- retail_map02_scene_identity_verified: false
- retail_map02_gpu_rendering_verified: false
- physical_ps1_equivalence_verified: false
- nintendo_switch_hd_parity_verified: false
