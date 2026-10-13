# Switch blocker audit — first CI pass

Date: 2026-10-13  
Audited upstream revision: `14552fffa0e0b47e02b57592e274fc6e7a649923`  
Workflow run: [`38442205384`](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38442205384)

## Result

The static audit completed successfully and both minimal libnx diagnostic applications compiled into NRO files in CI. This is a successful tooling and inventory milestone, **not** a successful game port or a real-console test.

The audit reported the following matches in the upstream PC backend:

| Audit category | Matches | What needs investigation |
|---|---:|---|
| Fixed PSX addresses | 5 | Game/PS1 memory assumptions and the address model |
| Desktop virtual memory | 8 | `mmap`, `mprotect`, and `VirtualAlloc` paths |
| Executable / OS introspection | 9 | Signal-context, executable image, and platform-specific fault handling |
| SDL windowing / input | 11 | Replace or adapt the desktop window and event loop |
| Desktop graphics | 6 | OpenGL presentation path; define a Switch graphics backend |
| Desktop audio | 10 | Replace OpenAL device/source/queue handling with a Switch audio backend |
| POSIX threading | 6 | Verify pthread support and semantics, then tune worker/loading threads |

These are source-pattern matches, not necessarily unique defects or a count of required patches. Some code is platform-conditional; each finding must be traced through build guards and call sites before changing it.

## Main engineering conclusion

The first major risk is not HD rendering: it is the PC bootstrap's fixed-address memory and OS-specific fault-handling assumptions. Until the game's memory model and startup path can work on Horizon/libnx, rendering and audio work cannot produce a playable build.

The desktop graphics path also currently presents a framebuffer using SDL/OpenGL calls. The diagnostic framebuffer NRO proves only that the Switch toolchain can compile and link a small libnx application; it does not yet prove the upstream renderer can be reused.

## Recommended implementation order

1. **Map the bootstrap dependencies.** Trace fixed-address allocation, memory protection, fault handlers, and platform conditionals. Separate game-visible PSX memory from host virtual-address assumptions before attempting a Switch build.
2. **Define a backend seam.** Introduce a platform interface for startup/memory, input, presentation, audio, timing, and threads, keeping matching game/decompilation code untouched where possible.
3. **Prove one subsystem at a time.** Build a minimal engine integration target after the memory/bootstrap path is understood; add input and frame presentation before audio and CD/XA paths.
4. **Measure before optimizing.** Establish baseline CPU/GPU/memory budgets on hardware before selecting HD scaling, texture filtering, or other remaster enhancements.
5. **Test on actual hardware.** CI compilation and emulator testing are useful but cannot replace a homebrew launch and gameplay smoke test on the target console.

## Reproducibility and legal boundary

The workflow fetches the exact upstream revision into an ignored temporary cache for static inspection and does not build or redistribute upstream game code or assets. The uploaded artifact contains only the two diagnostic NROs and this text audit report; it does not contain the game. Do not add disc images, BIOS files, proprietary assets, or SDK material to this repository or its CI artifacts.
