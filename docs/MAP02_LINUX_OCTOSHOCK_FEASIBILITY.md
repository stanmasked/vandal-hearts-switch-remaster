# MAP02 Linux Octoshock feasibility and hard gate (Stage520)

## Verified upstream facts

- The official **BizHawk 2.11 Linux x64** archive has SHA-256 `cdaf9650d880bae660d63a388430f630b8d8a96b1ba59ebf0e0195a645c3bab8`, independently matched by GitHub Actions.
- After unpacking, the archive has a valid `EmuHawk.exe`, Mono launcher and managed `BizHawk.Emulation.Cores.dll`, but **no Octoshock native library** under any of the supported names. No private game data was used in this observation.
- Upstream [Linux core checklist #2423](https://github.com/TASEmulators/BizHawk/issues/2423) marks Octoshock **not built**, **not automated**, and without Linux build scripts.
- The upstream [2.11 Octoshock Visual Studio project](https://github.com/TASEmulators/BizHawk/blob/2.11/psx/octoshock/bizhawk/octoshock.vcxproj) references **41 native C++ compilation units**, with `EW_EXPORT` and `WANT_LEC_CHECK` defined. There is no existing Unix build target in its `bizhawk` project directory.
- Upstream `emuware/emuware.h` defines the `EW_EXPORT` ABI using `__declspec(dllexport/dllimport)` without a GNU/Linux counterpart. A Linux build requires a controlled, reviewable compatibility change rather than just invoking `g++` on Windows project settings.
- BizHawk's alternative PSX core, Nymashock, is not interchangeable with the Octoshock-specific BK2 evidence chain. It must not be substituted under an Octoshock attestation.

## Next native port feasibility milestones

1. **Source provenance:** Pin the exact official 2.11 upstream commit and Octoshock Git tree; compare an explicit 41-file source manifest with the upstream Visual Studio project. The commit/tree hash transitively pins all source blobs, while no per-file SHA-256 manifest is claimed yet.
2. **Portability compile spike:** In a separate isolated Linux build, create a narrowly scoped POSIX export/visibility shim and a CMake or Make translation of the Windows source manifest. Classify failures (ABI, Win32 APIs, compiler extensions, dependencies) without changing game logic. A successful link is not yet a valid core.
3. **Link/export audit:** Require exported `shock_*` API functions with the documented C ABI. Check missing and unexpected unresolved symbols with `readelf` and `nm`. Do not link fabricated stubs to achieve a green build.
4. **Official managed-binding check:** Place the experimental `liboctoshock.dll.so` only in an isolated private test package. Use Mono's P/Invoke loader to resolve the unmanaged exports; verify the actual runtime core identity, not the configured preferred core. Keep the official archive itself unchanged.
5. **No-media emulator smoke:** Exercise startup, clean shutdown and loaded core identity on permitted synthetic inputs. Without a genuine PSX disc/firmware/movie, do not claim that native PSX execution, MAP02, or any original screenshot was reached.
6. **Owner-private first capture:** Only after the native hash has been independently pinned, official DLLs and witness are pinned from the same exact build, and all synthetic checks pass, run the original disc/BK2/BIOS offline. Audit one cold launch before permitting two captures.


## Stage521 implementation now in the PR

- Upstream commit pinned: `427556b5ef3ac437eba754d90c5e7e9096c9a8df`.
- Octoshock source tree pinned: `24f43550ff70776a86a2d7b64d09993dd09021d9`.
- `tools/map02_linux_octoshock/verify_source_manifest.py` verifies the exact commit/tree, parses the official `octoshock.vcxproj`, and requires exact agreement with the 41-file manifest before any source shim is applied.
- `tools/map02_linux_octoshock/CMakeLists.txt` builds those same source units as `liboctoshock.dll.so`, with `--no-undefined` and `-iquote` so the game-specific `endian.h` does not shadow glibc's `<endian.h>`.
- The disposable CI checkout receives four narrow source patches: `posix-export.patch` (C ABI visibility), `posix-header-order.patch` (include ordering and standard declarations), `posix-deinterlacer-include.patch` (explicit `<cstring>` for `memcmp`/`memmove`/`memcpy` in Deinterlacer.cpp), and `posix-local-buffer.patch` (names an MSVC-specific anonymous CD-sector struct without changing layout). `apply_posix_compiler_sanity.py` adds POSIX size macros and GCC attributes using exact, fail-closed anchors. None of these edits touch tracked upstream sources or the official release archive.
- `tests/test_map02_linux_octoshock_compiler_sanity.py` covers the shim's success path, the upstream commented-out `NO_INLINE` example, unexpected header drift, and partial-shim refusal. The native-port workflow runs this test before installing native build tools.
- The native workflow checks ELF64/x86-64 identity, all declared managed P/Invoke exports except the explicitly audited stale-import exception, verifies that actual managed calls have declarations, and checks unresolved symbols. Its Mono smoke harness calls `shock_Util_DisassembleMIPS`, then creates and destroys the native core using a zero-filled synthetic 512 KiB firmware buffer. It never powers on the emulated console, mounts a disc, or advances CPU frames; no original BIOS or game data is used.

## Stage521 CI findings (2026-10-23)

- The POSIX shim application and all 41-source manifest checks now pass.
- Native compilation passed after adding the explicit Deinterlacer `<cstring>` include on revision `eb516dbe963b78e91a369913bf4b2aea4b346327`.
- The next gate exposed one upstream mismatch: `OctoshockDll.cs` declares `shock_Peripheral_SetNegconInput`, but the pinned native `psx.h`/ `psx.cpp` have no declaration or implementation, and no pinned PSX managed source calls it. Actual neGcon input is sent through `shock_Peripheral_SetPadInput`. No stub will be fabricated.
- `tools/map02_linux_octoshock/known-unimplemented-managed-imports.txt` records that single exception. The revised export audit verifies that it remains declared but unused, absent from native source and absent from the compiled exports; all other managed P/Invoke imports must still be exported. If upstream adds or starts using the symbol, the exception fails closed and must be reviewed.
- The first native compile attempt to reach ABI auditing is [workflow #39954806274](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39954806274); it passed compilation but failed the then-overly broad export check on the stale declaration. The revised audit and helper-only Mono P/Invoke then passed on [workflow #39955329151](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39955329151): 32 required exports were present, the unresolved-symbol check passed, and `shock_Util_DisassembleMIPS` returned 0 through Mono. The latest code adds the synthetic create/destroy lifecycle check and runs the compiler-sanity regression test before native build setup; [workflow #39956496635](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39956496635) is queued on code revision `6366bb6ae73f377407bbbdbbb18db9fb5d3d54da`.
- No native ABI/export pass, Mono P/Invoke pass, real PSX execution, BK2 compatibility, or MAP02 capture is claimed yet. Keep the PR Draft until the revised export audit and safe Mono call both pass.
 
## Acceptance boundaries

The Stage520 Linux workflow must **fail** its final PSX readiness gate when the native module is absent. It may still compile and test managed code without private files, but it must not publish a presumed capture-ready package. The owner runbook is blocked until the native port is proven. The project's Windows route remains unchanged and the original BIN/CUE, BK2, BIOS, private hashes and PNG must never enter public CI.

Unsupported shortcuts: silently swapping to Nymashock, using an unpinned native DLL, treating a Windows compilation as Linux proof, declaring screenshot parity from synthetic PNGs, or converting the owner's original assets into a public CI fixture.
