# MAP02 v173 — no unexpected MIPS-origin GP0/GP1 writes during native VBlank waits

The previous [v172](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/191)
passed 65/65 workflows, independently establishing four **actual internal
PCSX ReARMed** `psxRcntUpdate()/GPU_vBlank(1,0)` events with
source-attested 72 guest-MIPS GP0 writes, three GP1 commands and
2380 native Unai VRAM pixel samples.

## Stronger provenance boundary

A separate diagnostic-only v173 native `psxMemWrite32` observer is
armed for each of the four **512-MIPS-NOP/jump wait intervals** after
the GP0/GP1 source observer has completed that CPU phase. The native
PCSX emulator advances its own cycle counter and VBlank count by
executing the self-authored wait pad. The new observer watches the
true memory-writer path and **counts any guest writes to GPU MMIO
GP0 (0x1f801810) or GP1 (0x1f801814)**. It does not change CPU
instructions, native counters, interrupts, GP0 packets or VRAM.

After each genuine VBlank edge, **before GPUFreeze/readback**, the
observer disarms and requires exactly zero forbidden MMIO writes.
The original, independent v172 source attestation and four separate
595-pixel Unai GPUFreeze oracles still must succeed.

Expected native marker (GCC AND Clang):

`VH173_GUEST_MIPS_VBLANK_QUIET_PASS windows=4 forbidden_gp0_gp1=0 vblanks=4 gp0_words=72 gp1_writes=3 samples=2380 native_psxcounters=1 original_retail=0`

## Native negative

A deliberately altered **self-authored** v78 PS-X EXE preserves the
unique `VH78SYN!` tag and the entire GPU source program. The only
mutation replaces the *first* wait-pad MIPS NOP with
`SW t1,0(t0)`, resulting in an unexpected real GPU-port write
while the emulator executes the loop. Actual native GCC and Clang
must return code 79 with
`VH173_VBLANK_WAIT_MMIO_REFUSED phase=0 forbidden=...`
instead of crediting any valid v173 pixel marker.

Standalone compiled GCC+Clang fixtures separately require all four
clean windows to pass, reject any stray GP0 or GP1 write, reject
double arming and wrong disarm phase, and ignore ordinary guest RAM.

## Limitations

The VBlank events are genuine **software-emulator** callbacks,
*not* measured physical PS1 or Nintendo Switch video. All MIPS
instructions, textures, palettes and resulting rectangles are
self-authored synthetic assets. No original Vandal Hearts retail
MAP02 game executable, original frame, HD parity, Switch output,
or playable remake is established. No original game media or
private traces are published to GitHub.
