# MAP02 v78 — real PCSX ReARMed VBlank-start events and GPU VRAM readback

## Change from v77

v77 executed four separate synthetic MIPS `ExecuteBlock` calls inside
one actual pinned PCSX ReARMed process and matched 2,380 native GPU VRAM
samples, but the checkpoints were **host-directed CPU branch boundaries**.
They were explicitly **not video VBlank events**.

v78 retains all four distinct CPU stages and the independent per-phase
native VRAM oracle, but observes the **real emulator's original
`psxRcntUpdate()` VBlank-start callback**. In pinned upstream
`libpcsxcore/psxcounters.c`, when `hSyncCount==VBlankStart`, the core
calls `GPU_vBlank(1,0)` and raises the VSync IRQ. A read-only probe
is inserted **immediately after the original callback**; it records
only an event count, last emulated CPU cycle, `frame_counter`, and
`hSyncCount`.

Upstream commit pin:
[notaz/pcsx_rearmed@8b6c163575e6ce9a0537553e0d4ed4225315955e](https://github.com/notaz/pcsx_rearmed/tree/8b6c163575e6ce9a0537553e0d4ed4225315955e).

**No call to `GPU_vBlank()` is added by the test**. No
`psxRegs.cycle`, `hSyncCount`, IRQ flags, event counters or
`frame_counter` is manually incremented to impersonate a frame.
The observer merely increments the v78 private diagnostic event count
after the original emulator event has occurred.

## Interpreted MIPS as the clock

The original v77 scene is reused without changing a single CPU or
GP0/GP1 command word in its four functional stages.

A new 10,240-byte all-synthetic PS-X EXE holds an extra bounded
program segment: **512 actual MIPS-I NOPs** followed by a jump
back to the start of that segment. After each scene stage, the native
diagnostic frontend temporarily sets the **emulated program counter**
to this otherwise unreachable MIPS wait segment and repeatedly invokes
`psxCpu->ExecuteBlock()`. Each call executes the full NOP segment on
the genuine CPU interpreter and calls normal cycle/event handling
on its branch.

The frontend checks the real observed VBlank event count. When the
original `GPU_vBlank(1,0)` callback has increased the diagnostic
count **by exactly one**, it restores the CPU PC to the next synthetic
scene stage. The wait loop is bounded to 8,000 iterations per stage;
a missing VBlank or anomalous PC transition fails closed. It also
checks monotonic CPU cycles, nonzero horizontal sync, and consecutive
`frame_counter` values across observed VBlank starts.

The four snapshots are therefore **synchronized to four distinct
genuine emulator VBlank-start events**. They are not claimed to be
real PlayStation hardware video timestamps, and the MIPS phase
content remains source-authored rather than retail MAP02.

## Native scene and oracle

The actual original PCSX GPU plugin receives GP0(A0) 4bpp texture
and CLUT uploads and the following four stages:

| Phase | MIPS GPU action | State and native VRAM |
|---|---|---|
| 0 / setup | Blue backdrops + E1 ABR1, E2 horizontal window, E6 mask bit | six blue 4×4 tiles; persistent E1/E2/E6 |
| 1 / persist | Two draws without reprogramming E1/E2/E6 | newly red-blended and bit15-marked tiles |
| 2 / FIFO reset | GP1(01), then identical draws | GPU state retained, matching phase 1 colors |
| 3 / full reset | GP1(00), restore only drawing bounds, then draws | E1/E2/E6 reset, old VRAM retained, different new pixels |

At each **actual VBlank-start event**, the diagnostic calls the
original `GPU_freeze(SAVE=1)` and compares the native 1024×512
BGR555 VRAM buffer against an independent fixed oracle. A rectangle
with X=39..123 and Y=159..165 has exactly **595 pixels**, including
96 painted pixels and 499 required untouched guards, so **four VBlank
events correspond to 2,380 separately verified pixel comparisons**.

The genuine PCSX GPU control-register freeze data must additionally
match each checkpoint's expected GP0(E1), GP0(E2), GP0(E6). GPU
register mismatches are never accepted. The GP0/GP1 MMIO input
sequence and original loaded GPU callback evidence are also verified
separately.

## Fail-closed assertions

The real GCC and Clang CI suite runs the complete pinned emulator
and seven fully synthetic MIPS EXE variants:

- Correct 10,240-byte executable must yield four real source VBlank
  events, four consecutive frame indices, four native GPU snapshots,
  and exact **2,380/2,380** pixel agreement.
- Altered GP1(01) FIFO reset → GP1(00) full reset, and conversely
  altered GP1(00) full → FIFO-only, must each fail at the *actual
  VBlank-synchronized pixel comparison*.
- Changing E1, E2, E6 independently or the final rectangle color must
  each cause a native VRAM mismatch and be rejected.
- An EXE with an invalid synthetic identity marker is refused without
  executing the test.

The entire inherited v45–v77 native public PC-port GPU/PRS/GTE/OT/
VHT1/MIPS/PSX GPU and provenance/privacy matrix is also rerun under
both GCC and Clang, along with new v78 unit tests. CI publishes
only synthetic fixture hashes, aggregate status, and authored test
logs. Original retail game data, private VRAM and ROM material stay
private and uncommitted.

## Scope, authenticity and switch HD gate

This is real **emulator-origin VBlank callback observation** in a
pinned PCSX version, not a fabricated host checkpoint. Yet it does
**not** establish physical PS1 VBlank fidelity, actual retail MAP02
frame identification, original scene render/texture authenticity,
native Nintendo Switch frame timing, or HD-replacement readiness.

- `emulator_vblank_start_hook_installed=true` is a source
  instrumentation fact, not a proof of a successful run by itself.
- `physical_ps1_vblank_verified=false`.
- `retail_video_frame_correspondence_proven=false`.
- `original_retail_MAP02_verified=false`.
- `HD_replacement_approved=false`.

PR remains **DRAFT** stacked on v77, without modifying `main`.
