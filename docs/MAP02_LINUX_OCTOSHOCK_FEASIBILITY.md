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
- `tools/map02_linux_octoshock/CMakeLists.txt` builds those same source units as `liboctoshock.dll.so`, with `--no-undefined`; `posix-export.patch` changes only the export macro in the disposable CI clone. The pinned upstream repository and the project's tracked upstream sources are not modified.
- `.github/workflows/map02-linux-octoshock-native-port.yml` runs the no-game compile spike and audits ELF64/x86-64 identity, every `shock_*` symbol imported by the pinned `OctoshockDll.cs`, and unresolved dynamic symbols; it also compiles a tiny Mono harness that calls the safe `shock_Util_DisassembleMIPS` helper through `DllImport("octoshock.dll")`. It uploads no binary and uses no disc, BIOS, BK2, or screenshots.
- This is a **compile feasibility experiment**, not yet a supported core port. Mono loading, API/structure ABI compatibility, exact core identity, and actual PSX/BK2 execution remain unproven.

As of the last status check, GitHub Actions had left the initial native-port job queued and had not produced a compiler result; newer head revisions also had no associated result visible through the current run query. Do not infer build success from the workflow definition or from the earlier managed-only Windows build. Once the queue advances, the first actionable result is the compiler log, followed by the P/Invoke loader test.

## Acceptance boundaries

The Stage520 Linux workflow must **fail** its final PSX readiness gate when the native module is absent. It may still compile and test managed code without private files, but it must not publish a presumed capture-ready package. The owner runbook is blocked until the native port is proven. The project's Windows route remains unchanged and the original BIN/CUE, BK2, BIOS, private hashes and PNG must never enter public CI.

Unsupported shortcuts: silently swapping to Nymashock, using an unpinned native DLL, treating a Windows compilation as Linux proof, declaring screenshot parity from synthetic PNGs, or converting the owner's original assets into a public CI fixture.
