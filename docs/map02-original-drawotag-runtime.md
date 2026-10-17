# MAP02: execution of original DrawOTag and rasterizer

The headless gate `tools/check_map02_original_drawotag_runtime.py`
runs the **actual pinned original PC-port** `libgpu.c` and
`pc_raster.c` together. It creates two source copies with the
opt-in DrawOTag and scoped BlendG1 hooks, compiles a synthetic
`DR_MODE → POLY_F4 → POLY_FT4` ordering table, and executes the
original token-mint/resolve walker and original 15-bit rasterizer.

```sh
python3 -m tools.check_map02_original_drawotag_runtime \
  /private/VandalHearts-PcPort
```

The upstream checkout must be pristine and pinned to
`14552fffa0e0b47e02b57592e274fc6e7a649923`.
No original PlayStation executable, disc assets, BIOS, HD pack, private
trace or screenshots are needed.

Three modes are compiled and executed:

- **ordinary**: both original GPU translation units with diagnostic
  macro disabled;
- **scoped**: callbacks linked to the bounded in-memory witness sink;
- **staged**: the same callbacks plus explicit POSIX private staging
  of paired PutPixel and BlendG1 JSONL files in a temporary 0700
  directory, followed by the strict Python witness comparator.

The OT receives a synthetic red semi-transparent flat quad under
`DR_MODE` with ABR=1, followed by a textured semi-transparent FT4 with
ABR=2. The texture is a synthetic in-memory 15-bit BGR555 word with
STP set. `AddPrim` adds packets in reverse order because the
original bucket walk is LIFO. The observer asserts there are exactly
two drawing primitive ordinals 0 and 1, with proper original primitive
types and independent, actual BlendG1 argument and result values.

External language-pack, HD-pack, GPU presentation and trace-output
dependencies are stubbed *only in this headless fixture*; the original
`DrawOTag`, token walking, `FillQuad`, DDA, `PutPixel`, BlendG1 and
native VRAM storage are not stubbed. Never use the stubs in a real
game build or represent the harness as authentic MAP02 capture.

CI: `.github/workflows/map02-scoped-blend.yml` runs this additional
real-code runtime gate after the existing 43 regression tests, original
GPU compilation gate and four-ABR raster-only runtime check.

**Remaining**: a full unmodified-runtime native game build against
the user's legally obtained game content, independently source-keyed
real MAP02 VRAM evidence, PS1 hardware comparison, and privacy-reviewed
capture. The headless synthetic test establishes software behavior
in the original PC GPU path, **not** any of those later milestones.
