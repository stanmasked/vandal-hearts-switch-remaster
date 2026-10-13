# Sound buffer and transfer-lifetime audit

Scope: pinned upstream PC-port revision `14552fffa0e0b47e02b57592e274fc6e7a649923`, primarily `src/core/cd.c`. This is static source analysis; it does not copy upstream implementation code or establish runtime behavior on Switch.

## Findings

### 1. The sound work pointers are a small set of logical offsets

The US tree defines `SOUND_WORK_PTR(addr)` for the PC build as an offset into a static `sPcSoundWorkRam[0xc0000]` allocation based at logical guest address `0x80140000`. The sound-set table currently points at:

| Guest address | Offset from `0x80140000` | Table use |
|---|---:|---|
| `0x80140878` | `0x0878` | VAB set 0 |
| `0x80141878` | `0x1878` | VAB set 1 |
| `0x80144878` | `0x4878` | VAB set 2 and its variants |

The PC allocation size `0xc0000` matches the remainder of the 2 MiB guest RAM window from `0x80140000` to `0x80200000`; it is not evidence that a single VAB needs that much storage. The actual VAB header/body transfer sizes and any downstream writes must be traced before shrinking it. The Japanese tree uses different offsets (`0x272c`, `0x372c`, `0x672c`) but the same general storage seam.

### 2. CD loading writes to caller-selected buffer pointers

The `gCdFiles` table associates many files with `gScratch3_80180210` and some with `gScratch1_801317c0`. The loader's CD-read path passes `gCdFiles[gCdLoader.cdf].bufferPtr` to `CdRead`. VAB setup assigns the selected sound set's `bufferPtr` to the VAB-header entry before calling `LoadCdFile`; the state machine then opens the header and starts body transfer using the body entry's `bufferPtr`. Sequence loading similarly assigns a buffer from `gSeqSets` before loading.

This means the loader is not merely allocating a local temporary: its table-selected destination is consumed by subsequent audio-library calls. Buffer lifetime must extend until those consumers finish. Replacing the shared staging area with a stack buffer would be unsafe without proving that all pointers are consumed synchronously.

### 3. What is and is not established about overlap

- Multiple sound-set variants intentionally reuse the same work address for VAB ID 2.
- Many CD entries reuse `gScratch3` as a staging destination; sequential state-machine steps select which file is being loaded.
- The source table alone does **not** prove that two asynchronous reads never overlap, nor that audio middleware stops referencing a header/body immediately after a state transition.
- The PC-specific sound-work allocation and the PC data-segment symbol `gScratch3` are separate host allocations. They should not be assumed to alias merely because both stand in for PS1 guest RAM addresses. A Switch-wide memory model should decide whether guest-address regions share one backing allocation or whether every legacy pointer is adapted individually.

## Switch implications

1. Prefer a single, explicit guest-RAM backing store if feasible, so guest addresses that fall in the same PS1 RAM window preserve aliasing by construction. If using separate allocations, document and test every range and alias assumption.
2. Keep staging destinations alive for the complete CD/audio consumption period; do not migrate them to automatic storage.
3. Preserve reuse of the VAB ID 2 work area until VAB close/transfer completion behavior is understood.
4. Add tests around a small adapter that translates each known guest address to a bounded host span. Do not size storage based solely on the current table's base addresses.
5. Before reducing the `0xc0000` prototype allocation, inspect the audio library's maximum writes, alignment, and retained-pointer behavior. The source facts above are insufficient to justify a smaller buffer safely.

## Evidence

Upstream source locations reviewed: `src/core/cd.c` definitions of `SOUND_WORK_PTR`, `gSoundSets`, `gCdFiles`, `LoadCdFile`, the CD-read path around line 990, VAB setup/continuation around lines 1060–1122, and sequence loading around line 1147. The line numbers refer to the pinned revision and may shift on upstream changes.
