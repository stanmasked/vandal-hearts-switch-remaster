# MAP02 v142 — real native PCSX MIPS writes to private JSONL, source-bound offline

Stacks onto [v141 Draft PR #133](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/133), confirmed **35/35** CI workflows. The v141 offline verifier accepted an arbitrary user-supplied JSONL of alleged original MIPS GPU/DMA writes; it could cross-check source identity and code words, but **not authenticate the claim producer**.

This stage creates the **first controlled interpreter-origin receipt** in our synthetic experiment:

- `tools/apply_map02_v142_native_private_mmio_receipt.py` instruments the actual pinned PCSX ReARMed `psxMemWrite32` path, after the unchanged v138–v140 source checkers. It records the exact 19 ordered native MIPS `SW` tuples: program counter, fetched 32-bit instruction word, full MMIO effective address and full stored value.
- The native observer is **opt-in** and only starts after the source-authored v129 synthetic PS-X program has passed the existing private SHA-256 / execution initialization constraints. It never changes PS1 clock, CPU registers, GPU commands, DMA memory or VBlank. A fixed-capacity buffer in the native process is sealed to a file only after the same four CPU stages.
- The private receipt is created with `openat(O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC, 0600)` inside an owned `0700` directory specified by `VH142_PRIVATE_RECEIPT_DIR`. The directory's leaf must not be a symlink; all **ancestors** must also be controlled by the operator (GitHub CI creates the path locally under `proof/private`). Existing files are not overwritten. The writer bounds and checks every line and synchronizes bytes with `fsync`. Individual PCs, words, GPU values, private paths and receipt lines never appear in console output or uploaded artifacts.
- `tools/check_map02_v142_native_private_receipt.py` privately reads that file with the two-pass, no-follow v141 reader and validates all 19 actual native tuples against an **independently constructed** v129 source-authored PS-X EXE and byte-matched v136 ELF32 MIPS code section. It uses the v141 whole-PC/codeword/MMIO-class verifier and then requires full exact effective-address/value equality to the independent synthetic source program. A second private read detects file changes.
- **Native positive run** uses `--vh129-vblank-04 --vh138-interpreter-pc --vh139-codewords --vh140-mmio-values --vh142-private-receipt`. It must print `VH142_NATIVE_PRIVATE_RECEIPT_PASS events=19 source=synthetic emulator=pcsx original_retail=0`, then the older v140/v139/v138/v129 PASS statuses. Its private receipt must produce `VH142_NATIVE_SOURCE_EXE_ELF_RECEIPT_PASS`.
- **Native negative control** uses the same flags plus `--vh142-corrupt-receipt`. It corrupts **one saved claim's MIPS instruction word only**, leaving the actual emulated CPU/GPU/DMA program unchanged. The native program still produces its private file and normal synthetic GPU evidence, but the *independent* v141-source/EXE/ELF verifier must reject this corrupted receipt with `VH142_CORRUPTED_NATIVE_RECEIPT_REJECTED`. Treating it as accepted is a hard CI failure.
- Native source files, actual receipts and user-owned code are not committed or uploaded. The public artifact upload remains exclusively `proof/public/`, while all private JSONL stays under `proof/private/`.

## Strict limitations

The positive source-generated native trace now has an identifiable producer **within this pinned, instrumented synthetic test executable**, because it was recorded inside the actual executing PCSX interpreter and inspected immediately by the same job. This is *not cryptographically authenticated attestation*, not a verified general-purpose runtime collector, and not any retail trace. The v141 external JSONL checker continues to mark `trace_producer_authenticated=false` for general inputs. The original retail `SLUS_004.47` has **not** been supplied or executed in public CI.

- original retail MAP02 execution: **unverified**
- original PS1 frame capture: **unverified**
- physical PlayStation hardware comparison: **unverified**
- Nintendo Switch HD rendering parity: **unverified**

## Public tests

Standalone GCC+Clang workflow checks protected output rules, actual interpreter-hook source, unchanged old VBlank/GPU code, full synthetic receipt round trip, exact codeword/data/address tamper rejection and negative-mode false-acceptance refusal. Full native GCC+Clang jobs run the two extra pinned PCSX processes after all prior v129/v138–v140 stages.
