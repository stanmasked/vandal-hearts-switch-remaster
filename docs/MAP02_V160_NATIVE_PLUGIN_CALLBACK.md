# MAP02 v160 — actual native GPU plugin callback entry and return

Stacked on v159 [Draft PR #169](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/169). v159 still requires CI confirmation on its own head.

The synthetic fifth PS1 MIPS instruction is source-authored SW to GP0. Existing observers prove the exact instruction reached `psxMemWrite32` (v158) and then the `psxHwWrite32` GPU dispatch immediately before `GPU_writeData` (v159).

v160 adds a third, logically independent opt-in witness: immediately before the synthetic five-instruction run, it saves the currently installed `GPU_writeData` plugin function pointer, replaces it temporarily with a forwarding diagnostic, and counts the entry and return of that diagnostic callback. The diagnostic forwards exactly the received word to the original handler, unmodified; no additional packet, GPU call, framebuffer operation, allocations, locks, I/O or synthetic frame is introduced. The prior function pointer is restored before plugin shutdown, and pointer tampering fails closed.

Expected authentic **synthetic native** markers:

- `VH160_NATIVE_PLUGIN_CALLBACK_PASS entered=1 returned=1 original_retail=0`
- `VH160_NATIVE_FIFTH_CALLBACK_REFUSED entered=0 returned=0 original_retail=0` for a deliberately mutated fifth opcode (expected exit 62).

These are added to, not substituted for, v158 and v159 witnesses. Standalone GCC/Clang C fixture checks exact forwarding, saturated duplicate observation, invalid data, no callback on mutation, reinvocation, restoration and replacement detection. Full pinned PCSX native CI is wired for both compilers and original older regressions.

## Limits

A callback's entry and return **do not** prove that the GPU plugin consumed the packet fully, changed GPU state, rasterized pixels, captured MAP02, played an original retail disc, or achieved HD parity with Nintendo Switch. Public tests use only generated synthetic input. No user-owned PS1 files, retail MIPS instructions, original disc, textures or frame captures are checked into GitHub.

Keep this PR Draft while all new native CI jobs are pending.
