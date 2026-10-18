# MAP02 v162 — actual gpulib command parser and bounded flush

Scope: diagnostic only; five self-authored synthetic PS1 MIPS opcodes, **no retail data**.
Prerequisite: v161 (exactly one native GPUwriteData command buffer append),
v160 (exactly one callback entry and return), v159 and v158.

The pinned PCSX ReARMed gpulib GPU parser is instrumented **after** the original
`cmd = LE32TOH(data[pos]) >> 24;` in `do_cmd_buffer`, and the original
`left = do_cmd_buffer(...)` in `flush_cmd_buffer`. The observer requires the
single exact `0xe3000000` E3 word from `gpu.cmd_buffer` with `count=1`,
`pos=0`, and one consumed word (`left=0`).

Only inside the opt-in native synthetic MIPS test, call the already-loaded
`GPU_readStatus` callback. In pinned gpulib this causes a genuine
`flush_cmd_buffer` if there is pending input. The original parser and native
read-status operation remain intact; the diagnostic merely counts and checks.

Positive native GCC/Clang evidence must be:
`VH162_NATIVE_GPULIB_PARSE_FLUSH_PASS parsed=1 flushed=1 original_retail=0`.
Mutated fifth instruction must not enqueue or parse any synthetic word:
`VH162_NATIVE_FIFTH_PARSE_REFUSED parsed=0 flushed=0 original_retail=0`.

Checks include parser source anchors, a real C compiled parser/flush fixture,
one valid E3, duplicates, wrong word, stale command buffer, and missing SW.
All prior v158–v161 positive/negative markers remain mandatory.

## Limits

One `E3` state command can be a redundant state update and may be skipped
inside `do_cmd_buffer` without entering `renderer_do_cmd_list`. This stage
does **not** prove the Unai renderer was invoked, pixels or VRAM changed,
or that original retail MAP02 code executed or the game runs on Switch.

The synthetic-only `GPU_readStatus` flush is explicitly triggered by the
diagnostic host harness: do not equate it with spontaneous game behavior.
Original disc/game resources and private captures remain outside public CI.
