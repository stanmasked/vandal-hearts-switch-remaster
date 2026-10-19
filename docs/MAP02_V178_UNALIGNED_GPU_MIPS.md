# MAP02 v178 — unaligned MIPS GPU memory paths

Stacked on v177 Draft PR #201, which completed 70/70 GitHub Actions successfully.

The pinned PCSX interpreter implements MIPS LWL and LWR with aligned psxMemRead32, while SWL at offset 2 calls psxMemWrite16 and psxMemWrite8, and SWR at offset 1 calls psxMemWrite8 and psxMemWrite16. v178 adds a source-route audit, negative mutations of these interpreter routes, and real native GCC/Clang test runs.

The four tests replace exactly one NOP in a self-authored VH78SYN! synthetic PS-X EXE with: LWL t1,1(t0) (0x89090001, GP0 read, expected exit 81); LWR t1,6(t0) (0x99090006, GP1 read, exit 81); SWL t1,2(t0) (0xa9090002, GP0 16-bit plus 8-bit write, exit 82); SWR t1,5(t0) (0xb9090005, GP1 8-bit plus 16-bit write, exit 82). Each refusal must identify exactly the expected GPU operation and must occur without a positive pixel marker.

The clean native synthetic guest must still traverse four PCSX emulator-internal VBlank events and 2380 native Unai pixel samples. GCC and Clang independently run the route audit and inherited 24-lane regression tests. No new GPU mutation or host-injected VBlank is introduced.

This tests only synthetic MIPS execution within a software emulator. It does not establish retail Vandal Hearts MAP02 execution, physical console timing, Switch rendering or a playable remake. The original game data remain private.
