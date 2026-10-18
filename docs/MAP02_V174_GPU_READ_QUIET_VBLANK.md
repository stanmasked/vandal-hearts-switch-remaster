# MAP02 v174 — reject unexpected GPU reads during real MIPS VBlank waits

This stage extends [v173](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/192), which independently passed 66/66 GitHub workflows, with a separate read-only observer in pinned PCSX ReARMed `psxMemRead32`.

## New provenance check

- The previously attested self-authored `VH78SYN!` executable still drives four internal `psxRcntUpdate()/GPU_vBlank(1,0)` transitions using 512-instruction MIPS NOP/jump waits.
- v173 forbids MIPS guest `GP0`/`GP1` **writes** during each wait. v174 also forbids interpreted guest `GP0`/`GP1` **reads** at 0x1f801810 and 0x1f801814, including KSEG aliases, while permitting ordinary CPU RAM reads.
- The observer is installed before the original 32-bit PCSX read implementation and does not alter its return value. Each new read-window observer arms after v173 and disarms with the same four VBlank boundaries before VRAM readback.
- The positive path must retain all v173/v172 provenance and 595 native Unai samples per phase (2380 total).

Expected genuine native marker for both GCC and Clang (requires CI confirmation):

`VH174_GUEST_MIPS_VBLANK_READ_QUIET_PASS windows=4 forbidden_gp0_gp1_reads=0 vblanks=4 samples=2380 native_psxcounters=1 original_retail=0`

## Native negative

A test-specific copy of the same self-authored signed synthetic PS-X EXE replaces **only the first wait NOP** with `LW t1,0(t0)` (`0x8d090000`). This causes a guest GPU-register read during genuine interpreter wait execution. The real pinned native emulator must exit **80** with `VH174_VBLANK_WAIT_READ_REFUSED phase=0 forbidden=...`, without any v174 or v173 positive marker.

Compiled-C GCC and Clang regressions independently cover four clean windows, GPU port reads, KSEG aliases, incorrect phase arming and ordinary RAM reads. Both native GCC and Clang must pass before claiming the stage complete.

## Limits

This verifies software-emulator-internal VBlank and self-authored synthetic MIPS/GPU data only. It does **not** assert original retail Vandal Hearts MAP02 frame parity, PlayStation hardware video timing, Nintendo Switch output, or a playable remake. No private game assets are uploaded, and the production engine is unchanged.
