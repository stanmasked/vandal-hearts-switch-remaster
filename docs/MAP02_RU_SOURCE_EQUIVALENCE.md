# MAP02 — Russian PS1 v1.6 source-byte equivalence (2026-10-20)

## Scope and provenance

A privately run, read-only audit of the user-owned `Vandal_Hearts_(RU)_v1.6.bin`
reported `LOCAL_MAP02_RU_SOURCE_RECONCILIATION`, source SHA-256 preflight
verified, volume `SLUS_00447`, and `original_payload_exported=false`.
The private source image and extracted game content are **not** in this repository.
The sanitized receipt was checked for internal consistency before recording
these findings.

**This proves source-resource byte equivalence at MAP02 for the compared files,
not full-disc identity, release authenticity, texture selection at runtime,
or visual correctness.**

## Verified resources

| Resource | ISO9660 start LBA | Source file bytes | SHA-256 |
| --- | ---: | ---: | --- |
| `DATA/M_MAP02.PRS` | 7116 | 22783 | `c370660f7f13e6d6e76f4126a45418bc9c64c747de8309ca946d37b502516387` |
| `DATA/M_MAP02.DAT` | 6999 | 238336 | `07666bd80b87de763ef7312ecaeaa0bf747ebfe49db032fa68c9af675d151c31` |

The PRS length header declares 22,779 compressed bytes; the 4-byte length
prefix yields 22,783 logical file bytes. The existing PRS decoder produces
exactly **187,264 bytes** (616 records of 304 bytes), SHA-256
`dd98f466fbf4f1019cf04d9b19dd85861afa61e97d0470ce796a4cb83b989382`.

All three digests match those already recorded by the previous source-disc
audit and in `docs/MAP02_PRS_DAT_RECONCILIATION.md`. This means no RU-specific
MAP02 decoder variant is necessary for this verified pair.

## Exactly two PRS versus DAT differences

Across the first 187,264 bytes of DAT, the private audit reports precisely
two mismatching bytes:

| Byte offset | Record / (z,x), face | PRS local GFX | DAT local GFX |
| ---: | --- | ---: | ---: |
| 74048 | 243 / (8,19), face 0 | 241 | 98 |
| 97152 | 319 / (11,11), face 0 | 243 | 150 |

Existing PC-port source analysis indicates that loading map 11 requests
`M_MAP02.PRS` and adds 400 to nonzero local GFX identifiers. Thus,
**predicted if PRS is used**, the runtime identifiers are 641 and 643;
**if DAT were used**, 498 and 550. These are **predictions**, not observed
runtime values.

## Reproducibility on the private Mac

From the repository root, with Python 3.9 or newer and the locally mounted,
user-owned raw Mode2/2352 disc, a read-only audit may be run as:

```bash
python3 -m tools.audit_map02_disc_prs \
  --disc-image "/private/path/to/Vandal_Hearts_(RU)_v1.6.bin" \
  --layout mode2-2352 --dat-from-disc --require-prior-provenance \
  > "/private/path/to/map02_audit.json"
```

The command verifies source-sector EDC and resource fingerprints; the JSON
contains hashes and record values, not the original artwork or game bytes.
The CLI import smoke test now runs with the active Python interpreter,
including support for Python 3.9's runtime annotation semantics.

## Next acceptance gate: original runtime rendering

Do **not** automatically swap PRS to DAT, assign synthetic UVs, or declare
textures missing based on the two differences alone. To establish actual
behavior, gather a private trace from the original running game that binds
both faces (243, face 0; 319, face 0) to:

1. the source-file/load path actually selected (PRS versus DAT),
2. post-`LoadMap` local and global GFX identifiers,
3. effective UV/CLUT/tpage and draw flags,
4. source-tile and VRAM texture residency at the observed draw,
5. an original emulator screenshot/frame identifying the same scene.

Existing instrumentation and source-trace tools in this repo should be
reused. Keep captured gameplay and source bytes private; only sanitized
diagnostic evidence may be shared.

Reference: `docs/MAP02_PRS_DAT_RECONCILIATION.md`.


## Metadata-only gate before a future runtime capture

The private v10.1 audit produced a **receipt** and no game byte content. A
bounded, fail-closed validator is now available as
`tools/check_map02_ru_receipt.py`:

```sh
python3 -m tools.check_map02_ru_receipt \
  "/private/map02_ru_source_reconciliation.json"
```

It checks the declared source version, LBA and file sizes, exact source
fingerprints, decompressed size, and both face differences. It refuses
mutations and reports `source_receipt_consistent=true`, but **always**
returns `runtime_gfx_selection_verified=false`,
`disc_independently_rehashed_by_this_gate=false`, and
`original_gameplay_authenticated=false`. A JSON report is not a
signature: it can be fabricated and cannot prove the original program read
that disc during the observed frame.

For real runtime evidence, separately run the existing
`tools.verify_map02_capture`, source/GTE join, and native GPU/VRAM
witness checks on a **private capture**. Only independently bound same-run
observations may resolve the PRS/DAT selection. Never infer a GPU event,
CLUT, UV or screenshot from this source-data receipt.

No new private game file needs to be uploaded to GitHub to use this gate.


## Independent RU receipt + PC-port trace reconciliation

A second optional, **local-only** gate now accepts a previously audited
RU source receipt and an independently captured PC-port stdout bundle.

