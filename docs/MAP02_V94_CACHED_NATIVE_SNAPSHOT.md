# MAP02 v94 — O(1) repeated native GPU journal reads and verified snapshots

The pinned PCSX ReARMed emulator v93 confirmed genuine detailed and
aggregate journal lanes with 4,106 **globally ordered** private events
from four emulator VBlank transitions and synthetic GPU host controls.
Repeated calls to `vh80_events()` still merged both physical lanes
every time, even when no new events had been recorded.

## Cache, mutation and explicit integrity check

This opt-in diagnostic-only change (not the production Switch renderer)
retains the exact public C ABI for `vh80_events()` and keeps the original
4,096 detailed + 256 GPU aggregate **independent bounded buffers**.

- The first `vh80_events()` after reset or successful event append
  performs the existing O(n) globally ordered merge and records a
  monotonically increasing merge-count statistic.
- Each subsequent read with the same event sequence returns the same
  merged array pointer in O(1), with **no re-merge**.
- Successful `vh80_record` marks the cache stale. An explicit integrity
  check on a stale view is refused; the next getter rebuilds precisely once.
- Invalid, over-capacity or sequence-overflow event appends continue to
  fail closed through the old `dropped` counter. No truncated or
  overwritten private evidence is accepted.
- `vh94_snapshot_check()` independently walks the two original physical
  source buffers in global sequence order and compares all **five**
  fixed 32-bit event fields against the cached merged snapshot:
  sequence, kind, value, cycle and frame. A forged or mutated cached
  record is refused. The serializer performs this check immediately
  before the mode-0600 exclusive private publisher can save the file.

The integrity check is deliberately O(n), called explicitly at
synchronization/serialization boundaries, **not** on every O(1)
getter call. No raw event hash/digest of private GPU content is
placed in logs or public CI summaries.

## Native host-only regression

After the existing four emulator VBlank and 2,380 VRAM oracle
checks and the entire v80–v93 native GPU probe chain, and only after
the renderer has drained with original `GPUfreeze`, v94:

1. Reads the merged dual-lane cache **128 times**, requiring all
   pointers to be identical, no extra merges, and 128 independent
   successful source-versus-snapshot integrity validations.
2. Appends one bounded aggregate observation. Immediately verifies
   that the old snapshot is refused as stale.
3. Reads the journal again and requires exactly **one additional
   O(n) merge** and an exact new contiguous sequence entry.
4. Appends two final aggregate observations, rebuilds/validates the
   complete private snapshot and checks every sequence number again.

Three synthetic aggregate-only metrics are added to the private
journal: 128 cache hits, successful stale-view invalidation and
128 source integrity checks. The new independent strict Python
verifier requires these exact ordered records, preserves the
previous v93 checkpoint count, and continues every earlier stage
audit. GCC and Clang also compile isolated native C library
regressions that explicitly alter a cached value using a test
pointer and verify **both** integrity check and JSONL publication
fail rather than saving inconsistent evidence.

Private publication remains exclusive, byte-for-byte reopened
and mode 0600. The full private event stream and any original
retail game data remain excluded from public GitHub artifacts.

## Limits

Tests run inside a **pinned emulator, on a synthetic host-supplied
GPU fixture**, not the retail game's MAP02, not a physical PS1,
and not the production Nintendo Switch HD renderer. The cached
view is only guaranteed stable when no concurrent writer is active,
which the opt-in native test ensures via original GPU synchronization.
This does not establish correctness under unsynchronized GPU
threads, and never approves HD replacement.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`

Draft stacked on v93; `main` unchanged.
