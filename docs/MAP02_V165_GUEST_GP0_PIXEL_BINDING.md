# MAP02 v165 — exact interpreted MIPS GP0 packets bound to Unai VRAM deltas

## Purpose

Stage v164 demonstrated five source-authored interpreted PS1 MIPS draw stages
with exactly 16 changed 15-bit VRAM pixels and 20 unchanged border pixels per
stage. Stage v165 tightens causality: it witnesses **each exact 32-bit GPU
packet word** arriving through gpulib's genuine `GPUwriteData` queue append
*while* that particular CPU stage executes. A synthetic-only observer then
pairs the exact packet with the existing stage PC, RAM marker, GPU state
sampling and VRAM halo.

The only input image is the independently self-authored, deterministic
`V121_SYNTHETIC.EXE`. No retail Vandal Hearts code or assets are used.

## Sequence, bounded observation and fail-closed checks

Each of five interpreted guest-MIPS draw stages must produce, in order:

1. GP0(60) solid rectangle command and specified 24-bit RGB color.
2. XY position word `0x00a00028` (X=40, Y=160).
3. Size word `0x00040004` (width 4, height 4).

The five colors are source-authored: `0x600000ff` (red),
`0x6000ff00` (green), `0x60ff0000` (blue),
`0x6000ffff` (cyan), `0x600000ff` (red).

After the *original* gpulib command-buffer assignment the observer compares
the arriving CPU-submitted word with the expected word and the unmodified
stored buffer tail. Wrong, extra, missing and reordered words cannot pass.
The observer must see exactly three words per MIPS phase, and disarms **before**
the GPU VRAM readback. Only after the original v121 stage PC and MIPS-written
RAM marker gates, the v164 per-stage 6×6 halo and the existing five-phase
color return can a success marker be produced.

Expected authentic pinned PCSX ReARMed/Unai GCC and Clang marker:

`VH165_GUEST_MIPS_GP0_VRAM_BOUND_PASS phases=5 gp0_words=15 pixels_changed=80 border_unchanged=100 host_draws=0 original_retail=0`

Corrupting the signed synthetic EXE tag in the separate negative run must
produce `VH121_EXE_REFUSED` (exit 37) and never the v165 PASS marker.
Independent GCC/Clang C fixtures cover the exact original append,
out-of-order, wrong-word, missing-word, duplicate and double-arm refusal,
without replacing the original GPU read/write implementation.

## Explicit limits

This is **synthetic guest-interpreted PS1 MIPS code**, not commands
reconstructed or authenticated from the original retail MAP02 engine.
It is not a complete Vandal Hearts battle, a Nintendo Switch renderer test,
a released game or visual parity proof. The separate v158-v162 fifth E3
state-only instruction remains non-rasterizing. This experiment explicitly
uses the older self-authored v121 rectangle program and does not claim that
the v158 fifth E3 instruction produced any pixels.

All private or user-owned original game data stays outside public GitHub.
