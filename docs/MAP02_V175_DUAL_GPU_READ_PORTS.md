# MAP02 v175 — independent GPU GP0/GP1 register read provenance

Based on fully green [v174 Draft PR #195](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/195) (67/67 GitHub Actions). This diagnostic-only step distinguishes **GP0 at 0x1f801810** from **GP1 at 0x1f801814** in actual interpreted MIPS 32-bit GPU-register reads during the four genuine PCSX VBlank waits.

## What changes

- A per-port read observer is added to the pinned PCSX psxMemRead32 path, alongside the inherited v174 32-bit read and v173 32-bit write observers. It counts GP0 and GP1 independently after masking KSEG aliases.
- The per-port window is armed after the v174/v173 windows, and separately disarmed before the inherited teardown and VRAM readback. Wrong-phase arming, repeat arming and double disarming fail closed.
- The synthetic native positive still requires four actual internal psxRcntUpdate()/GPU_vBlank(1,0) events, the same attested 72 MIPS GP0 writes + 3 GP1 writes outside waits, and all 2380 native Unai pixel samples.

Expected real GCC and Clang positive marker (pending CI):

VH175_GUEST_MIPS_VBLANK_PORTS_PASS windows=4 forbidden_gp0=0 forbidden_gp1=0 vblanks=4 samples=2380 native_psxcounters=1 original_retail=0

## Independent genuine MIPS negative

The same self-authored tagged VH78SYN! EXE has exactly one first wait-pad MIPS NOP changed to LW t1,4(t0) (0x8d090004), forcing a GP1 status-register read in the actual interpreter. The native emulator must refuse with exit 81 and the marker:

VH175_VBLANK_GPU_READ_PORT_REFUSED phase=0 gp0=0 gp1=...

before any v175/v174 native pixel PASS. The inherited v174 GP0 native negative and all other scenarios must remain successful. Separate compiled GCC/Clang C fixtures test both registers, aliases, normal guest RAM, four clean windows and wrong arm/disarm transitions.

This is evidence only for native software-emulator internal VBlank and synthetic self-authored MIPS/Unai behavior. It does not prove retail Vandal Hearts MAP02 execution, original PS1 hardware display timing, Nintendo Switch output or a playable remake. No private original game assets are published.
