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

## GP0(E2h) texture-window Switch SPRT acceptance candidate

Pinned upstream `libgpu.c` already implements the Sony-compatible GP0(E2h) mask/offset path in `SetDrawMode`/DR_MODE, and original `pc_raster.c` applies `u=(u&~(maskX*8))|((offX&maskX)*8)` in `SampleTexture`. No rasterizer reimplementation is needed. Commit `842c0ce` exercises this original path using a second SPRT at native (0,5) (2x2). It uploads an extra 4bpp VRAM word at (66,0) with indices [3,4] and extends the 16-entry CLUT at (0,40) with blue/white. The `DR_MODE` texture-window RECT (8,0,248,256) encodes maskX=1/offsetX=1, redirecting UV0/1 to UV8/9. A reset `DR_MODE` with RECT (0,0,256,256) restores mask=0 before the established red/green sprite, demonstrating state transitions in OT order. The new sprite does not overlap prior synthetic probes.

Commit `9758e75` updates the host reference fixture/palette/VRAM bounds and adds an eleventh test for UV mask semantics and head-inserted OT ordering. Commit `f839fa01` adds NeXium checks for blue (210,440) and white (290,440) on both screenshot frames, while retaining the existing red/green sprite check.

**Acceptance pending final NRO NeXium job.** The initial source-only push `842c0ce` failed the preflight because the C fixture changed before the corresponding Python expectation was committed; this is an expected fail-fast check, not a compiler or renderer failure. Later CI preflight passed after synchronizing the C and Python fixtures. The previously confirmed sprite and FT4 modes remain established by [run #38812020245](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38812020245).

## GP0(E2h) original texture-window accepted in NeXium (CI #38812953937)

**The pending GP0(E2h) gate above is now passed.** [GitHub Actions run #38812953937](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38812953937), source revision `f839fa01f0e1d9b3b4a91d389883635aecf1ac52`, finished with **cross-compile = success** and **Run original DrawOTag raster NRO in NeXium = success**. The cross-compile logs report **11 tests / OK**. Screenshot logs on both 1280×720 frames record the original texture-window SPRT at (210,440) **blue (0,0,255)** and (290,440) **white (255,255,255)**, proving the 8-pixel U window-mask/offset GP0(E2h) path. The immediately following DR_MODE reset preserves baseline SPRT **red (255,0,0)** and **green (0,255,0)** on both frames. Previous FT4 texture and STP assertions also passed: ABR0 red marked texel (173,49,41) → (173,49,99), opaque green (0,255,0), animated center (99,99,90) → (99,99,198), **9,175** changed sampled pixels.

This confirms *asset-free* upstream `SetDrawMode → DrawOTag → SampleTexture` horizontal texture-window addressing (maskX=1/offX=1) and mode reset. It does not yet prove Y-axis window masking, nested modes, additional ABR modes, real game resources/scene, or a hardware Switch run. No new rasterizer implementation was introduced.

## GP0(E2h) vertical texture-window acceptance probe (new CI pending)

Building on horizontal GP0(E2h) CI #38812953937, commits `3986833e`, `e13fd6b4`, `f75ccfd2` and corrective `5d37d0b2` add a **vertical** mask/offset candidate. Pinned original `SetDrawMode` encodes `RECT(0,8,256,248)` as maskX=0/maskY=1, offsetX=0/offsetY=1; original `SampleTexture` thereby redirects native V=0,1 to V=8,9 while keeping U untouched. A 4bpp word at VRAM (64,8) contains indices [3,4] (blue/white), and the next at (64,9) indices [5,6] (magenta/yellow); both reference the same expanded original CLUT at (0,40). A separate SPRT at native (2,0) size (2,2) exercises all four texels. `DR_MODE` with RECT(0,0,256,256) subsequently resets both mask axes, so earlier X-window and baseline SPRT checks must remain unchanged.

The host suite adds a **twelfth** test verifying both V remapping and ordering-table insertion order, and NeXium checks (370,40) blue, (447,40) white, (370,120) magenta, (447,120) yellow across both frames. Early CI pushes failed before SDL2 compilation while the C/Python fixtures were being synchronized; the second pass additionally exposed omitted closing parentheses in the palette fixture, fixed in `5d37d0b2`. The current source-bearing run is [#38813978935](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38813978935) and **must pass NRO build plus emulator screenshots** before this vertical GPU behaviour can be marked verified. Synthetic test data only; no real Vandal Hearts scene or physical Switch validation.

## GP0(E2h) V-axis window verified in NeXium (CI #38813978935)

**The vertical texture-window gate above is now accepted.** [GitHub Actions run #38813978935](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38813978935), commit `5d37d0b2ce437a49e5c6302867bd6e1e42a13fc1`, completed with `cross-compile=success` and `Run original DrawOTag raster NRO in NeXium=success`. The cross-compile logs record `Ran 12 tests in 0.005s` and `OK`, followed by successful Switch ELF-to-NRO verification. Original native screenshot checks at 1280x720 on BOTH frames show the V-window SPRT:
- V8/U0 blue (0,0,255), V8/U1 white (255,255,255);
- V9/U0 magenta (255,0,255), V9/U1 yellow (255,255,0).

The prior independent horizontal window remains blue/white on both frames and baseline `SPRT` remains red/green after both explicit `DR_MODE` resets. Original STP ABR0 remained correct: (173,49,33) → (173,49,90) marked red, opaque green (0,255,0); animated center (99,99,74) → (99,99,181), 8,648 changed sampled pixels. The successful checks establish **both X and Y 8-pixel-masked GP0(E2h) texturing** with OT-ordered state transitions on synthetic VRAM, through original pinned PC-port raster and Switch SDL2/GLES2 backend.

CI #38813778176 failed while C/Python vectors differed and CI #38813831915 / #38813865798 failed on missing Python closing parentheses; these intermediate regressions were fixed in commit `5d37d0b2` and are superseded by passing #38813978935. Real game asset formats, gameplay scene rendering, additional ABR modes, and Switch hardware validation remain separate unverified milestones.

## Original POLY_FT4 STP ABR1/2/3 acceptance candidate

The already accepted asset-free GP0(E2h) XY-window baseline is [run #38813978935](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38813978935). The pinned original `pc_raster.c` implements all Sony BGR555 STP blend modes in `BlendG1`: ABR1 (B+F with saturation), ABR2 (B−F with floor zero), ABR3 (B+F/4), along with previously established ABR0 (B/2+F/2).

Commits `54dc7ccc`, `03bfa948` and `273bf5d1` add three **independent source-backed synthetic raster probes** using original `SetPolyFT4`/`setTPage`/`SetSemiTrans`/`AddPrim` and the existing STP red=0x801f and unmarked green=0x03e0 texture at VRAM (320,0). The ABR1/2/3 quads occupy the free bottom strip at native (2,7), (4,7), (6,7), respectively, outside the original corner tiles and all earlier probes. Expected red BGR555 channels with background 12/31 and foreground 31/31 are ABR1 31/31 (RGB~255), ABR2 0/31 (RGB~0), ABR3 19/31 (RGB~156). Green remains 12/31 background (~99 RGB); the unmarked green neighbouring texel must be fully opaque (0,255,0) for each mode. The workflow checks both screenshots; the reference Python suite includes a 13th test for the exact 5-bit calculation and the C primitive attributes.

**Awaiting the latest Switch NRO and NeXium success.** The first C-only push triggered the expected fail-fast texture test mismatch before the Python fixture update; it does not indicate a native raster regression. Once the current full-code run is green, record its run ID and observed colours before accepting ABR1/2/3. No actual game assets or physical Switch execution are covered.

## Original textured ABR=1/2/3 accepted in NeXium (CI #38815823959)

**ABR1/2/3 pending gate above is now passed.** [GitHub Actions run #38815823959](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38815823959), built from `273bf5d1593c6fe3585985571a9f9921c7b09bd4`, completed with **cross-compile success** and **Run original DrawOTag raster NRO in NeXium success**. Host preflight logged **Ran 13 tests in 0.005s / OK**.

Native 1280x720 screenshot evidence on **both** sampled frames from the original `SetPolyFT4 → SetSemiTrans → DrawOTag → FillQuad → BlendG1` 15bpp STP path:
- **ABR1** (`B+F` saturate): red/green/blue = (255,99,206) → (255,99,33).
- **ABR2** (`B−F` floor zero): (0,99,206) → (0,99,33).
- **ABR3** (`B+F/4`): (156,99,206) → (156,99,33).
- Three adjacent **non-STP green** texels remained completely opaque (0,255,0) on both frames.
- Previous ABR0, zero-texel alpha, indexed/direct FT4 modes, SPRT and horizontal/vertical GP0(E2h) texture-window tests all passed; animated center (99,99,206) → (99,99,33); 7,550 changed sampled pixels.

**Native smoke milestone: ABR0, ABR1, ABR2 and ABR3 are all confirmed** for synthetic 15bpp STP-marked texels on pinned original upstream PC-port raster running as a Switch NRO under NeXium. No real Vandal Hearts textures/game scenes or physical hardware test is implied. A separate live game-assets bootstrap remains the next substantive integration milestone. The earlier C-only partial push failed as expected on source/fixture drift before its Python companion was committed, superseded by this green full-source run.

## First original TIM parser-to-raster integration candidate

Following confirmed synthetic FT4, SPRT, CLUT, ABR0–3 and GP0(E2h) modes, commits `070b87fd`, `7b9ec913` and `70444716` exercise the pinned PC-port's **original `OpenTIM → ReadTIM → LoadImage` path** inside the Switch NRO. A **complete serialized 4bpp PS1 TIM test fixture** (18 little-endian 32-bit words; magic 0x10, flags 0x8, 44-byte CLUT section at VRAM (0,42), 20-byte pixel section at VRAM (384,0)) is assembled as a source-defined buffer. The original `ReadTIM` returns the CLUT/pixel rectangles and data addresses, both are passed directly to the original `LoadImage` VRAM upload. An independent original `SPRT` at native (8,1), textured with tpage x=384 and CLUT y=42, should render red at (835,120), green at (910,120), on **both** NeXium screenshots. This goes beyond ad hoc manually supplied GPU rectangles by exercising the real 4bpp TIM serialization/parser interface, but the pixels and palette remain **synthetic, not actual Vandal Hearts game data**. No proprietary files are committed.

Commits `3333f6de`, `28d2a2fc`, `4b90ba9d`, `a63c82f0` and `cc1f9de2` add a standalone file inspector `tools/inspect_psx_tim.py` and extensive host regressions `tests/test_inspect_psx_tim.py`. The inspector bounds-checks magic, mode, CLUT presence, per-section length/word alignment, payload dimensions, VRAM destinations and entire file length before any call to the original buffer-length-unaware parser. It supports standalone PS1 TIM 4bpp, 8bpp and 15bpp, emits read-only metadata and SHA-256, and rejects corrupt or unsupported files. Users can run: `python3 tools/inspect_psx_tim.py /path/to/own-extracted-image.tim` (not an ISO/BIN disc image). `make test` and the pinned DrawOTag workflow run these additional checks before source compilation.

**Acceptance gate:** only accept the serialized TIM original-parser visual check after a current workflow run with both build and NeXium jobs successful **and** exact TIM red/green screenshot observations. The original image-inventory report (from the user's own local disc) indicates map-specific `F_TEX01.DAT` and `LAND_DT.DAT` assets; these have **not** been proven to be standalone TIM files, and they must not be sent through this parser without format identification/extraction. A first real game-asset frame still needs access to the user's legally obtained local assets and validation of the specific map texture decoding/loading path. This change does not add copyrighted assets, gameplay, or physical hardware testing.

## Original OpenTIM/ReadTIM/LoadImage-to-SPRT verified in NeXium (CI #38816802229)

**The serialized-format TIM gate above is passed.** [GitHub Actions run #38816802229](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38816802229), at source commit `70444716cede9687b4ac4ea5193c2dd8fcefc600`, finished **cross-compile success** and **Run original DrawOTag raster NRO in NeXium success**. On two screenshots the original PS1-format 4bpp TIM parsed and uploaded through the pinned `OpenTIM → ReadTIM → LoadImage` path, then sampled through original `SetSprt → DR_MODE → DrawOTag → FillQuad → PC_GpuPresent → GLES2`: CLUT red (835,120) = **(255,0,0)** and CLUT green (910,120) = **(0,255,0)** on both frames. Previous 4/8/15bpp, STP ABR0–3 and texture-window assertions also remained green. This is **format and raster acceptance on synthetic binary TIM data**, NOT an authentic game texture.

A subsequent source-bearing workflow run [#38817067149](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38817067149) confirms a passing preflight of **14 DrawOTag fixture tests** plus **15 strict TIM inspector tests**, and successful Switch cross-compilation; its separate emulator job status should be checked before representing this later run as fully passed. A separate follow-on run [#38817158123](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38817158123) covers the final test-only zero-padding expression correction.

**External-resource boundary:** the safe CLI inspector `python3 tools/inspect_psx_tim.py own-image.tim` accepts standalone TIM only, rejects malformed/truncated/out-of-VRAM images and produces JSON metadata/SHA256. The pinned port's original TIM API does not accept a buffer length, so any actual external bytes should be preflighted (and file type identified) before delivery to `OpenTIM`. Known map files `DATA/F_TEX01.DAT`/`DATA/LAND_DT.DAT` are separate game resource formats or containers until demonstrated otherwise; do not rename them .tim or assume this parsing path is suitable. Original game bytes were neither uploaded to GitHub nor included in the NRO.

## Final binary TIM preflight and original raster acceptance (CI #38817158123)

The **latest code-bearing** TIM inspector/test revision `cc1f9de28de1161ec930afb04855c34523f8c23c` passed [GitHub Actions #38817158123](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38817158123). Both `cross-compile` and `Run original DrawOTag raster NRO in NeXium` jobs finished **success**. Host logs explicitly show **14/14 DrawOTag fixture tests OK** plus **15/15 bounded standalone TIM inspector tests OK** (29 checks). NeXium screenshots, 1280×720, verify red **(255,0,0)** and green **(0,255,0)** through the original `OpenTIM → ReadTIM → LoadImage → DrawOTag` path on each of two frames; 6,248 sampled pixels changed with background animation. All earlier FT4/SPRT/STP ABR0–3 and X/Y texture-window screenshot assertions completed without failure.

The milestone is a validated **native, original-format TIM ingestion/rendering interface with synthetic input**, not a real game's artwork. To progress to Vandal Hearts image content, first extract and identify individual resources from the user's lawful game image outside the public repo, validate supported formats and destination bounds, then connect that data to the pinned original image upload path. Do not assume the audited F_TEX01.DAT / LAND_DT.DAT map packs are standalone TIM files.

## Original F_TEXxx.DAT + LAND_DT.DAT bank layout / raw CD Mode2 safe inspection (2026-10-16)

**Source finding:** The pinned original `src/states/game_setup.c::LoadMapTextures` does **not** use `OpenTIM` for terrain textures. It directly uploads `F_TEXxx.DAT` via `LoadImage` as a **64 × 256 BGR555-VRAM-word RECT at (320,0)**, representing **32768 bytes / 256 × 256 texels in 4bpp**. `LAND_DT.DAT` is `69 × 1797 = 123993` bytes; map record `mapNum` at `1797 × mapNum` has `257 × 4` UVWH bytes, `257` CLUT selector bytes, then `16 × 16 × 2 = 512` bytes of BGR555 CLUT colors, which original code uploads at VRAM `(672,496)` with `RECT(16,16)` and maps to `gClutIds[32..47]`. These are **not standalone TIM files**. An index-zero texel is only transparent if its looked-up BGR555 **palette color word is zero**, not merely because the index equals zero.

Commits `86049524`, `a1baf326`, `08547269`, and `89c724c8` add a bounded Python inspector `tools/inspect_vh_map_texture_bank.py` and a synthetic-data-only regression suite `tests/test_inspect_vh_map_texture_bank.py` to `make test` and the pinned GPU workflow. The tool reads **already extracted** raw F_TEX+LAND files, or extracts directly from an explicitly supplied *user-owned* raw 2352-byte-sector PS1 BIN by verified CD Mode2/Form1 LBA (2048 bytes at sector offset 24). It validates exact file sizes, map index, sector sync/mode/redundant XA subheaders, extracts CLUT/UVWH records, emits checksums and metadata, and can generate a 256×256 local PNG with an explicit slot's local palette (32..47). A PNG is **an atlas preview only**, not the game's polygons/camera/light state. No game/disc data is uploaded to GitHub. Usage and format proof: `docs/ORIGINAL_MAP_TEXTURE_BANK.md` (commit `1aa11d9a`).

**CI confirmed:** [GitHub Actions run #38817971876](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38817971876), source revision `89c724c847792b715480e0934046dd0943f3f585`, completed with **cross-compile = success** and **Run original DrawOTag raster NRO in NeXium = success**. Its host log reports **14 DrawOTag texture fixtures OK, 15 bounded TIM inspector tests OK, 13 raw map texture/LAND_DT/Mode2 extractor tests OK** (42 tests). The Switch NRO executable passed NRO0 segment verification and the emulator's previous original parser-to-SPRT synthetic TIM assertions remained valid: red `(255,0,0)` and green `(0,255,0)` on both screenshots, 6,248 changed sampled pixels.

**Still not achieved:** actual `F_TEX01.DAT`/ `LAND_DT.DAT` bytes are **not present in this GitHub branch nor in the accessible raw source files in this session**. The prior private disc audit identified RU v1.6-specific LBAs 4374 (F_TEX01) and 4954 (LAND_DT), but no runtime draw of authentic Vandal Hearts map textures has yet been performed in NeXium. The next gate is to inspect/verify the user's local extracted data and connect its bytes to original `LoadImage`/terrain polygon UV, CLUT and TPage paths without publishing copyrighted files.

## Original raw F_TEX/LAND_DT native LoadImage-to-SPRT accepted (CI #38818976526)

The prior map-bank milestone verified **offline format parsing** and a TIM
upload, not a native raster draw of raw `F_TEX` bytes. A new synthetic
integration probe in `probes/pinned_drawotag_switch_smoke.c` (commit
`c612af3343fe22f7fe3cc73d96103b0407a25b58`) now uploads the same
**32768-byte raw 4bpp texture page** and **512-byte BGR555 CLUT block**
used by the original `LoadMapTextures` logic, at `RECT(320,0,64,256)`
and `RECT(672,496,16,16)`, respectively. Source-defined 1797-byte
LAND_DT record slot 0 has UVWH (16,16,15,15) and CLUT ID 32. A real pinned
`SPRT` samples from tpage x320 using `DR_MODE`. The 4bpp page is loaded
*before* the original small 15bpp STP fixture to preserve earlier tests.
The new DrawOTag source-contract regression (commit `b602652c`)
guards the upload addresses, byte offsets, CLUT and ordering-table links.
The NeXium capture assertions (commit `a877d4aa`) measure pixel colors
on both frames.

**Verified:** [GitHub Actions run #38818976526](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38818976526)
at code commit `a877d4aa642315e2f928970940ea5005bda70893`
completed with **cross-compile: success** and **Run original DrawOTag
raster NRO in NeXium: success**. The host preflight logged **15 DrawOTag,
15 TIM, 13 map-bank tests (43 passed)**. Both 1280×720 screenshots show
native raw map-texture red **(255,0,0)** at (835,630) and green
**(0,255,0)** at (910,630). Earlier independent original TIM CLUT red/green,
ABR0–3, SPRT and horizontal/vertical GP0(E2h) assertions also succeeded.
5,447 sampled pixels changed with the animated background.

**Limit:** The GPU executed *synthetic* F_TEX and LAND_DT layout bytes,
not any of the user's actual game data. It does not establish correctness
of user-owned `F_TEX01.DAT`, map 11 geometry, authored UV/GFX tables,
lighting, gameplay or physical Switch hardware. Next practical gate:
user-side read-only extraction/validation of authentic assets and a
private, reproducible way for the NRO to consume them, without embedding
copyrighted assets in the public source or GitHub Actions.

## Optional user-owned SD map 11 preview path: code/host CI verified (run #38820440323)

The prior synthetic `F_TEX/LAND_DT` scene was already proven native.
The next stage preserves that CI fixture and introduces an **opt-in, local-only**
loading path: `source/vh_private_map_bank.[ch]` validates the exact
32768-byte `F_TEX01.DAT` and 123993-byte `LAND_DT.DAT` pair from
`sdmc:/switch/vandal-hearts-remaster/private-assets/`. If **both**
files are absent, the existing synthetic NeXium smoke remains unchanged.
If one exists alone, either length is wrong, map 11 slot 241 UVWH extends
outside the original 256x256 texture page, or its CLUT ID is not in the
16 local rows 32–47, loading **fails closed**. On success, the probe
uses the native original `LoadImage` and `POLY_FT4 → DrawOTag` path to
show the **entire authored slot-241 UVWH patch**, with the selected
CLUT row from LAND_DT, rather than the earlier two sample texels.
This is *one isolated, enlarged texture patch*, not the real map geometry,
battle scene, camera or complete gameplay.

A deliberately invoked **local** stager
`tools/stage_vh_private_map_bank.py` accepts the user's extracted file
pair or audited raw 2352-byte-sector disc LBAs, validates all sizes,
map 11 slot 241 UVWH and local CLUT, and optionally pins both
SHA-256 hashes to the previously audited Russian v1.6 release via
`--require-audited-ru-sha`. It writes the two resource files and a
metadata-only JSON manifest under the mounted Switch SD root.
It refuses to overwrite pre-existing destination files. See
`docs/ORIGINAL_MAP_TEXTURE_BANK.md`. The repository's `.gitignore`
now excludes game disc images, `F_TEX*.DAT`, `LAND_DT.DAT` and
private-assets directories as additional protection against accidental
commit of proprietary files.

**Verified source/test milestone:** [GitHub Actions
#38820440323](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38820440323),
source-bearing commit `69ba2e37f5d569a8d4da676dc4ed8f242bac22fe`,
passed **cross-compile** and the original asset-free **NeXium raster**
jobs. CI logs: **16 original DrawOTag source/pixel fixture tests**, **15
TIM bounds tests**, **13 map bank/Mode2 tests**, **5 private SD staging
tests** (49 Python tests, all OK), plus the native-independent C host
test of missing, partial, invalid and valid owner-bank files (passed).
The built Switch NRO passes NRO0 structural verification. On both 1280x720
synthetic screenshots, the original map-bank red is exactly (255,0,0)
and green exactly (0,255,0); TIM and all established STP/texture-window
checks also remain passing. 5,450 sampled pixels changed between
screenshots due to the existing animated background.

**NOT verified:** Neither the actual user's raw game image nor the
two proprietary `DAT` files were available to the public CI,
the new *private* rendering branch has not been run on real NeXium SD
storage or physical Switch, and no authored live map geometry has been
displayed. CI proves compilation, host asset-reader behavior, state
branch source contracts, and no regression of the synthetic raster path.
Do not present this milestone as a successful real-texture or hardware test.

## Private SD staging ↔ actual C reader cross-language contract (CI #38821308211)

A new host-only `tests/private_map_bank_bridge.c` executable links the
**exact** `source/vh_private_map_bank.c` implementation used by the Switch
NRO. Its companion `tests/test_private_map_bank_bridge.py` generates
synthetic full-size map 11 records, stages them using the production
`stage_vh_private_map_bank.py`, and opens the staged pair with the C
reader. It independently validates **UVWH=(240,192,15,15)**,
**local CLUT ID=35**, 4bpp indices **1,2** read in little-endian PS1
nibble order from F_TEX01, and BGR555 colors **0x001f (red)** and
**0x03e0 (green)** from the selected fourth LAND_DT local CLUT row.
It also asserts that both missing files return **0** (synthetic
fallback), while one-sided files, bad file size and invalid local CLUT
return **-1**, matching NRO fail-closed behavior. All fixture bytes are
generated in memory; no proprietary game data is in the test.

**Verified:** [GitHub Actions run #38821308211](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38821308211)
for source commit `09db3b2d4e376a9bf62aaf9f40c25d1426a29203`
completed with both **cross-compile = success** and
**Run original DrawOTag raster NRO in NeXium = success**. The CI host log
reports **16 DrawOTag fixture tests, 15 TIM tests, 13 original raw map
bank tests, 5 Python private SD staging tests and 3 Python-to-C roundtrip
tests: 52 Python checks passed**. The separate native C file-loader
validation also passed. The built Switch executable passed NRO0 checks.
On both 1280x720 NeXium frames, the asset-free synthetic original
F_TEX/LAND_DT path still renders red **(255,0,0)** and green
**(0,255,0)** exactly; original TIM, ABR and texture-window screenshot
assertions all remain green. Background animation changed 5,447 sampled
pixels. The SD staging cross-language tests are now also wired into
`make test` for host operation.

**Unverified:** SD filesystem access inside NeXium and physical Switch,
a screenshot of the **private rendering branch** using original
`F_TEX01.DAT`/`LAND_DT.DAT` bytes, gameplay camera/terrain geometry,
and a full real asset-driven frame. This milestone shows the local
file-format compatibility and synthetic GPU fallback, not those later
stages. See `docs/ORIGINAL_MAP_TEXTURE_BANK.md` for private staging
instructions and evidence boundaries.

## Virtual SD source-bank preview accepted inside NeXium (CI #38822697671)

**New native milestone:** [GitHub Actions #38822697671](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38822697671), source commit
`a4aec52f4ccad0ad39aef7fc0991816334b170a8`, completed with
**all three jobs successful**:

1. `cross-compile`: compiled the unchanged original pinned rasterizer
   and Switch NRO, confirmed NRO0 and all previous **52 Python**
   + host C private loader checks.
2. `Run original DrawOTag raster NRO in NeXium`: retained the prior
   synthetic TILE/F4/FT4/TIM/CLUT/ABR0–3/X–Y texture-window checks.
3. `Synthetic SD map 11 preview through original DrawOTag`: created an
   **isolated virtual SD card**, with host root `NEXIUM_DATA_ROOT` and
   `$NEXIUM_DATA_ROOT/sdmc/switch/vandal-hearts-remaster/private-assets/`.
   Staged full-sized synthetic F_TEX01.DAT + LAND_DT.DAT using the
   production Python stager, loaded the **regular NRO executable**
   (no fixture compiled inside and no code-path bypass), and verified
   the *private* `POLY_FT4 → DrawOTag` branch via screenshot at 1280×720.

**Native screenshot measurements:** black outer border **(9,9,12)**,
private patch center **(255,0,0)**, **235,248 red pixels** and
**156,156 green pixels** inside the ROI. The previous synthetic
scene has a bright red outer corner and animated gray center,
so it cannot pass these acceptance assertions. The NeXium guest
`fprintf(stderr)` text is not forwarded to the host emulator log:
earlier attempts #38822375680 and #38822519520 drew the private
patch successfully but the first failed on a log-grep assertion;
the stable green run instead asserts the **unique private rendering
pattern** directly, with accompanying screenshot artifact
[`pinned-drawotag-private-sd-synthetic-evidence`](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38822697671).

This demonstrates real executable `sdmc:` I/O in NeXium, production
`vh_private_map_bank_load_pair` for synthetic file inputs, and original
`LoadImage`/`POLY_FT4`/DrawOTag preview from the private texture
page and selected local CLUT. **Not yet established:** use of authentic
`F_TEX01.DAT`/`LAND_DT.DAT` byte content from a user-owned PlayStation
disc, a complete terrain mesh/map scene, lighting, actual game logic or
hardware Nintendo Switch. No proprietary assets have entered GitHub
source, CI artifacts or release builds.

## Verified native private-SD four-quadrant UV + CLUT orientation (CI #38823499785)

**Expanded GPU acceptance passed:** [GitHub Actions #38823499785](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38823499785)
at code/workflow revision `6139d7a9a2bdc09655b4b4e37a9b8db034bdd12a`
completed with **cross-compile SUCCESS, original synthetic raster
NeXium SUCCESS, and isolated virtual-SD private map-preview NeXium
SUCCESS**. Before NRO compilation, 56 Python tests passed (16 pinned
DrawOTag, 15 standalone TIM, 13 map bank/CD Mode2, 5 private staging,
4 four-quadrant synthetic SD fixture, 3 Python-to-C file bridge);
separate C host file-loader checks also passed. Switch NRO0 structural
validation succeeded.

The updated asset-free private SD fixture at map #11, slot 241,
UVWH=(240,192,15,15), local CLUT=35 distinguishes **four independent
UV quadrants**: red BGR555 0x001f in upper left, green 0x03e0 in upper
right, blue 0x7c00 in lower left and yellow 0x03ff in lower right.
On both sides of the source-format → C loader → `LoadImage` →
original `POLY_FT4/DrawOTag` chain, the 1280x720 NeXium capture
checked exact interior pixels: (400,205)=(255,0,0),
(880,205)=(0,255,0), (400,510)=(0,0,255),
(880,510)=(255,255,0). The screenshot also requires a dark external
border, eliminating a false-positive legacy scene. Explicit
`tests/test_private_sd_nexium_fixture.py` reference checks protect
little-endian PS1 4bpp row packing, source UV boundaries, fourth CLUT
row, and the owner-only stager's file bytes. All previous STP/ABR,
TIM, texture-window and baseline GPU regression checks remained green.

This is stronger proof of **both U and V texture coordinate mapping
and local CLUT row selection** than the earlier red/green-only smoke.
These files are synthetic, **not authentic game data**. The first
retail textured map fragment, full map geometry and any hardware Switch
trial remain unverified. Complete details in
`docs/ORIGINAL_MAP_TEXTURE_BANK.md` (commit `88d6872a`).

## Original map 11 MapTileModel and bounded PRS geometry inspection: accepted host preflight (CI #38824725594)

Following the verified synthetic, owner-only `F_TEX01.DAT/LAND_DT.DAT`
virtual SD GPU patch, the upstream map geometry path was audited at
pinned `HalmyLyseas/VandalHearts-PcPort` commit
`14552fffa0e0b47e02b57592e274fc6e7a649923`:

- `src/states/game_setup.c::LoadMap` selects `CDF_M_MAP02_PRS`
  for map index 11, stores tiles with stride 28 and 12 active rows
  (28×12 packed source model prefix = 102144 bytes; usable map
  region is 24×12), then `ProcessMapFileData` calls the map PRS
  decompressor.
- `src/maps/unpack.c::UnpackMapFileData` uses an LSB-first
  control-bit stream and 1024-byte zeroed ring cache initialized
  at write offset 990, supporting literal, absolute 10-bit cache,
  short relative cache and inline literal-run commands. The original
  implementation has no output capacity argument.
- `include/field.h::MapTileModel` is 304 bytes:
  `SVECTOR[22]` (176), `s16 gfx[18]` (36),
  `u8 faces[18][4]` (72), `u8 shades[18]` (18),
  `u8 faceCt` (1) and `u8 height` (1).
  The original `RenderMapTile` in `src/core/graphics.c`
  joins face vertex indices to model geometry, `gGfxSubTextures`
  (UVWH), `gGfxClutIds` and `gGfxTPageIds` and then projects
  and submits textured `POLY_FT4` quads through original DrawOTag.

New **private, read-only metadata inspectors**:
`tools/decode_vh_map_prs.py` (compressed LE-length wrapper,
ring-cache decoding with 2MiB input/output hard caps, bounds checks,
decoded-size/sha256 metadata only) and
`tools/inspect_vh_map_geometry.py` (decompressed 304-byte tile model
prefix, face-index validity, original local GFX slot and
`LAND_DT.DAT` UVWH/CLUT linking; optional `--prs` safely
decodes in-memory before inspecting a selected tile).
Test suites `tests/test_decode_vh_map_prs.py` (13 tests)
and `tests/test_inspect_vh_map_geometry.py` (11 tests)
exercise all command types, corruption limits, 28×12 synthetic map
buffer, face bounds, geometry and CLUT associations. They are wired into
the workflow's preflight and host `make test`. Usage, safe
boundaries and exact original source structure are documented in
`docs/ORIGINAL_MAP_GEOMETRY.md`. Private `M_*.PRS` files are
also excluded by `.gitignore`.

**Confirmed CI**: [GitHub Actions #38824725594](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38824725594),
source code SHA `f2db4a6ce75140b41f0ad5c625844237284d6768`,
finished **cross-compile SUCCESS**, **original synthetic raster
NeXium SUCCESS**, and **virtual-SD private texture preview NeXium
SUCCESS**. Exactly **80 Python tests OK** in eight suites:
16 DrawOTag, 15 TIM, 13 map bank, 5 SD stager,
4 quad fixture, 11 geometry, 13 PRS decoder, 3 Python-to-C
bridge; C file loader tests also passed. Switch ELF→NRO binary
structure validation succeeded. The baseline NeXium TIM and
F_TEX/LAND_DT synthetic samples remained red=(255,0,0) and
green=(0,255,0), with 5450 changed frame pixels.
The private SD NeXium preview independently preserved four
exact colors at their UV corners: red, green, blue and yellow.
An earlier PRS test-only revision failed due to an incorrect high-bit
encoding in the absolute 10-bit cache address test vector; fixed
in `f2db4a6c`, which passed.

**Verification limits:** The decoder and model parser are currently
confirmed against SYNTHETIC PRS streams and MapTileModel records.
The user's original `M_MAP02.PRS` is not available in the
current checked-in sources, so this is **not evidence that a genuine
map file has been decoded**, that original `RenderMapTile` runs
inside the Switch NRO or that a full scene/gameplay is rendered.
The current native map preview remains one source UV patch;
the next gate is to validate actual owner map bytes and wire
multi-face projected terrain models into the pinned GPU port
without redistributing game resources.
