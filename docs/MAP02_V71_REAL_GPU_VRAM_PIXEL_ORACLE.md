# MAP02 v71 — real PCSX GPU VRAM readback versus independent pixel oracle

## New proof boundary

Earlier v70 executed an **original synthetic MIPS PlayStation executable**
inside the real pinned PCSX ReARMed CPU interpreter. It observed
real CPU GPU MMIO writes and entry/return from real GPU plugin callbacks.
That established command delivery, **not renderer output**.

v71 adds a fundamentally different assertion: after MIPS issues drawing
commands, **GPUfreeze(SAVE=1)** in the actual PCSX GPU plugin flushes
pending GPU commands, synchronizes the renderer, and exposes the
plugin's native 1024×512 16-bit VRAM buffer. The diagnostic path
compares independently calculated 15-bit BGR pixels at 105 fixed
positions against that buffer, counting every mismatch.

The test executable is independently generated, 4 KiB long (2048-byte
PS-X EXE header and 2048-byte self-authored MIPS-I text section);
there is no commercial BIOS, Sony SDK, Vandal Hearts ROM, texture,
sprite, map or original game data anywhere in these tests.

## Synthetic draw program

The 32-bit MIPS CPU first writes GP1(01) FIFO reset to its real
0x1F801814 register, then submits this exact GP0 sequence through
0x1F801810:

- GP0 E3 = 0, E4 = 0x7FFFF, E5 = 0: full drawing area / offset zero.
- GP0 E6 = 0: clear mask update/check controls.
- GP0 0x600000FF + position (16,16) + size (4,4):
  draw a flat red rectangle with BGR555 value **0x001F**.
- GP0 E6 = 1: write mask bit 15 in pixels when drawing.
- GP0 0x60FF0000 + position (24,16) + size (4,4):
  draw a flat blue rectangle with BGR555 value **0xFC00**,
  including the required mask bit.
- GP0 E6 = 2: respect existing mask bit on destination pixels.
- GP0 0x6000FF00 at the same (24,16), size (4,4):
  attempt a green overwrite, which MUST NOT alter masked blue pixels.

The program stores completion marker 0x70000001 to emulated
RAM 0x80011000, then branches to itself at 0x800100E0.

## Independent VRAM oracle

For x=15..29 and y=15..21 (15×7 = 105 pixels), v71 expects:

| Classification | Pixel count | Native VRAM BGR555 |
|---|---:|---|
| Red rectangle | 16 | 0x001F |
| Masked blue rectangle | 16 | 0xFC00 |
| Unpainted surroundings | 73 | 0x0000 |

**Crucial:** this is not a screenshot hash or callback-count test.
A plugin that returned without drawing pixels, drew the wrong color,
ignored mask bit 15 or incorrectly overwrote masked blue fails even
when all GP0 callbacks and MIPS CPU markers match.

The independent oracle is fixed in the diagnostic C checks and in
Python unit tests, rather than being calculated from observed plugin
pixels. The sample does not include any original MAP02 pixel data.

The exact source path is the pinned upstream
[notaz/pcsx_rearmed@8b6c163575e6ce9a0537553e0d4ed4225315955e](https://github.com/notaz/pcsx_rearmed/tree/8b6c163575e6ce9a0537553e0d4ed4225315955e).
In `plugins/gpulib/gpu.c`, `GPUfreeze(1)` flushes/synchronizes
pending commands and returns a VRAM pointer. The test uses the
unchanged plugin GPU code, not a mock GPU implementation.

## CI and privacy

Full GCC and Clang builds of the actual instrumented native PCSX
ReARMed executable still run all inherited v45–v70 original-C
GPU/PRS/GTE/OT/VHT1/GP0/GP1 provenance and privacy regressions.

The v71 smoke test runs the newly generated synthetic EXE through
the real MIPS interpreter and requires `VH71_VRAM_ORACLE_PASS`
with 105/105 exact expected pixels. It checks separately that the
v68 CPU GPU input log contains the 15 original GP0 words and GP1(01),
and that the original v69 GPU callback wrapper confirms 15 direct
GPUwriteData callbacks, at least one GPUwriteStatus callback.

An EXE without `VH71SYN!` is refused; a negative synthetic variant
that changes only the red color word but retains a valid marker
**must fail the pixel oracle**. A test which intentionally changes
GP0 mask control bit must also fail. This prevents interpreting
successful CPU execution alone as successful GPU rasterization.

CI publishes only generated synthetic diagnostics and aggregate
results. **Never publish retail GPU RAM, real-game VRAM snapshots,
copyrighted game resource material or private MMIO captures.**

## Evidence boundaries

- `synthetic_cpu_gpu_vram_oracle_verified`: true only if the native CI
  real-emulator GPU pixel test actually passes.
- `retail_ps1_hardware_pixel_parity_verified=false`
- `original_retail_MAP02_verified=false`
- `HD_replacement_approved=false`.

One synthetic 4×4 pixel scene demonstrates a *small, controlled*
subset of rasterization, not PlayStation-complete GPU behavior.
Original MAP02, textured FT4, semitransparency STP/ABR, geometry,
Nintendo Switch gameplay and the retail HD replacement are separate
unverified milestones.

v71 remains a stacked draft PR over v70; `main` unchanged.
