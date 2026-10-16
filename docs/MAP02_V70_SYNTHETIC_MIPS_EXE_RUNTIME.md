# MAP02 v70 — execute an original synthetic MIPS PS-X EXE on PCSX CPU

## What v70 tests

The previous stage proved that the complete pinned PCSX ReARMed
diagnostic frontend could initialize its PS1 emulator core, HLE
BIOS and GPU plugin with no game media. Its GPU callback harness
then used ordinary host-C functions, **not emulated MIPS CPU code**.

v70 exercises the next actual runtime boundary: it creates and
loads a brand-new **4 KiB PS-X EXE** containing hand-encoded MIPS-I
opcodes and invokes the pinned PCSX's normal interpreter to execute
those instructions. The fixture was written solely for these tests
and contains **no commercial BIOS, original Vandal Hearts code,
music, textures or images**.

The small program explicitly:

1. Builds the PS1 GPU GP0 MMIO address `0x1f801810` in register t0.
2. Writes GP0(E6) mask control `0xe6000000`.
3. Writes a 1x flat untextured rectangle GP0 packet using
   `0x600000ff`, `0x00000000`, `0x00000404` (4x4 pixels).
4. Writes the GP1(01) GPU FIFO-reset command `0x01000000` to
   GPU status/control MMIO address `0x1f801814`.
5. Writes a synthetic completion marker `0x70000001` into
   emulated RAM at `0x80011000`, then branches to itself at
   `0x8001004c`.

The PS-X EXE header is 2048 bytes (including a distinct
`VH70SYN!` marker at 0x4c). The image has a 2048-byte payload
at RAM destination/entry `0x80010000`. All opcodes are generated
from pure Python; no original game resources or Sony SDK binaries
are required.

References for hardware format:
[PS-X EXE format overview](https://www.retroreversing.com/ps1-exe)
and [PlayStation GPU specifications](https://psx-spx.consoledev.net/).

## Running the emulator CPU, not just the frontend

The pinned real PCSX ReARMed is
`notaz/pcsx_rearmed@8b6c163575e6ce9a0537553e0d4ed4225315955e`.
In the diagnostic source patch, a **new opt-in CLI flag**
`--vh70-exe-smoke` is accepted only with diagnostics enabled.
It runs after the original `Load(file)` PS-X EXE loader and
the prior actual core, HLE and plugin initialization.

This test mode requires a marker-matched user-provided PS-X EXE,
interpreter mode (`-nodrc`) and the exact start address,
then calls the genuine `psxCpu->ExecuteBlock` method **once**.
The fixture has one bounded branch to itself; the runner also
uses a host-process timeout to refuse hung emulator execution.
After the interpreter returns, the diagnostic checks both the
expected loop PC and **RAM completion marker written by CPU MIPS
instructions**, before printing `VH70_MIPS_EXEC_PASS`.

This is stricter than a static trace: CPU-to-MMIO writes are
independently observed through v68 CPU GP0/GP1 hooks and via
the actual v69 GPU plugin callback dispatch wrappers.

## GCC and Clang proof (synthetic only)

Workflow `.github/workflows/map02-v70-mips-gpu-cpu-exe.yml`
builds the full original pinned PCSX emulator with diagnostics,
generates its own 4096-byte EXE, executes it inside the emulator,
and requires these independent observations:

- Four exact CPU GPU-port GP0 input words:
  `0xe6000000`, `0x600000ff`, `0x00000000`,
  `0x00000404`.
- One matching GP1 FIFO-reset input `0x01000000`.
- At least four original GPU plugin `GPUwriteData` callback
  returns and one `GPUwriteStatus` callback return.
- No GPU linked-list DMA submissions from this fixture
  (that is a separate subsequent milestone).
- A checked interpreter PC and RAM marker, proving bounded
  CPU instruction execution reached the end.
- A deliberately altered test EXE with an invalid v70 marker
  **must be rejected**, rather than being treated as a
  genuine test program.
- All prior v45–v69 original GPU/GP0/OT/GTE/PRS/VHT1
  and privacy regressions remain mandatory.

These tests use only synthetic files. The callback event logs
contain only callback names/phases; the v68 raw GP0 observations
contain commands and remain synthetic CI fixtures.

## Local developer example

With the pinned PCSX checkout separately prepared and the
diagnostic patch applied:

```bash
python3 -m remaster.tools.make_map02_v70_synthetic_psx_exe \
  --output /private/new-v70-test.exe

SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
  VH_MAP02_V69_CALLBACK_LOG=/private/new-callback-log.jsonl \
  VH_MAP02_V66_PCSX_LOG=/private/new-gp0-input.jsonl \
  ./pcsx -novid -nodrc -nothread \
    --vh70-exe-smoke /private/new-v70-test.exe
```

Keep all trace data local. This program is synthetic and public-safe,
but any *real-game* GPU port logs and RAM dumps may contain copyrighted
data and must never be published as CI artifacts.

## Remaining trust gates

A synthetic GP0 packet delivered by the emulated MIPS CPU to a
synchronous GPU callback establishes **command delivery**, not
correct GPU rendering, VRAM output equality, hardware accuracy, or
genuine retail MAP02 provenance.

- `real_game_boot_verified=false`;
- `gpu_plugin_fifo_consumption_verified=false`;
- `gpu_rendering_or_pixel_parity_verified=false`;
- `original_retail_MAP02_verified=false`;
- `retail_gp0_provenance_verified=false`;
- `HD_replacement_approved=false`.

The stacked draft is based on v69; `main` is unchanged.
