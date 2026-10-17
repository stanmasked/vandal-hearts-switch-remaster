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

## Confirmed CI runtime checkpoints

The [first passing joint-original-GPU run](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38986959881)
at commit `f86ba322` confirmed that all three modes execute the real
DrawOTag and rasterizer without an original game asset. An earlier run
failed on an omitted headless helper (`PC_CpuCount`), which was supplied
only in the isolated fixture; the actual original GPU TUs remain
unmodified outside of opt-in generated source copies.

The [native VRAM parity run](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38987063349)
at commit `31081f28` also **passed**. The headless program now hashes the
complete 1024×512×16-bit native VRAM with FNV-1a and compares it across
**ordinary**, **scoped** and **private staged** binaries. This verifies
that, for the synthetic DR_MODE → semi F4 → semi FT4 sequence, the
observer and optional file publication do **not change any native VRAM
byte**. Only a digest is emitted, never the raw framebuffer.

These two green checks directly verify the original code's behavior
for these controlled inputs. They do not authenticate MAP02 gameplay,
PS1 hardware blending, or independent original-console VRAM snapshots.

## Overdraw and texture transparency regression

The extended headless scenario
`tools/check_map02_original_drawotag_complex.py` compiles the same
pinned original GPU source twice and runs three build modes: ordinary,
scoped in-memory observation and private POSIX staging.

Its synthetic OT walk is:

```text
DR_MODE ABR=1
F4 semi (draw ordinal 0; ABR 1)
DR_MODE ABR=3
FT4 semi, STP=1 (ordinal 1; own tpage ABR 2)
F4 semi (ordinal 2; inherited ABR 3)
FT4 semi, texel 0000h (ordinal 3; no PutPixel event)
FT4 semi, STP=0 (ordinal 4; opaque PutPixel, no BlendG1)
```

The original GPU switches modes between overlapping polygons,
executes actual native texture fetches, and preserves PS1-style
transparent and STP conditions. The test asserts absent PutPixel at
ordinal 3, absence of BlendG1 at ordinal 4, proper blend ABRs and
primitive kinds for earlier writes, and unchanged full native 1 MiB
VRAM FNV-1a across all three executable configurations.

The
[complex DrawOTag CI run](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38987272990)
for `027e56a6` **completed successfully** (43 regression tests,
pinned real PC GPU object linking, earlier runtime gates, and the new
overdraw/STP regression).

The strict Python witness comparator also now rejects a broken
selected-pixel native VRAM chain (`next.before != previous.after`)
and any change in packet type while `primitive_ordinal` remains the
same. These are genuine constraints of a single synchronous DrawOTag
native-VRAM walk; they are NOT assertions about VRAM transfers between
different game frames. Neither condition establishes real MAP02
content or equivalence to physical PlayStation graphics hardware.
