# MAP02 v176 — detect narrow MIPS GPU MMIO during real VBlank waits

Builds on fully green [v175 Draft PR #197](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/197): 68/68 successful GitHub Actions, both pinned native PCSX ReARMed/Unai GCC and Clang.

## Scope

The existing 32-bit observers check GP0/GP1 reads and writes during four genuine internal PCSX VBlank intervals, but they cannot independently rule out 8- and 16-bit interpreted guest accesses.

v176 adds diagnostic-only observers to four original PCSX memory accessors: psxMemRead8, psxMemRead16, psxMemWrite8 and psxMemWrite16. The observer counts GP0 (0x1f801810-0x1f801813) and GP1 (0x1f801814-0x1f801817) separately for each width and read/write direction, with KSEG aliases normalized. It leaves the emulated read return values, GPU state, guest CPU, native counters and VRAM unchanged.

The four-window observer is armed after the v173-v175 sentinels, and disarmed before their teardown. Wrong-phase, repeat arm and repeat disarm fail closed. A positive requires all four native GPU_vBlank callbacks and 2380 inherited genuine Unai pixel samples.

Expected native GCC and Clang positive marker (CI pending):

VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS windows=4 narrow_reads=0 narrow_writes=0 vblanks=4 samples=2380 native_psxcounters=1 original_retail=0

## Four real interpreter negative cases

Each mutation retains the self-authored VH78SYN! EXE signature and only changes the first NOP in its 512-instruction MIPS VBlank wait pad.

| Negative | MIPS instruction | Encoding | Expected observed operation |
| --- | --- | --- | --- |
| LB_GP1 | LB t1,4(t0) | 0x81090004 | GP1 8-bit read |
| LH_GP0 | LH t1,0(t0) | 0x85090000 | GP0 16-bit read |
| SB_GP1 | SB t1,4(t0) | 0xa1090004 | GP1 8-bit write |
| SH_GP0 | SH t1,0(t0) | 0xa5090000 | GP0 16-bit write |

Every native mutated launch must exit **82** and print VH176_NARROW_MMIO_REFUSED phase=0 with nonzero only in its corresponding category, never a positive pixel PASS. The GCC/Clang compiled C fixtures cover all eight width/direction/port categories, including address aliases and no ordinary RAM false positives.

**Limitations:** This concerns synthetic guest MIPS instructions and software-emulator-internal VBlank; it does not establish original retail Vandal Hearts MAP02, physical PlayStation/Switch display timing, or a playable remake. Original game assets remain private and uncommitted.
