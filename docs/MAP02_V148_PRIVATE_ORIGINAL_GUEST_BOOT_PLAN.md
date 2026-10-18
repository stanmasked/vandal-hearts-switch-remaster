# MAP02 v148 — privately prepare original US PS-X entry and guest RAM plan

This Draft PR builds on [v147 PR #139](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/139), verified **41/41** GitHub Actions workflows. The v147 PCSX interpreter now has a generic 1024-event bounded native MIPS GPU/DMA collector but **retail-original boot is not yet enabled**. Exact original PS-X load address, initial PC and extracted MIPS executable segment identity have not previously been established as guest execution prerequisites.

## Added source-verified guest loader *preflight*, not boot execution

New `tools/prepare_map02_v148_original_guest_boot.py` accepts the user's **privately owned** original US `SLUS_004.47` and separately extracted matching MIPS ELF. Before producing any guest boot plan it:

- Reads both 0600 regular files via all-component O_NOFOLLOW descriptor walks, checks unchanged inode/metadata and double-reads.
- Requires the pinned original US legacy edition MD5 `596bb082a2de5f1fe977dd3d7e160b03` (**edition selector, not a cryptographic proof**), original PS-X 0x80010000 load mapping and bounded header/text length.
- Requires the same three original data anchors (MAP32, MAP35 and font) and the exact matching executable MIPS ELF .text sections from v135–v136.
- Verifies that the PS-X header's **initial PC is a four-byte instruction wholly inside one verified, file-backed ELF executable section**, and that its mapped physical address fits the PS1 2 MiB RAM.
- Validates optional GP, SP and BSS startup-header placements. Non-zero BSS must fit memory, must not overlap the loaded text and is zero-initialized in an ephemeral **2 MiB guest memory model**. The loaded image is copied only into the simulated mapped address range, and the entrypoint instruction bytes are taken from that image.
- Computes private SHA-256 of original EXE/ELF, mapped text and first verified entrypoint instruction. These private digests, guest PC and memory sizes are saved in a new **mode-0600** canonical JSON manifest `vh148-private-original-boot-plan.json` inside an owned 0700 directory with exclusive O_NOFOLLOW creation and file+directory fsync; an incomplete newly-created manifest is removed on error.
- Rereads original EXE+ELF after preparing and verifies that the stored manifest is unmodified. Neither source bytes, private file paths, hashes nor guest instruction words appear in console or public CI artifacts.

Example **local-only preflight** (do not upload owned game data):

```sh
mkdir -m 700 /private/vh148-boot
python3 -m tools.prepare_map02_v148_original_guest_boot \
  /private/original/SLUS_004.47 \
  /private/original/extracted-mips.elf \
  /private/vh148-boot
```

The success status explicitly states `runtime_executed=0 map02_rendered=0`. It is not a cartridge-ready loader or an attested PS1 boot run. The generated private manifest contains original-derived addresses/hashes and must **never** be uploaded publicly. Any failure is a coarse `VH148_PRIVATE_ORIGINAL_BOOT_PLAN_REFUSED` with no disclosure.

## Public validation

Standalone GCC and Clang jobs run **10 synthetic tests** from independently generated PS-X EXE and ELF32 MIPS with verified loaded `.text`, covering correct 2 MiB RAM relocation, exact entry opcode digest, GP/SP and BSS mapped bounds, invalid load/entry and ELF corruption rejection. The **public CLI always rejects these synthetic inputs** at the original US edition selector; it cannot be tricked into claiming synthetic content is original. The full pinned native GCC/Clang PCSX/Unai workflow also runs the preflight unit tests, retains v147 actual interpreter synthetic receipt source matching and all five four-VBlank/three-DMA2/five-Unai profiles.

### Remaining original-execution prerequisites

An original original-loader run still needs disc/BIOS/HLE startup and a bounded, termination-controlled MIPS CPU execution policy; there is no claim that a standalone PS-X EXE can reach MAP02 without game disc resources or CD/XA/VBlank services. The original assets have **not** been made available in this public CI, and **no retail game instructions or MAP02 rendering have executed**. Nintendo Switch HD parity remains unverified.

PR stays Draft; `main` unchanged until results are green.