```sh
python3 -m tools.reconcile_map02_ru_runtime_trace \
  "/private/map02_ru_source_reconciliation.json" \
  "/private/map02-pc-capture"
```

The second argument is a directory previously generated by
`tools.capture_map02_runtime`, containing `capture_report.json`,
`game_stdout.log`, and `map02_trace.jsonl`. The verifier:

- rejects symbolic links on these evidence files;
- independently replays raw stdout and verifies stored JSONL SHA-256;
- requires pinned unmodified upstream source provenance and *full* trace mode;
- requires both target faces and a consistent PRS or DAT variant at **both**
  post-load and renderer submission stages in each map-load episode;
- refuses missing renderer visits, omitted face submissions, mixed variants
  across game loads and inconsistent aggregate results;
- emits only short hashes, counts, status flags and the observed trace variant.

This is a source/trace **consistency** check, not a single-game-source
attestation. **The PC-port capture has no cryptographic proof that its
executable read the exact private RU image whose resource hashes appear
in the source receipt.** CI tests use a synthetic native executable and
synthetic events; they cannot establish retail PS1 execution. The output
deliberately marks `same_owned_disc_used_by_executable_proven=false`,
`original_gameplay_authenticated=false`, and
`native_gpu_ft4_and_vram_verified_by_this_tool=false`.

Actual pixel correctness requires the existing independently verified,
same-session source/GTE/FT4/VRAM capture chain. Do not replace art assets
or label a source patch correct on the strength of a PRS/DAT classification.


## Direct read-only check against the user-owned RU image

A stronger optional gate re-reads the **full pinned raw image** on the Mac
instead of trusting a JSON-only source receipt. Execute it from this
repository's root, keeping both inputs **outside the repo**:

```sh
python3 -m tools.verify_map02_ru_owned_disc \
  --disc-image "/private/path/to/Vandal_Hearts_(RU)_v1.6.bin" \
  --receipt "$HOME/Documents/NintendoSwitchRemakesAudit/map02_ru_source_reconciliation.json" \
  > "$HOME/Documents/NintendoSwitchRemakesAudit/map02_ru_owned_disc_verified.json"
```

The original image is opened read-only, must be a **regular file**, not a
symlink, exactly 664,849,248 bytes, and match pinned SHA-256
`48c686f9ae7e57615c06fd20d1048b2b8e9e7debabc371e6e941821b6b3b121a`.
The existing Mode2/Form1 CD reader independently validates all 12 PRS
and 117 DAT source sectors (sync, Mode2, XA Form1 and EDC); the existing
PRS decoder must reproduce all pinned resource hashes, 187,264 decoded
bytes and both exact target-face GFX differences. Image file identity
and modification timestamp are checked after the sector reads.

If a private, previously recorded **full** PC-port capture exists, append
`--capture "/private/path/to/pc-capture-directory"` to cross-check the
original stdout and rendered-face submission events. No capture is
created by this command; the capture's provenance and two loaded/drawn
faces are verified by `tools.reconcile_map02_ru_runtime_trace`.

The output report is metadata-only: no image paths, original bytes, tile
pixels, audio, textures or original source-file contents are written.
Keep the image, private stdout and raw GPU/VRAM captures off GitHub.
A successful independent disc read establishes the local image's source
identity, not that a **separately launched process** opened precisely
that image. The output always marks
`same_owned_disc_used_by_executable_proven=false`,
`actual_gameplay_authenticated=false`, and
`native_gpu_vram_pixels_verified=false`.

The CI test mocks the original disc read and PRS data. Its success means
the failure gates and dataflow are exercised, **not** that a retail CD
was present on the CI runner.

 
### Single-open image identity guard

The direct-check tool hashes and sector-reads through a **single read-only
file descriptor**, opened with `O_NOFOLLOW` when supported. It never reopens
the original pathname for either MAP02 file after computing the digest.
It checks the original inode, device, size and nanosecond modification
timestamp against both the open descriptor and the pathname before accepting
the result. Replacing or modifying the named BIN during the check causes
failure; tests exercise both cases. This addresses the earlier two-reopen
race, but it is not a malicious-kernel attestation and cannot prove the
runtime PC executable used this specific disc.

The public `read_sectors(path, ...)` API is unchanged. The new
`read_sectors_from_stream(handle, ...)` implementation lets trusted callers
reuse their open handle while retaining the established Form1 EDC checks.


### One-command macOS runner (optional)

After checking out this PR's audit branch into a separate, clean directory,
run **with Bash**, not as a directory or executable. This avoids the earlier
`zsh: permission denied` error:

```sh
bash tools/run_local_map02_ru_owned_disc.sh \
  "/path/to/Nintendo Switch Remakes — Originals"
```

The script defaults to the existing v10.1 private receipt at
`~/Documents/NintendoSwitchRemakesAudit/map02_ru_source_reconciliation.json`
(or takes an explicit second receipt path). It checks for real, non-symlink
inputs, writes a temporary report using `umask 077`, and atomically publishes
an exclusive private result to
`~/Documents/NintendoSwitchRemakesAudit/private-map02/map02_ru_owned_disc_verified.json`.
It **does not overwrite** an existing result. Failures leave no published
success report, and no original resources are copied or extracted. Keep this
command on the Mac with the owned BIN; never run it in public CI against
original game assets.
