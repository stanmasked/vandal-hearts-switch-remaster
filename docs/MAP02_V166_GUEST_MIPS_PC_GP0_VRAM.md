# MAP02 v166 — exactly 15 guest MIPS SW PCs → GP0 words → Unai VRAM

## Proof chain

Building on v165 (58/58 workflows), v166 instruments **actual native**
`psxMemWrite32`, before its existing optional v138 observer and before
the actual GPU dispatch. In a separate opt-in signed, self-authored
`V121_SYNTHETIC.EXE` run, a read-only diagnostic records each guest
MIPS `SW` instruction address and value written to physical GP0
`0x1f801810`.

Exact expected PCs are generated from the independently authored
six-stage MIPS source's five drawing stages. In each stage, word
positions 4, 7 and 10 must be exact original `sw(9,0,8)`
instructions. Pinned interpreter advances `regs->pc` by four before
calling `psxMemWrite32`, so each observed PC is compared with the
source-derived MIPS PC **plus four**. All 15 PCs are unique.

The watched stage then must satisfy existing v165 checks for **three
ordered 32-bit GPUwriteData queue words** (the exact 24-bit rectangle
color, XY X=40/Y=160 and size 4×4), plus previous v164 exact
VRAM readbacks: 16 changed pixels and 20 unchanged neighbor samples
for each of 5 distinct RGB states.

The native v166 success marker is:

`VH166_GUEST_MIPS_PC_GP0_VRAM_PASS phases=5 sw_pcs=15 gp0_words=15 pixels_changed=80 border_unchanged=100 original_retail=0`

All v164, v165 and v121 success markers remain required on the
same native test run. There is **no host-submitted drawing packet**.

## Negative proof and tests

An authenticated self-authored PS-X executable is mutated in precisely
one machine instruction: the first draw stage's `SW t1,0(t0)` becomes
`SW t3,0(t0)`. Its signed synthetic file tag is untouched, as are
all other opcodes and source-PC expectations. The native test must
refuse with exit 70 and `VH166_GUEST_SW_PC_REFUSED phase=0`
*before* treating GPU packets as authenticated. Missing/wrong PC,
wrong SW opcode, unexpected MMIO address, wrong GP0 value, duplicate
arming and incomplete three-word stages are independently exercised
by the compiled GCC/Clang C fixture.

The strict previous v165 bad-color and invalid-EXE cases also stay
in place. Source patches require unique anchored code sites.

## Boundaries

This is exclusively synthetic PS1 MIPS-originated GPU activity. No
original retail Vandal Hearts MAP02 executable was run, no true MAP02
battle screenshot was captured, no Nintendo Switch renderer was tested,
and no remaster/release readiness is asserted. No user-owned game
media, private MIPS traces or original code are published to GitHub.
