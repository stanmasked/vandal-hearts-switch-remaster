# MAP02: compiling the real original-PC GPU source

This is the **first real-source compilation gate** for the opt-in
DrawOTag/PutPixel/BlendG1 observer. It is deliberately narrower than a
complete playable PC-port build: it compiles the actual original
`platform/pc/src/libgpu.c` and `pc_raster.c` with the private code
inserted, then performs a relocatable link against the bounded sink and
POSIX stage module. No game executable, disc, BIOS, or HD pack is needed.

## Reproduce on Linux

Use a pristine copy of upstream
`HalmyLyseas/VandalHearts-PcPort` pinned at commit
`14552fffa0e0b47e02b57592e274fc6e7a649923`.

From this remaster repository:

```sh
python3 -m tools.check_map02_original_gpu_tus /private/VandalHearts-PcPort
```

The tool creates generated copies only under a short-lived private
temporary build directory; it does not mutate upstream or emit raw
original game data. It uses the original PC Makefile's GPU include
paths, warning policy and `VH_REGION_US` target, and checks:

1. **Ordinary** generated `libgpu` and `pc_raster` objects, with the
   probe disabled.
2. **Scoped** objects with `VH_MAP02_SCOPED_BLEND_PROBE`, linked with
   `map02_scoped_blend_sink.c` (no disk output module).
3. **Private POSIX** objects with both
   `VH_MAP02_SCOPED_BLEND_PROBE` and `VH_MAP02_POSIX_STAGE`, linked
   with sink and `map02_scoped_blend_stage.c`.

All cases compile with `-Wall -Wextra -Werror` and fail if any
`vh_map02_*` callback remains unresolved after a relocatable link.
The script exits nonzero on source drift, any C compiler error, missing
symbols, or failure to link.

The `.github/workflows/map02-scoped-blend.yml` job now runs this check
against the pinned upstream commit after the synthetic regression
suite. The workflow never invokes the game's proprietary data
generator, packages a game binary, or uploads VRAM snapshots.

## Remaining full-build requirement

A playable native PC-port build still needs the user's own original
regional PS-X executable, disc assets, and its documented SDL2/OpenAL
and optional media dependencies. Full build/setup instructions live in
upstream `docs/building.md` and `platform/pc/Makefile`. The
public CI check does not and must not retrieve or distribute these
copyrighted inputs.

A successful real-source object compile confirms integration at the C
translation-unit and diagnostic symbol level **only**. It is not a
runtime proof of an original MAP02 frame, authentic VRAM provenance,
correct STP/ABR arithmetic, hardware-accurate PS1 rendering, or a
working full game binary.

## Confirmed GitHub Actions checkpoint — 17 October 2026

For commit `c3b5aaf42f66ff388318546774e37f3360af7ff1`,
the dedicated [MAP02 scoped blend run](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38986150920)
**completed successfully**. The job log confirms:

- `Ran 43 tests in 2.457s` — `OK`;
- the upstream checkout at the pinned revision completed;
- both generators passed exact upstream source-anchor checks;
- `Original PC GPU TUs compiled and linked: ordinary, scoped, private-posix`;
- no unresolved private `vh_map02_*` symbols were found in the three
  relocatable GPU object groups.

Early versions of this job **did execute and fail** on synthetic fixture
false-positive reinstrumentation, a PutPixel manifest schema mismatch,
and an incorrect missing-file test expectation. The CI failure logs,
not missing workflow runs, exposed these issues. The relevant fixes
landed in commits `01168918`, `a24e4caf`, `db81bbbb`,
`ce4a8834`, and `c3b5aaf4`.

This checkpoint establishes the actual pinned PC-port GPU TUs compile
in the three modes under the Linux GitHub runner, **not** that the
complete PC game links, boots, captures MAP02, or matches PS1 hardware.
