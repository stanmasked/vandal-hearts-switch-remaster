# MAP02 v150 — bounded instruction quota in the pinned PCSX ReARMed interpreter

Stacked on [v149 Draft PR #141](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/141), with its independently synthesized RAM-only MIPS-I subset. v150 **adds an optional guard directly inside the real pinned PCSX ReARMed MIPS interpreter**, not a retail-original boot route.

## Native execution boundary

`tools/apply_map02_v150_native_instruction_budget.py` applies v147's existing native test instrumentation, then guards both `execI_` and `execIbp` **before** advancing cycles, load-delay state, fetching the next word, or dispatching the guest opcode. The guard checks an explicitly authorized executable address interval, alignment, and an upper bound of 256 steps. If the quota is exhausted (or the PC exits the authorized range), it halts via the interpreter's `stop` and `branchSeen` criteria rather than executing the rejected next word.

The **only** native CLI activation in this version is `--vh129-vblank-04 --vh150-bounded-instructions` with the existing independently authored tagged `VH129SY!` synthetic EXE. It arms an exact **three-instruction** limit immediately before the first native `ExecuteBlock`, checks that the fourth instruction is rejected and returns before later GPU/DMA/VBlank stages can run. A different v129 VBlank profile combined with this flag is rejected with status 54. Normal PCSX execution is unchanged without the flag. The v148 private original boot plan is **not** accepted as native-execution authorization in v150.

Public tests compile a separate C witness with GCC and Clang for quota/invalid PC/pre-side-effect guarantees. The full pinned source build (GCC/Clang) patches the actual PCSX interpreter, runs a deliberately capped real native MIPS synthetic test and a mismatched-mode refusal, then retains all previous v129 genuine-VBlank, v142-v147 MMIO, Unai/DMA2 and v148 preflight regressions. Only aggregate `proof/public/` reports are uploaded; raw guest instructions, GPU traces and user-owned resources are never uploaded.

## Evidence limits and next steps

This stage can prove that the instrumented native PCSX interpreter stops **synthetic instructions** at an explicit quota. It does **not** establish independent OS-level isolation, complete runtime memory protection, retail PS-X EXE startup, BIOS/CD behavior, original MAP02 rendering or Nintendo Switch HD graphics parity. Do not activate arbitrary original game code in the patched native interpreter on this evidence alone. Before any private retail instruction execution, a separately reviewed process sandbox, verified original boot inputs/immutable file descriptors, authenticated runtime receipt, explicit resource budgets and denial of unapproved BIOS/CD/MMIO effects are still required. The PR remains Draft; `main` stays unchanged.
