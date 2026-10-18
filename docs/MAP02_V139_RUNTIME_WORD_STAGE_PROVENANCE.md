# MAP02 v139 — exact native MIPS SW words and four stage-boundary checks

Stacked on [v138 Draft PR #130](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/130), confirmed **32/32 GitHub Actions green**. GCC and Clang each ran a self-authored synthetic PS-X executable inside the real pinned PCSX ReARMed interpreter, observing all 19 expected MIPS SW PC/MMIO-class matches, with a compulsory corrupted-witness refusal.

## Additional runtime source binding

Stage v138 confirmed the *program counters* and destination register classes of executed MIPS SW instructions. However, two different valid SW instructions could occupy the same counter and target class if their operands, offsets or source registers were modified. The new v139 verifier compares the **entire 32-bit instruction word** in `regs->code` at each actual MMIO store to the unmodified MIPS program words independently generated in `make_map02_v129_four_vblank_exe.build()`.

The ordered codeword table is derived by indexing exactly the source-authored PS-X EXE payload at each v138 independently classified address. Every word must remain a genuine MIPS I SW (opcode 0x2b) and match the generated instruction tuple. The native check also validates the cumulative number of observed MMIO stores after each of four actual `psxCpu->ExecuteBlock` stages: initial setup and three GPU DMA2 phases.

- `tools/apply_map02_v139_mips_word_stages.py` patches the **same opt-in** pinned native `psxMemWrite32` observer without changing PS1 program bytes, simulated registers, GPU, DMA, cycles or VBlank.
- New `--vh139-codewords` requires `--vh138-interpreter-pc` and the existing source-authored `--vh129-vblank-04` run. The five legacy profiles remain unchanged when this opt-in flag is absent.
- A second native process adds `--vh139-corrupt-word-witness`: it deliberately flips one bit of the observer's *expected* instruction word for a single MMIO store, leaving actual emulation unmodified. Exit code **49** and `VH139_NATIVE_WORD_REFUSED` are required, and success text is forbidden.
- Positive native execution requires `VH139_NATIVE_MIPS_WORDS_PASS matched=19 stages=4 exact_words=19 original_retail=0` as well as the earlier `VH138_NATIVE_INTERPRETER_PC_PASS` and genuine four-VBlank/Unai proof.

### Independent negative controls

`tools/check_map02_v139_native_words.py` generates a separate C11 test compiling the exact source-derived observer under GCC and Clang with bounds/undefined-behavior sanitizers. One complete ordered execution must pass. Four mutations must fail: a changed SW instruction with the *same opcode* and PC, flipped expected word, omitted DMA stage checkpoint, and incorrectly numbered checkpoint. Python tests independently guard the original MIPS bytecode table, original native GPU/VBlank oracle call counts and opt-in CI coverage.

### Strict scope

Every positive run in public CI uses only the independently authored **synthetic** PS-X EXE. No original `SLUS_004.47`, extracted retail MIPS ELF, encrypted/packaged game resources or VRAM image is published. This gives stronger proof about **which source-authored instructions were executed in the pinned emulator**; it still does not prove that real Vandal Hearts MAP02 loaded, which code paths it took or whether PS1/Nintendo Switch HD graphics are equivalent.

- original_retail_MAP02_executed: false
- original_MAP02_graphics_captured: false
- physical_PS1_parity_verified: false
- Nintendo_Switch_HD_parity_verified: false
