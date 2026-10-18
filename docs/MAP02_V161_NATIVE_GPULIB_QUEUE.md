# MAP02 v161 — genuine gpulib GPUwriteData queue append

## Scope

This stage builds on v160's native GPU plugin callback entry/return, not on
retail game code. Pinned upstream: notaz/pcsx_rearmed at commit
8b6c163575e6ce9a0537553e0d4ed4225315955e.

The native core's fifth self-authored synthetic MIPS instruction executes SW
to GP0 (0x1f801810), with word 0xe3000000. The source-bound witness
is inserted immediately after this existing line in plugins/gpulib/gpu.c:

    gpu.cmd_buffer[gpu.cmd_len++] = HTOLE32(data);

It only counts after confirming the input word, exact stored word, and
monotonic cmd_len growth from the point the observer was armed. It refuses
duplicates and altered commands, malformed indices, arming twice, stale native
source anchors, and a changed fifth MIPS instruction. The original append is
not replaced or intercepted; the observer is inactive in ordinary operation.

Expected full native GCC/Clang results:

- Positive synthetic guest: VH161_NATIVE_GPULIB_QUEUE_PASS stored=1 original_retail=0.
- Mutated fifth MIPS opcode: VH161_NATIVE_FIFTH_QUEUE_REFUSED stored=0 original_retail=0.
- All v158, v159 and v160 markers must remain present.

The independent v161 GCC/Clang C fixture compiles the original append together
with the new witness and tests no-observer behavior, exactly-one success,
duplicates, wrong data, missing callback, invalid index and double-arm refusal.

## Explicit non-claims

A GPUwriteData call buffers GP0 input. Its return and a valid append do not
prove that flush_cmd_buffer, do_cmd_buffer, renderer_do_cmd_list or Unai
polygon rasterization ran. This stage does not claim VRAM mutation, image
display, Nintendo Switch HD output, a rendered MAP02 frame, or execution of
any retail PS1 game data.

Public CI uses only self-authored synthetic instructions; original user-owned
game media and confidential captures stay outside GitHub.
