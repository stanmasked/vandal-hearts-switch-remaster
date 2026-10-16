# MAP02 v61 — private, local-only DMA2 GPU capture preflight

## Purpose and scope

v61 is an **offline-only** tool for a legally obtained PS1 GPU DMA2
linked-list RAM snapshot. It does not connect to any service, upload input,
commit user assets to GitHub, publish GPU instructions or claim that a
structurally valid file must originate from the retail game.

It builds on v60's strictly bounded GP0 opcode decoder. The v61 patch also
fixes an important GPU-state error: **GP0(E6) mask-set/mask-check are
persistent GPU drawing state between successive DMA OT lists**, unless a
separately issued GPU reset/reconfiguration changes it. The v60 decoder
previously reset both at the start of *every* listed frame. The parser now
carries the mask state forward and tests a new frame whose FT4 arrives before
its next E6 command. It cannot prove an external GP1 reset *didn't* occur
between separate captured DMA lists; the report says so.

## Local-only invocation

Run on a trusted local machine with the project's Python package:

```bash
python3 -m tools.audit_map02_v61_private_capture \
  --ram /private/ps1_gpu_ram.bin \
  --manifest /private/ps1_gpu_manifest.json \
  --context /private/capture_context.json \
  --output /private/v61_sanitized_report.json
```

When running one level ABOVE the repository root, use
`python3 -m remaster.tools.audit_map02_v61_private_capture` instead.

The RAM manifest **retains the v60 schema** and SHA256 check:

```json
{
  "format": "ps1-dma2-linked-list-ram-v1",
  "source_class": "user-supplied-unverified",
  "base_address": 4096,
  "entry_points": [4096],
  "sha256": "REPLACE_WITH_64_LOWERCASE_SHA256_HEX_CHARACTERS"
}
```

The base address and entry point are *examples only*: enter the actual
captured RAM slice load address and the genuine DMA2 ordering-table head.
Do not guess values or assume `4096` in a real capture. SHA256 is over
the exact input binary bytes; a valid hash proves integrity only, **not
retail authenticity**.

The optional context JSON declares *unverified capture metadata*:

```json
{
  "schema": "map02-v61-local-capture-context-v1",
  "method": "emulator-debugger",
  "scope": "MAP02",
  "frame_indices": [0],
  "reset_status": "unknown"
}
```

Method choices: `unknown`, `emulator-debugger`,
`hardware-probe` or `reconstructed`. Scope may be `MAP02` or
`unknown`. Frame indices must be strictly increasing and match the
manifest's number of ordering-table entry points. Reset status may be
`unknown` or `no-reset-observed`, never a claim of verified non-reset
hardware state. Extra fields (including identifying names, discs, serials,
paths, emails or unsupported claims of verified provenance) are refused.

To compare *two private captures* without disclosing contents, add:

```bash
  --compare-ram /private/second_gpu_ram.bin \
  --compare-manifest /private/second_manifest.json
```

The comparator checks all GP0 semantic event order, mask transitions,
FT4 geometry/UV/texture attributes internally and publishes only Boolean
equivalence. A match does **not** prove independence, retail origin, pixel
fidelity or original MAP02 provenance. Identical RAM bytes are labeled as
such, to prevent accidentally treating one copied file as an independent
capture.

## Privacy and malformed inputs

- Input is bounded to 4 MiB RAM binary, 16 KiB manifest, 8 KiB context.
- Only normal files; symbolic links, directories, oversized files and
  duplicate JSON keys are refused.
- Manifest sha256, pointer alignment/bounds, GPU commands, OT cycles,
  unsupported opcodes and E6 reserved bits remain fail-closed.
- By default, reports only include counts, Boolean status gates and a
  checksum. **No private raw GPU bytes, coordinates, textures, source file
  paths, user annotations or per-pixel output** are written to reports.
- Rejected inputs produce intentionally sanitized error categories rather
  than original file names, data words or source-value excerpts.
- The output must not overwrite an input file or target a symbolic link.

**Privacy caveat:** anyone with read access to the user's local files can
read the raw inputs. This script makes no network requests, but users should
not upload their original RAM, gameplay capture or locally produced VHT1
trace to GitHub Actions. It does not encrypt input files or guarantee the
privacy of other programs on the host.

## Reproducible CI (no retail assets)

The inherited GCC/Clang CI performs only a locally generated **synthetic**
PS1-format 19-node/11-E6/11-FT4 DMA capture, joined to the executed original
PC-port VHT1 trace from v59. New adversarial tests validate:
- GP0(E6) state continuity across frame boundaries;
- source integrity, bogus retail-origin assertions and uncertain resets;
- symlink/special-file refusal and JSON duplicate-key attacks;
- tampered mask or FT4 semantics across a second capture;
- bounded sanitized output and input-overwrite safeguards.

No authentic PS1 RAM, retail MAP02.PRS, Switch gameplay or proprietary
assets are used in CI. Passing synthetic tests is a development gate only.

Every audit result keeps these **closed**:

`retail_gp0_provenance_verified=false`

`original_retail_MAP02_verified=false`

`HD_replacement_approved=false`

The PR remains a stacked **draft on v60**, with no changes to `main`.

### Following gate

A future v62 could support additional GP0 packet families when a real
capture demonstrates their presence, with independent packet-boundary
fixtures and a locally reproducible hardware/emulator reference. No
unsupported opcode should ever silently be guessed as an E6 command.
