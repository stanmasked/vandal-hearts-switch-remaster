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

## Independent native VRAM snapshots at original draw boundaries

The selected-frame opt-in generator now additionally supports
`VH_MAP02_VRAM_EDGE_PROBE` alongside
`VH_MAP02_SCOPED_BLEND_PROBE`. The helper
`tools/map02_vram_edges.c/.h` is *independent of the PutPixel callbacks*.
Immediately before and after **every native raster draw**
(F4, FT4, SPRT or TILE), instrumented `libgpu.c` reads the selected
pixel directly from `PC_GpuVram()[y][x]` and retains:

`frame`, `primitive_ordinal`, `primitive_type`, `x/y`,
`before`, `after`.

This is bounded to 8192 draw boundaries in a frame. It fails closed
on overflow, a malformed draw sequence, missing begin/end calls, or an
aborted OT walk. No raw VRAM, source assets, snapshots, or event logs
are emitted automatically. It uses an optional in-memory buffer and
is never enabled in the ordinary renderer.

The headless **staged** runtime now compiles this independent module
and joins its sealed observations against the separately collected
PutPixel buffer *only after the actual DrawOTag traversal ends*.
For each primitive:

- the first PutPixel `before` must equal the independently sampled
  `before`;
- subsequent writes must maintain pixel-word continuity, and the last
  PutPixel `after` must equal the independently sampled `after`;
- any primitive with no selected-pixel PutPixel observations must
  have **identical independently read before/after VRAM words**.

In particular, the complex test sees **five** native draw boundaries
including the transparent FT4 at ordinal 3, for which no PutPixel
occurs, and the STP=0 opaque FT4 at ordinal 4. Both the baseline and
overdraw headless programs continue to compare the *entire native VRAM*
digest against the ordinary and scoped builds.

The standalone test `tests/test_map02_vram_edges.py` checks untouched
primitives, ordinal/type validation, private buffer closure,
overflows, and sticky failure semantics. Pinned original-GPU
compilation now builds the edge module, and CI enforces the
source+runtime integration.

The [verified green run](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38988416483)
at commit `0e4cdd8b` reports **45/45 regression tests passed** and
successful compilation and execution of the original GPU paths,
including both independent-boundary runtime checks.

**Scope:** these are independent *read sites* in the same original
PC-port process and selected synthetic input. They are **not**
independently acquired physical PlayStation VRAM snapshots, not a
genuine MAP02 frame, and not proof of original-console behavior.
Private witness-file export and external original-game comparison
remain separate, later validation stages.

## Private SHA-256 witness for direct VRAM boundaries

With both opt-in macros \`VH_MAP02_SCOPED_BLEND_PROBE\` and
\`VH_MAP02_VRAM_EDGE_PROBE\`, plus \`VH_MAP02_POSIX_STAGE\` and an
explicit \`VH_MAP02_PROBE_OUTPUT_DIR\` owned by the current user and
permissioned \`0700\`, the original synchronous DrawOTag frame now
stages **three related files** from the same selected frame:

- \`putpixel-native-events.pending.jsonl\` (all observed pixel writes);
- \`blendg1-native-events.pending.jsonl\` (real BlendG1 calls);
- \`vram-edges-native-events.pending.jsonl\` (all native DRAW
  boundaries, including primitives with no selected-pixel writes).

The third buffer is separately bounded to **8192** draw edges and at
most **2 MiB**, allocated only for the explicit private staging
configuration. All three files are fully written, synced, reread and
compared before the exclusive hard-link publication. If publication
fails, newly linked filenames are rolled back without replacing
existing data. A crash can nevertheless leave orphaned pending files:
this process is not a crash-atomic multi-file transaction and **pending
files are never trusted evidence**.

The independent JSONL edge entry is a bounded object with stage
\`native_vram_edge\`, frame, zero-based draw ordinal, primitive type,
native X/Y, and 16-bit BGR555 before/after words. Every row is
directly observed at the DrawOTag boundary; no edge is synthesized
from PutPixel. A transparent polygon with no writes must have equal
before/after values.

After capturing real **private** original source-keyed GTE/DrawOTag/VRAM
evidence, the verification/publication chain is:

\`\`\`sh
python3 -m tools.promote_map02_putpixel_stage \
  /private/map02/source-bundle /private/map02/native-capture
python3 -m tools.publish_map02_blendg1_witness \
  /private/map02/source-bundle /private/map02/native-capture
python3 -m tools.publish_map02_vram_edges_witness \
  /private/map02/source-bundle /private/map02/native-capture
python3 -m tools.verify_map02_vram_edges_witness \
  /private/map02/source-bundle /private/map02/native-capture
\`\`\`

The VRAM-edge publisher **cannot skip** the existing full BlendG1
verification (which rechecks PutPixel and the independent
source-keyed original VRAM/OT chain). It then checks that every
PutPixel lies within a sampled draw ordinal and that its first
\`before\` and final \`after\` match the independent VRAM boundary
words. Empty/transparent draws must preserve the sampled pixel.
The edge manifest is installed *last* and binds the SHA-256 digests
of the completed BlendG1 manifest, verified PutPixel log, verified
BlendG1 log and independently staged VRAM-edge log.

The final verifier repeats SHA-256 and source-keyed chain validation;
none of these commands print raw pixels or upload private logs. C
tests and Python tests use entirely synthetic, asset-free records
and cannot authenticate original MAP02 gameplay. No physical PS1
hardware comparison has been performed. HD replacement remains
disabled pending original MAP02 confirmation.

## Verified private triple-witness integration checkpoint

The [55-test green CI run](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38990282308)
for commit \`04bf437b\` confirmed:

- **55/55** regression tests (including direct-edge JSON strict parsing,
  SHA-256 manifest publication/reverification and C three-file
  exclusive-write rollback);
- successful pinned original PC GPU source object compilation;
- successful real rasterizer runtime for the normal and scoped modes;
- successful original DrawOTag baseline and complex transparent/overdraw
  runtimes in all three configurations;
- SHA-bound publisher/validator integration in synthetic private
  fixtures, with the original source-keyed verifier mocked **only in
  explicitly marked unit tests**.

The complex synthetic DrawOTag runtime independently checks
VRAM-edge/PutPixel agreement, including zero-texel draws, and ensures
the full native VRAM hash is unchanged across renderer configurations.
The tests also reject duplicate JSON keys, nonstandard numeric
constants, and replacement of the published VRAM-edge file.

This verifies software integration and publication fail-closure; it is
**not** evidence that actual retail MAP02 data were loaded, rendered or
compared to a PlayStation console. Until original gameplay and
provenance have been independently established, HD replacement remains
disabled.
