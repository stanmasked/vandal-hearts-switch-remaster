# MAP02 private real-capture readiness preflight

This **read-only** preflight runs **before** the source-keyed
MAP02 GTE/DrawOTag/VRAM verification and the staged PutPixel/BlendG1
and independent VRAM-edge witness publishers. It does not create,
change or upload original game files, hash manifests or capture logs.

## Local invocation

With independently captured, private source and native GPU directories:

```sh
python3 -m tools.check_map02_private_capture_ready \
  /private/map02/source-bundle /private/map02/native-capture
```

The two directories must already exist, not be symlinks, and have
owner-only permission (typically `0700`). Do not upload them to
GitHub or copy their contents into CI logs.

This checks, without doing a complete expensive compiled-GTE verification:

- original MAP02 source bundle schema, pinned PC source revision, source
  frame, decoded-map/VRAM/GTE event SHA-256 digests;
- independently supplied PutPixel/OT and original native-overdraw
  manifest SHA-256 links, and matching source/GPU frame labels;
- full recorded native GPU event pairs with valid before/after metadata,
  strict JSONL framing and a refusal at the existing **64-event
  truncation limit**;
- canonical, bounded private **pending** PutPixel, BlendG1 and
  directly observed DrawOTag VRAM-edge JSONL, including cross-stream
  frame/coordinate/primitive consistency;
- equality of the count of recorded native GPU **draw pairs** and
  separately observed DrawOTag VRAM edges;
- selected-pixel `before` and `after` words for every draw,
  read independently from the real 1024×512×16-bit native VRAM
  snapshots (without printing or saving raw pixels).

The output is a small aggregate-only readiness report. A passing
preflight asserts **structural integrity only** and explicitly reports
that actual original game origin, complete GPU-frame coverage,
compiled-GTE correctness and PS1 physical GPU behavior remain unproven.
Even a synthetic local fixture can pass.

## Important bounded-recorder blocker

The current source-authenticating native GPU event recorder allows
**64 events**, which is at most **32 before/after pairs**, and its
source FT4 evidence capture admits up to **32 submitted faces**. The
new independent DrawOTag VRAM-edge recorder, however, can retain
up to **8192** draw primitives. That asymmetry means simply enabling
all three probes is **not sufficient** to prove the complete original
MAP02 scene: a full scene exceeding the smaller native recorder
capacity must be rejected or safely captured in smaller
source-keyed windows. The preflight rejects the 64-event cap as
potential truncation and rejects draw-count disagreement, rather
than silently marking missing primitives as verified.

Do **not** increase event limits blindly without also adjusting the
full-VRAM snapshot recorder, manifest formats, source-keyed matching,
memory/disk budgets and explicit truncation detection. No genuine
MAP02 capture has been authenticated yet.

## After preflight

Once actual independent inputs exist and preflight succeeds, run the
full private verification chain (which compiles and validates the
original PC GTE/reference geometry, AddPrim OT order and exact native
VRAM snapshots):

```sh
python3 -m tools.promote_map02_putpixel_stage \
  /private/map02/source-bundle /private/map02/native-capture
python3 -m tools.publish_map02_blendg1_witness \
  /private/map02/source-bundle /private/map02/native-capture
python3 -m tools.publish_map02_vram_edges_witness \
  /private/map02/source-bundle /private/map02/native-capture
python3 -m tools.verify_map02_vram_edges_witness \
  /private/map02/source-bundle /private/map02/native-capture
```

A passing hash chain is still not evidence of actual retail game
provenance or physical PlayStation pixel equivalence. HD replacement
remains disabled pending independent real MAP02 verification.
