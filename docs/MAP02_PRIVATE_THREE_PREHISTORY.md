# MAP02 — three-frame prehistory of private BK2 imagery

A conservative, optional improvement over the owner-private BK2
[animation filter in Draft PR #425](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/425).

**Purpose:** two pre-candidate screenshots may look identical even if
an animation was visible in an earlier screenshot (e.g. pixel phases
B → A → A). Comparing only A and A in #425 could wrongly count those
positions as newly changing at a later candidate. This stage requires
**three prior frames** and refuses to count pixels whose entire decoded
RGBA value changed during *either* earlier interval.

## Evidence to keep locally

Each of the two supplied (not independently authenticated) BizHawk
Octoshock playback datasets now needs at least **five** separately
named PNG captures in strict movie-counter order:

1. Oldest of the **three** recent `pre_map02` observations.
2. Next `pre_map02` observation.
3. Last `pre_map02` observation.
4. First manually labelled `map02_candidate` observation.
5. First following `post_map02` observation.

Each adjacent capture must be at most **120 emulator counters** apart.
All observations must be later than the existing Start-anchor capture
through counter 1663, remain inside the 933949-frame BK2 and pass
the inherited private marker, PNG CRC/IDAT/SHA and paired decoded-RGBA
checks. The newest three pre frames are used if more are provided.

Qualifying pixels must have **identical RGBA** in all three pre frames,
change at the candidate, and have **identical changed RGBA** in the
candidate and post. They still must cover at least 1% of the image
(minimum 16) and at least four of 16 image tiles. For a 64×64 image
the 1% threshold is rounded up to 41 pixels.

Run entirely on the owner's computer with Pillow:

```bash
umask 077
python3 -m tools.verify_map02_private_three_pre_history \
  /private/vh-bk2-inspection.json /private/vh-start-report.json \
  --first-markers /private/run1/candidate-markers.log \
  --first-manifest /private/run1/candidate-manifest.json \
  --first-images /private/run1/images \
  --second-markers /private/run2/candidate-markers.log \
  --second-manifest /private/run2/candidate-manifest.json \
  --second-images /private/run2/images
```

The report contains only bounded counts and booleans, without private
paths, hashes, image data or particular candidate frame numbers.

## Interpretation

This is **not a scene classifier**. Three widely separated or
periodically aliased samples may still show identical colors even
when an animation exists, and a genuine MAP02 transition with a
moving backdrop could be rejected. Neither a real PS1 game execution
nor separate BizHawk emulator processes nor movie-to-screen frame
calibration nor GPU/VRAM parity is authenticated by the tool.
The Start report remains privately supplied and is not a signature.

Public GitHub Actions tests **only 14 synthetic cases** using invented
16×16 PNGs plus a synthetic 64×64 rounding-boundary test on Ubuntu
Python 3.9/3.11 and Intel macOS Python 3.11. No original BK2,
PS1 game/BIOS, real images or private logs are checked into GitHub.
This branch is Draft and cannot be mistaken for completed MAP02
identification; `main` is left untouched.
