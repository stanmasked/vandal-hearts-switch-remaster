# Vandal Hearts (USA) — offline BizHawk BK2 input replay preparation

This optional developer-only tool consumes an **owner-private** movie
recorded with **BizHawk / PSX / Octoshock**. It is an exact-frame input
timeline analyzer, not an emulator, retail PS1 capture, frame renderer or
a proof of original MAP02 GPU identity.

## Owner-local command

From the repo checkout or an approved **local** copy of the tool:

```bash
python3 -m tools.inspect_map02_private_bk2 \
  /path/to/owner-private/vandalhearts.bk2
```

The tool streams the movie's `Input Log.txt` from the archive, checks
`Header.txt` and `SyncSettings.json` for **Vandal Hearts (USA)** /
**Octoshock**, one digital PS1 controller with memory cards/multitaps
off, and the exact expected 17-button/4-axis BizHawk `LogKey` order.

It returns sanitized aggregate JSON: total zero-based frames,
state-change frames, individual button press onsets, counts of active
frames, nonneutral analog frames, per-button counts, longest
no-button interval and explicit provenance limitations. User paths,
private movie bytes, author strings and ROM/firmware hash identifiers
are **not** copied into the JSON. Frames are zero-based, and timing
comes from the movie's recorded frame count; **do not assume real
elapsed time or PAL/NTSC playback timing without checking the core**.

To export **only a selected bounded timeline** to a private local CSV
(mode 0600, exclusive create, no overwriting), after the beginning of
the recorded movie has been reproduced independently in BizHawk:

```bash
python3 -m tools.inspect_map02_private_bk2 \
  /path/to/owner-private/vandalhearts.bk2 \
  --start-frame 1600 --window-frames 350 \
  --private-events-csv /path/to/owner-private/controls-window.csv
```

That CSV holds exact frame offsets, which buttons were pressed/released,
and the set currently held after each change. The first event at the
requested start is always emitted to establish the held state.
Individual exports are limited to **24,000 frames**. The analyzer still
reads the entire archive to ensure stable frame indices and flag
unsupported disc/reset changes before writing an export.

## Inspected private recording (results only; NOT committed)

The owner-supplied `vandalhearts.bk2` was inspected locally.
It identifies `Vandal Hearts (USA)` and `Octoshock` and contains:

- **933,949** recorded input frames
- **20,152** button-state change frames
- **13,150** button press onsets
- **0** nonneutral analog-input frames
- first Start press at **zero-based frame 1,661**
- no embedded save-state member in the supplied ZIP; sync settings
  disable memory cards and multitaps

These aggregate observations are **not sufficient to locate MAP02 or
prove gameplay completion**. The short `SHA1` identifier in an old
BizHawk movie header is NOT treated as a verified full 40-hex
PlayStation disc SHA-1. Deterministic replay depends on a compatible
game image, Octoshock core, firmware, initial state and synch settings.

Before a real MAP02 frame number can be used for a source/native GPU
test, reproduce this exact input movie on a **matching private PS1
setup**, identify the map through actual emulator display/game state,
and collect authentic frame/VRAM and source-keyed GPU evidence. Never
infer the MAP02 scene boundary from a long idle interval alone.

## Strict parser and CI boundary

Only the movie headers and input log are read; unexpected ZIP members,
symlinks, oversized inputs, duplicate entries, mismatched LogKey/
game/core/synchronization, unsupported disc/reset control changes
and broken end markers fail closed. Input frames are processed
incrementally with bounded memory. Private file paths are removed from
CLI errors. No network access, GitHub upload, game assets or BIOS
read operations are performed.

The CI uses **twelve wholly invented miniature BK2 archives** generated
by the checked-in test module; no owner movie, original disc/BIOS,
copyrighted screenshots, original controller log or real map timestamps
are included. Its job checks Python 3.9 and 3.11 plus real macOS 15
Intel compatibility.

Keep this work in a separate Draft PR. Do not publish the owner
movie, raw input CSV or unverified game scene timestamps. `main`
and existing GPU parity requirements remain untouched.
