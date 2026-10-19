# MAP02 v184 — fail-closed late guest RAM data dependence

Base: fully verified [MAP02 v183 Draft PR #213](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/213), 76/76 Actions including native pinned PCSX ReARMed/Unai GCC and Clang, four genuine VBlank events, verified synthetic guest RAM values `0x51a7c3d9` and `0x51a73c26`, 2380 native Unai samples, and first-stage missing SW/LW refusals.

The v184 change adds **three** more private, self-authored PS-X EXEs. Each differs from v183 `CORRECT` by **exactly one 32-bit MIPS instruction in the signed nine-word wait pad** and retains all other bytes, staged GPU/VBlank commands and data. No native emulator hook or memory oracle is changed.

| Mutated guest instruction | Expected physical RAM `0x001e0000` | Expected RAM `0x001e0004` | Why it must fail |
|---|---|---|---|
| `MISSING_XORI` (NOP at guest word 7) | `0x51a7c3d9` | `0x51a7c3d9` | Loaded word is not XOR-transformed |
| `MISSING_FINAL_SW` (NOP at word 8) | `0x51a7c3d9` | `0xd15ea5ed` | Final derived result is not stored |
| `WRONG_LW_ADDRESS` (`LW $s7,4($s6)`) | `0x51a7c3d9` | `0xd15e5a12` | Guest loads the second pre-seeded RAM word, not the value originally stored |

Each of the three new variants runs under the exact previously verified `--vh183-guest-ram-values` mode and **must exit 85 at phase zero**, with `VH183_NATIVE_RAM_VALUE_REFUSED phase=0 first_ok=1 derived_ok=0`; a positive v183 data or v176 GPU/Unai marker before refusal is prohibited. The existing v183 good case (4 VBlanks, 2380 Unai pixels) and its two early negative cases are preserved. Independent GCC/Clang workflow checks the exact one-word signed mutations, MIPS load-delay semantics and wrong RAM results.

The fixtures and test probes are entirely synthetic. There is still no retail Vandal Hearts MAP02 gameplay proof or physical Nintendo Switch frame evidence. No game assets are published; main remains unchanged.
