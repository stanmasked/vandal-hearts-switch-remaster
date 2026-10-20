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
