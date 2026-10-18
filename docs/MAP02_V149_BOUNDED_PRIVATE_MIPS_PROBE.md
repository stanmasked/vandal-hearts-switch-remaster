# MAP02 v149 — bounded, fail-closed private MIPS instruction probe

Stacked on the completed [v148 boot-plan Draft PR #140](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/140). This is an exploratory **RAM-only diagnostic subset interpreter**, not PCSX ReARMed, a PS1 BIOS, authentic MAP02 playback, or a Nintendo Switch renderer.

## What is implemented

- Revalidates original US privately owned PS-X EXE, independently extracted matching MIPS ELF, three source anchors, executable source-byte identity, loaded entry address, BSS/GP/SP and full 2 MiB PS1 RAM layout using the v148 validator. **The public synthetic fixture cannot pass the original-only CLI.**
- Requires an existing, unchanged v148 mode-0600 private boot-plan manifest before attempting a local probe. A matching test fixture may call the pure function with `require_original=False` only in tests.
- Executes a strict MIPS-I instruction subset in an ephemeral 2 MiB bytearray: arithmetic, boolean and shift operations, conditional branches/jumps with delay slots, supported load/store instructions with a one-instruction load delay. Supports **1–256 instructions**. Unsupported/privileged opcodes, signed overflow, alignment faults, out-of-range accesses, MMIO and writes to source-verified executable sections (including KSEG0/KSEG1 mirrored aliases) stop **before side effects**.
- Returns a bounded stop reason and count, private CPU/RAM digests, and explicit `retail_runtime_authenticated=false`, `original_map02_rendered=false`, `bios_cd_gpu_services_executed=false`. Reaching the instruction budget is a controlled diagnostic stop, not completion of an emulated boot. The subset is not cycle accurate and does not model interrupts, CD, DMA, GPU, exception handling, BIOS, complete R3000A instructions, or peripheral timing.
- Private CLI creates an exclusive 0600 result JSON only in an owned 0700 directory (mode checks, no-follow, fsync, rereads of source and boot-plan after the write). It removes an incomplete result on error; the stdout result is generic and contains **no private addresses, instruction words, paths, hashes or registers**.
- Keeps preexisting native PCSX synthetic VBlank/DMA2/Unai work untouched. Public CI tests this separate subset on GCC and Clang runner jobs, with no original game executable or extracted ELF.

### Local, original-only *diagnostic* probe (no uploads)

After privately running v148 to create its manifest, use a **new** empty private output directory:

```sh
mkdir -m 700 /private/vh149-probe
python3 -m tools.run_map02_v149_bounded_guest \
  /private/original/SLUS_004.47 \
  /private/original/extracted-mips.elf \
  /private/vh148-boot/vh148-private-original-boot-plan.json \
  /private/vh149-probe --max-steps 64
```

Only the private result includes a stop reason and executed-step counts; the console output never prints the original guest state. A stop on unsupported instructions, MMIO, external BIOS calls, or fetch beyond the verified code does **not** mean original gameplay ran successfully. It is a controlled research observation, not proof of a valid retail startup.

**Evidence boundary:** No real user-owned original files are included or used in public CI. The local original-only path is available but **has not been executed here**; v149 public verification is synthetic. No original MAP02 gameplay, PS1 graphical frame, or Switch HD parity can be claimed from these tests.
