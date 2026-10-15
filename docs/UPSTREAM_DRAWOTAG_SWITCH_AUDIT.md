# Original DrawOTag and Native Rasterizer — Switch Integration Audit

**Source pin:** `HalmyLyseas/VandalHearts-PcPort`, commit `14552fffa0e0b47e02b57592e274fc6e7a649923`.

## Proven path in original PC implementation

In `platform/pc/src/libgpu.c`, `DrawOTag` walks the ordering table and draws primitives through software-rasterizer services in `pc_raster.c`. After the frame is rasterized, it reads the active `DISPENV`, obtains native 1024×512 BGR555 VRAM via `PC_GpuVram()`, and invokes `PC_GpuPresent` with the correct source rectangle. `PutDispEnv` only records display state; presentation occurs after `DrawOTag`, not when that state is set. The supersampled presentation path can instead call `HiresPresent`.

The independent, already-tested integration NRO runs original pinned `PC_GpuInit` and `PC_GpuPresent` through the project SDL2/GLES2 backend on generated VRAM. It does **not** call `DrawOTag`.

## Confirmed object-level progress

- [DrawOTag object CI #38802987267](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38802987267) passed: original `libgpu.c` compiles to an aarch64-none-elf object, defines `DrawOTag`, and still has external references to `PC_GpuPresent` and `PC_GpuVram`.
- [DrawOTag plus raster object CI #38803269505](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38803269505) passed: original `pc_raster.c` also compiles, defines native `PC_GpuVram` and `FillRect`. Its generated object and symbol audit are uploaded with the `DrawOTag` object.
- A narrowly scoped compiler preinclude `tools/switch_psyq_compat.h` defines the `u_char` and `u_short` aliases expected by the clean-room PsyQ headers. No upstream source is modified.

The audit is **compile-only**. Neither object is yet linked into the verified `PC_GpuPresent` test NRO or executed in NeXium.

## Remaining dependency groups and safety gates

`DrawOTag` depends on the software rasterizer's `FillRect`, `FillQuad`, `Hires*` functions and `PC_GpuVram`, plus tracing `Trc*`, resource/HD-pack hooks, and presentation integration. The rasterizer itself depends on `pthread` workers for the optional high-resolution path, `PC_CpuCount`, language-background hooks and HD asset interfaces. Full-object `nm --undefined-only` is a conservative inventory; it includes functions in sections that may not be retained after dead-section elimination.

The next **real engine frame** acceptance test should link these authentic source units with a legitimate ordering-table and native VRAM pipeline, invoke `DrawOTag` in an instrumented Switch NRO, and confirm the downstream `PC_GpuPresent` image in NeXium with controlled primitives. This would be a source-rasterization test, still **not** a playable Vandal Hearts build. Avoid permanent placeholder implementations of actual gameplay or asset systems, and do not ship copyright-protected game resources.

No physical Nintendo Switch execution is confirmed.

## First partial linkage of authentic DrawOTag + software rasterizer

[GitHub Actions #38803479209](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38803479209) **passed** after compiling both original translation units and invoking `aarch64-none-elf-gcc -nostdlib -r` on their object files. The resulting `gpu-raster-combined.o` defines `DrawOTag` and `PC_GpuVram`; `PC_GpuVram`, `FillRect` and `FillQuad` no longer remain unresolved after linking the two source units. The genuine `PC_GpuPresent` remains external, as intended for subsequent linkage with the separately verified Switch observer/GLES2 presentation backend.

This partial link checks symbol compatibility and native-code composition only. It **does not execute DrawOTag**, resolve the full subsystem dependency set, generate a game frame, or produce a playable Switch build. The compiled object and defined/undefined symbol inventories are saved in the CI artifact `original-drawotag-switch-object-audit`.

## Confirmed original ordering-table rasterization running in NeXium

[Original DrawOTag raster to Switch NRO — CI #38805494413](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38805494413) passed **both** target NRO compilation/linking and NeXium runtime screenshot verification. The new asset-free guest probe `probes/pinned_drawotag_switch_smoke.c` calls original `SetDefDrawEnv`, `PutDrawEnv`, `SetDefDispEnv`, `PutDispEnv`, `ClearOTag`, `SetTile`, `AddPrim`, and `DrawOTag`; its native BGR555 framebuffer comes from the unmodified original `pc_raster.c`. The original pinned `PC_GpuPresent` converts the actual rasterized pixels to RGB24 and the project SDL2/GLES2 observer draws the frame under NeXium. This is **not** direct synthetic VRAM filling: the CPU renderer really executes original ordering-table drawing and FillRect for tile primitives.

The independent NeXium job waited for a visible red marker (poll 1), verified the 1280×720 window, matched all four colored corner markers exactly (red, green, blue, yellow), observed center RGB (99,99,140) → (99,99,0), and counted 20,636 changed sampled pixels. Screenshots and the NRO are uploaded as GitHub Actions artifacts.

The test depends on **probe-only inert hooks** for localization, HD replacement and debug tracing (plus previously isolated movie/menu state). These are not substitutes for actual gameplay services; real game bootstrap and assets remain absent. The next step is to exercise additional original GPU primitives (such as F4 polygons and texture-backed paths), then integrate native engine frames with the real region/disc bootstrap. Physical Switch hardware testing remains outstanding.

## Native POLY_F4 quad rasterization confirmed (NeXium)

[CI #38806009204](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38806009204) passed target NRO build/link and NeXium runtime for the expanded `probes/pinned_drawotag_switch_smoke.c`. The probe inserts an original `POLY_F4` quad through `SetPolyF4`, `setXYWH`, `setRGB0`, and `AddPrim`. The pinned upstream `DrawOTag` executes the authentic `FillQuad` path in `pc_raster.c`; the resulting native BGR555 VRAM is passed to the pinned `PC_GpuPresent` and shown by the Switch GLES2 backend.

CI checks the center of that polygon at window pixel (600,200) on both screenshot frames. It measured **exact RGB (255,0,255)** both times. The four original TILE corner markers remained correct, the animated background center changed (99,99,99) → (99,99,206), and 16,684 sampled pixels changed. These assertions establish that **both untextured rectangle and quadrilateral primitives** render correctly end-to-end in the Switch-target emulator.

This test is still asset-free: textured `POLY_FT4`/CLUT sampling, actual gameplay ordering tables, authentic game assets, audio and input are not verified. The only extra service implementations are explicitly test-only placeholders; original libgpu, pc_raster and PC_GpuPresent code is linked, not replaced. Physical Switch validation remains outstanding.

## Indexed POLY_FT4 / CLUT integration candidate (pending CI)

Commits `a78a697e` and `95eeb7cb` extend the **asset-free** NeXium probe with a 4bpp indexed `POLY_FT4`. Two 16-bit packed texture words (indices 1,2,1,2) are uploaded by the **original** `LoadImage` to VRAM at (64,0); a sixteen-entry CLUT at (0,40) maps index 1 to BGR555 red (0x001F) and index 2 to green (0x03E0). `SetPolyFT4`, `setUVWH`, `setTPage`, `setClut` and `AddPrim` feed the original `DrawOTag` which routes to the original 4bpp `SampleTexture` and `FillQuad` implementation. The quad is deliberately separate from the prior F4 test and original corner markers.

The emulator workflow now asserts four alternating red/green sample locations on **both** screenshots, alongside the existing F4, TILE, animation and frame size assertions. **This is only an integration candidate until the new GitHub Actions run has completed and the screenshots have been verified.** Do not count this as a passing 4bpp/CLUT runtime test before CI confirmation. The probe does not use original game texture assets; 8bpp, direct 15bpp texture paths and actual engine frames remain separate gates.

## Independent 8bpp POLY_FT4 / 256-entry CLUT candidate (pending CI)

Commits `d91ad19e` and `40c6198c` add a second indexed-texture quad beside the existing 4bpp candidate. The asset-free probe uploads two 8bpp packed VRAM words (indices 1,2) at (128,0) through the original `LoadImage`, plus a 256-entry CLUT at (0,41): index 1 is BGR555 blue (0x7c00), index 2 is white (0x7fff). `SetPolyFT4`, `setTPage(...,1,...)`, `setClut` and `DrawOTag` exercise the native 8bpp `SampleTexture` path. The NeXium workflow adds two colour probes (blue/white) on both screenshots; existing TILE, F4, 4bpp and dynamic background assertions stay enabled.

**Status: committed, not yet CI-confirmed.** Neither the 4bpp nor the 8bpp additions should be reported as successful NeXium runs until fresh run logs and screenshots establish that result. Separate future gates: direct 15bpp textures, texture window, STP/semi-transparency, real game VRAM uploads and engine frames.

## Direct-colour 15bpp POLY_FT4 candidate (pending CI)

Commits `ea280273` and `3a67680b` extend the same isolated NeXium NRO probe with a 15bpp direct-colour `POLY_FT4`. The original `LoadImage` uploads a 2x2 BGR555 texture at VRAM (192,0), with alternating yellow (0x03ff) and magenta (0x7c1f). The probe supplies `GetTPage(2,0,192,0)`, which selects the native direct-colour `SampleTexture` path, bypassing CLUT. Independent screenshot probes check both texels on both captured frames and retain the prior TILE, F4, 4bpp and 8bpp assertions.

**Acceptance status: committed but unverified on NeXium.** The legacy #38806009204 run predates all indexed/direct-colour additions and proves only TILE/F4. Current workflow runs after these commits must be checked before promoting the three FT4 modes to passing. No copyrighted game assets are introduced.

## Zero-texel transparency regression (pending CI)

Commits `03aa0a7d` and `f59881ec` add a new 15bpp direct-colour texture at VRAM (256,0), uploaded by original `LoadImage` with the first texel 0x0000 and the adjacent texel opaque cyan 0x7fe0. The independent `POLY_FT4` is inserted through `AddPrim` and rendered by pinned `DrawOTag`/native `FillQuad`. A NeXium screenshot probe asserts that the transparent texel leaves the animated background visible (RGB red/green near 99 and blue changing between frames), while the adjacent opaque texel stays cyan.

This only checks fully transparent (zero-valued) direct 15bpp texels and their opaque neighbour. It does **not** establish STP-bit semi-transparency or any indexed CLUT transparency, and neither this test nor the preceding 4/8/15bpp probes is marked passed without a fresh CI runtime run. Previous confirmed #38806009204 is restricted to TILE/POLY_F4.

## Texture fixture preflight verified locally (5/5)

The pure-Python, asset-free reference suite `tests/test_drawotag_texture_fixtures.py` validates packed 4bpp nibble lookup, 8bpp byte lookup, 15bpp direct BGR555 reads, zero-value transparent texel encoding and that every fixture upload is inside VRAM but outside the 12x9 display rectangle. The initial five checks were committed in `6ccefe5e`. An earlier status note described them as locally passing, but no corresponding local test log was preserved with this audit; treat this as a **test-definition milestone**, not independently reproducible execution evidence. `make test` now runs this suite (commit `633561fc`), and the pinned DrawOTag NRO workflow runs it as a preflight build step (commit `3c6f54bf`).

Scope limit: the reference test duplicates the deliberate fixture layout and validates *fixture consistency*, not source equality against the C probe and not runtime correctness of the upstream `SampleTexture`, `FillQuad` or GLES2 path. NeXium acceptance remains pending verification from a new CI run and screenshots. Do not promote any FT4 format to verified merely from these five unit tests.

## 15bpp STP / ABR0 per-texel blend acceptance candidate (pending CI)

Commits `ea9adcc1` and `fcb10fa9` add a new asset-free direct-colour FT4 probe for semi-transparency. The original `LoadImage` writes (192-independent) 2x2 texels at VRAM (320,0): STP-tagged red 0x801f alternating with untagged opaque green 0x03e0. The quad lives at native x=8..10,y=5..7 (not overlapping the prior indexed/direct probes) and is configured via `SetTPage(...,2,0,320,0)` and original `SetSemiTrans(...,1)`, then rasterized through the original `DrawOTag`/native `SampleTexture` and `FillQuad`.

NeXium checks that STP red uses the ABR=0 approximately 50/50 red/green blended channels (expected RGB approximately 173,49,variable-blue on the animated background), while green without STP remains opaque despite primitive-level semi-trans mode. These approximate channel checks intentionally allow BGR555 quantization and presentation rounding.

**Unverified until a new CI run passes**: the preceding validated NeXium run #38806009204 still establishes only TILE/F4. Passing this candidate would establish ABR0 per-texel STP in the asset-free probe, not other ABR blend modes or gameplay effects.

## STP fixture preflight and source-drift gate

Commits `7c385b60` and `10b16033` add two reference-suite regressions: a sixth texture-fixture test confirms that 0x801f has STP bit 15 while adjacent 0x03e0 is unmarked and nonzero; a seventh test parses the C probe's fixture word initializers to ensure the Python reference vectors for 4bpp, 8bpp, direct 15bpp, zero-transparency and STP have not drifted from the guest source. These additions remain wired to `make test` and the pinned Switch workflow preflight.

**Validation status:** code committed; successful execution of the expanded seven-test suite and newly instrumented NRO is not claimed here. A fresh workflow success with screenshots is required for actual native STP/raster evidence.

## Fixed fixture-parser regex false failure

Commit `6c2b840e` corrects a double-escaped raw regular expression in `tests/test_drawotag_texture_fixtures.py`: the old expression searched for literal backslash characters rather than C whitespace/bracket syntax, so the C/Python drift check could not reliably match even valid fixture arrays. The corrected regex was inspected against all five current guest C array initializers (4bpp, 8bpp, direct 15bpp, zero-alpha and STP) and all names matched. This is a source/parser check, **not** a complete Python unit-test run or NeXium execution. Current full CI evidence remains to be verified.

## Full fixture-source contract and early CI gate (2026-10-16)

Commits `62e8c706` and `fde40ec6` strengthen the **asset-free preflight only**. The Python suite now has **nine test methods** and cross-checks the original guest-probe declarations for the 4bpp and 8bpp palette initializers (including C zero-initialization of unused entries), all seven `setRECT` + `LoadImage` upload associations, VRAM bounds/disjointness, five `setTPage` selections, the indexed `setClut` coordinates, and `SetSemiTrans(&semi15,1)`. The CI step runs immediately after checkout, **before** the expensive SDL2 source build, so a fixture regression fails fast.

An independent source-contract audit against GitHub's current `probes/pinned_drawotag_switch_smoke.c` verified seven declared pixel/palette arrays, seven disjoint upload rectangles, five texture-page settings and the early CI step order: **all matched**. This is *not* a completed run of the Python nine-test suite, an NRO build or NeXium screenshots. The GitHub connector's commit status / pull-request workflow lookup did not provide a current push-triggered run to verify. Therefore the last confirmed native runtime remains the earlier TILE/F4-only NeXium run #38806009204. Do not report 4bpp/8bpp/15bpp, alpha or STP native GPU acceptance as passed until the newer run evidence can be retrieved.

## Confirmed native FT4 / CLUT / transparency / STP NeXium acceptance (CI #38810768669)

**New evidence supersedes the earlier pending-status paragraphs above.** [GitHub Actions run #38810768669](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38810768669), built from `fde40ec662a6249c72bc1d499b655efe685ba378`, finished **successfully**, including both `cross-compile` and `Run original DrawOTag raster NRO in NeXium` jobs. The cross-compile log reports **Ran 9 tests in 0.003s** (successful job), and the runtime log verifies a 1280×720 screenshot with all four exact corner markers. It reports on both frames:
- 4bpp CLUT: alternating red (255,0,0) / green (0,255,0) exactly;
- 8bpp CLUT: blue (0,0,255) / white (255,255,255) exactly;
- 15bpp direct: yellow (255,255,0) / magenta (255,0,255) exactly;
- STP ABR0: marked red over animated background (173,49,123) then (173,49,41); unmarked green (0,255,0) on both frames;
- animated background center (99,99,247) then (99,99,90); **9,409** changed sampled pixels.

All programmatic screenshot assertions, including the zero-texel transparency checks, finished without error. The result proves asset-free native 4/8/15bpp `POLY_FT4`, CLUT, zero texel and ABR0 STP acceptance in NeXium using original pinned `libgpu.c` / `pc_raster.c` and SDL2/GLES2. It does **not** prove real game assets, an authentic game frame, other ABR modes, handheld hardware or real gameplay. The `fde40ec6` version was the latest source-bearing change before the subsequent documentation-only commits.

## Original SPRT + DR_MODE texture-page acceptance candidate (pending new CI)

The already-passing FT4/CLUT/STP baseline is [run #38810768669](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38810768669). Commits `4ff5f675`, `378a710b` and `559d1d5a` add another **asset-free** original primitive, `SPRT`. The sprite sits at native (0,3) with size 2x2, samples U/V (0,0) from the existing 4bpp packed test texture and CLUT at (0,40), and relies on the original `DR_MODE` primitive for `GetTPage(0,0,64,0)`: `SPRT` itself has **no** tpage field. Because `AddPrim` head-inserts in the one-bucket OT, the sprite is linked first and the `DR_MODE` packet linked next; `DrawOTag` therefore processes the mode before the sprite. The NeXium job checks red (210,280) and green (290,280) on both screenshots.

The host preflight now has **ten** test methods including a source-level assertion of sprite setup, correct CLUT, mode selection and OT insertion order. SPRT is **not accepted until this new NRO compiles and the emulator screenshot job passes**. All real game assets, 8bpp sprites, texture window tests and other semi-transparency modes remain separate gates.

## Original SPRT + DR_MODE confirmed in NeXium (CI #38812020245)

**The SPRT pending gate above is now passed.** [Run #38812020245](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38812020245) executed revision `559d1d5a90349eea459ec08ebfcb19187f555a58` with both **cross-compile: success** and **Run original DrawOTag raster NRO in NeXium: success**. The cross-compile log states `Ran 10 tests in 0.004s` and `OK`. The emulator log confirms 1280×720 screenshots and sprite sampled through original `SetSprt → AddPrim → DR_MODE → DrawOTag → SampleTexture/FillQuad → PC_GpuPresent → GLES2`: (255,0,0) red and (0,255,0) green on **both** screenshots, using the same original 4bpp CLUT VRAM page but setting the tpage by `DR_MODE` in OT order.

Existing FT4 assertions also passed: e.g. native STP ABR0 blend (173,49,41) → (173,49,90) while the adjacent unmarked green stayed opaque (0,255,0). Dynamic screen center (99,99,82) → (99,99,181), with 9,292 changed sampled pixels. The probe now confirms **TILE, POLY_F4, POLY_FT4 in 4/8/15bpp, zero-valued transparency, ABR0/STP, and SPRT using DR_MODE**, all on asset-free synthetic fixtures. Other ABR modes, texture-window handling, genuine game assets/engine frame and physical Switch hardware are still not established by this run.
