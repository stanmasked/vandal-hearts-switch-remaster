# MAP02 — source capture MAP/VRAM identity across FT4↔GPU-window verification

The parent [Draft PR #384](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/384)
already has successful CI for a **66-event synthetic** source FT4
match through two full native GPU capture windows and the
private SHA witness publisher. However, a source game asset was read
by the original GTE bundle verifier and later used again during native
window material comparisons, without a strict original-file identity
check spanning those expensive phases.

## Source asset mutation threat

Two private user-owned files are relevant:

- `map02.decoded.bin`: precisely **187,264 bytes** of locally decoded
  original MAP02 source data, passed to the compiled source/GTE verifier;
- `gpu-vram-le.bin`: precisely **1,048,576 bytes** of original source
  BGR555 texture and palette VRAM.

A changed source VRAM word *outside the subset sampled by the selected
FT4* could leave a source↔native texture equality result apparently
valid, even though the private game snapshot was modified during
checking. A byte-identical **inode replacement** of the decoded game map
might also fool a checksum-only comparison even when a user-side
capture was replaced between the original source/GTE run and the final
witness report.

## Defensive change

The actual source/native window join now reads both original private
source assets using the existing strict `private_file` utility **before**
compiled-GTE verification. This pinned reader double-reads a bounded
regular file using `pread`, rejects symlinks, non-owner links,
unexpected sizes and mid-read replacements, and returns its exact
filesystem identity (device, inode, UID, permissions, link count,
size, mtime and ctime).

The two original byte arrays and inode identities remain fixed throughout
the source/GTE verification, native window full-VRAM replay,
source↔GPU texture/CLUT material equality, source/DrawOTag ordering,
and final full native window repeat-audit.

**Before the final result is reported**, both original private assets
are read again using the same strict mechanism. Any changed byte or
inode identity refuses the witness. Accepted reports include the
sanitized boolean `source_map_vram_inode_and_bytes_reverified=true`
without disclosing original paths, map contents, screenshot pixels or
source hashes.

## Synthetic negative and cross-platform tests

Three additional source witness tests independently replace:

1. an unreferenced VRAM word at the far end of the 1-MiB source image
   while the expensive source/GTE verifier is executing;
2. the source decoded map's inode with a **byte-identical** local copy,
   using atomic replacement;
3. the last byte of the source decoded MAP02 file.

All three must fail even if selected FT4 materials and the native
window file tree remain valid. Existing positive synthetic source/
native GPU window, source FT4 join, and exclusive private SHA witness
publication tests must remain green.

The **Linux** and **macOS 15 Intel Python 3.9/3.11** CI matrix runs
14 distinct source/witness/CLI tests and 15 imported native window
fixture tests (29 executions per job). In the synthetic source tests,
the expensive `verify_bundle` step is deliberately mocked, but the
private-file reads, per-window 1-MiB VRAM snapshot checks, upload
content, and full native verifier actually execute.

## Evidence boundaries

This hardens the source-asset time-of-check/time-of-use boundary,
not the origin/authenticity of the retail data. It cannot exclude
a malicious privileged process from changing an entire operating system
or create a genuine original PS1/GTE capture. No original disc,
proprietary asset, private capture, actual Catalina 10.15.7 runtime or
physical Switch hardware is accessed or published.

All modifications remain Draft, with `main` unchanged and no merge.
