# MAP02 — owner-private BK2 controller-neutral review windows

This follows Draft PR #415's full-source BK2 fingerprint validation.
It is an **offline candidate-window planner**, not a map recognizer.
Its output must remain on the owner's computer because the exact frame
indices are derived from the user's private movie input history.

## What the scanner actually measures

The scanner reads the complete BK2 input stream using the existing
bounded Octoshock ZIP, input-log and synchronization validators. It
requires the previously observed *recording aggregate*: 933949 frames,
20152 button-state changes, 13150 presses, first Start at zero-based
index 1661, all four analog axes neutral.

A **controller-neutral interval** is a run of frames when no digital
buttons are held, with at least one held-button frame immediately before
AND immediately after the run. Both edge frames must be inside the
requested review region. Pauses at movie start and end are always
excluded. By default the tool selects spans of **180–1800 input frames**
and returns at most **20** windows, sorted by duration descending,
then by earliest movie input frame; ties and ranks have **no scene
probability meaning**.

These quiet intervals can occur during loading, a menu, an animation,
a cinematic, a tactical battle, or inactivity. **Do not infer MAP02,
a scene boundary or a PS1 video frame from any result**.

## Run privately, without GitHub upload

From an owner-local checkout, with the previously supplied BK2 stored
outside the Git repository:

    umask 077
    python3 -m tools.map02_private_bk2_neutral_review_windows \
      /private/vandalhearts.bk2 \
      --min-neutral-frames 180 \
      --max-neutral-frames 1800 \
      --max-windows 20 \
      > /private/vh-neutral-review.json

Optional exact movie-input range controls:

    --after-input-frame 25000 --before-input-frame 150000

The original Start onset (1661) is excluded from default suggestions.
The report returns an ordered list with each quiet interval, its
duration, and three **proposed input indices**: last held-button
frame before the interval, midpoint, and first held-button frame after
the interval. These are coordinates in the **zero-based BK2 input log**,
not confirmed emulator frame counters.

A downstream owner-local BizHawk screenshot helper may use these
indices as a **provisional** guide only after independently calibrating
the actual movie-to-emulator and displayed-frame relationships. The
current tool reads no PNG, screenshot, disc, BIOS, GPU or VRAM.
The script does not even invoke BizHawk or a PS1 emulator.

If no intervals qualify, an empty review list is a legitimate and
useful result. Do not relax the fingerprint constraints or invent a
MAP02 position. Narrow time/scene search using real locally observed
screenshots when available.

**Never commit or upload** the original BK2, private output JSON,
event logs, screenshots, original PS1 assets or BIOS to public GitHub.
GitHub CI tests this with a completely fabricated 933949-frame movie
and invented button presses; it has no real map identity or timing.
Keep all PRs Draft until real private playback establishes evidence.
