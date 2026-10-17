# MAP02 v98 — failure-safe private journal recovery without replacement

The pinned PCSX ReARMed v97 observer proved four real **emulator**
VBlank callbacks, the original 2,380 synthetic MIPS VRAM readbacks,
4,128 native events with no drops, source/cache erasure after reset and
complete stale-output-buffer clearing. v98 addresses a separate
lifecycle risk: **what happens when saving a private result fails or
another observer generation wants to use an already occupied path?**

## Existing, locked-down POSIX publisher

v82's original `vh82_publish_private` still owns the only actual
private export for the signed four-VBlank / original Unai/GPU host
diagnostic chain. It writes a mode-0600 file through a newly created
`.tmp` using `O_EXCL|O_NOFOLLOW`, fsyncs and reads its bytes back,
then uses a **hard link rather than replace-capable rename** to create
the final output. An existing final path or existing temp file is
never overwritten, regardless of what the caller wants to publish.

v98 adds `vh98_publish_recovery(previous_path,next_path,bytes,size)`.
It requires:

- A separate, non-identical, absolute next pathname (the prior
  pathname cannot be reused to replace a failed or older result).
- An existing **regular 0600 previous file** opened using
  `O_NOFOLLOW`; no previous symlink, missing file, weak permissions
  or multiply-hardlinked previous file is accepted.
- Both paths must satisfy bounded length and traversal safety.
- The new file is saved by **the unchanged v82 exclusive publisher**.
  After publication, the old path's device, inode, size and protective
  file mode are checked again.
- The next pathname can be used successfully only **once**. Replaying
  that same target is refused, and an already existing `.tmp` is
  preserved rather than silently deleted or reused.

This is a **non-clobbering** API and does not claim transactional
protection from arbitrary adversarial concurrent writers outside the
observer's exclusive private-directory ownership. In particular,
the old file's contents are compared byte-for-byte by native tests
and by the bounded runtime marker fixture, not by a general-purpose
cryptographic function inside the recovery API. The real full
private JSONL is separately validated using its existing byte-exact
v82 readback and SHA-256 CI proof.

## Real pinned emulator host verification

After v80–v97 and original `GPUfreeze` worker drain, v98 temporarily
creates two small, unprivileged **synthetic test marker files** as
siblings of the original private export path in the same restricted
CI directory. The fixture:

1. Publishes the first marker with real `vh82_publish_private`.
2. Verifies the existing pathname cannot be overwritten, and
   `vh98_publish_recovery` refuses using that same path.
3. Publishes the second marker through `vh98_publish_recovery` to
   a new unused filename, then verifies replay to that filename
   is refused.
4. Reads back **both distinct markers byte-for-byte** and verifies
   that the first is unchanged.
5. Removes only these two owned test markers before the original
   full v82 private exporter publishes to the normal unchanged path.

All marker bytes and private full-trace files stay in the restrictive
CI private directory; none are GitHub public artifacts. The runtime
adds exactly three bounded aggregate observations after v97:
rejection of existing old filename, successful fresh target, and
rejection of duplicate recovered filename. The independent v98
verifier checks their unique correct ordering and exact values,
all prior v80–v97 stage provenance, four VBlank callbacks and
unknown host-only clock/frame ownership.

## Isolated failure/recovery tests

GCC and Clang compile the **real native publisher C source** and
verify failure/retry scenarios: old file unchanged, distinct new
target has correct byte content and mode 0600, stale `.tmp`
refusal without deletion, recovery to a different fresh path,
symlink refusal, relative/traversal pathname refusal, refusal of
world-readable prior files and stable three-generation old outputs.

Neither this diagnostic work nor the synthetic host marker scenario
demonstrates retail Vandal Hearts MAP02 GPU parity, physical
PlayStation timing or Nintendo Switch HD renderer correctness.
Original `main` remains unchanged. HD replacement remains **OFF**.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`
