# MAP02 — owner-private distributed persistent raster change

This strictly optional witness builds on the prior unmerged Draft [#413](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/413).
It seeks **stronger evidence of a sustained change in supplied screenshots**,
not proof that the original Vandal Hearts PS1 game was actually run, or that
MAP02 began at any particular movie index.

## Owner-local command (private data never goes to GitHub)

Run the previous Start-to-candidate protocol first using two separately
retained Octoshock PLAY logs, private manifests and PNG folders. Each manifest
needs, in chronological order, at least:

- A `pre_map02` screenshot (the **last** one before the candidate is used).
- The first `map02_candidate` screenshot.
- A `post_map02` screenshot taken within **120 emulator counters** after
  the candidate screenshot.

Both sessions must have matching input counters, labels and decoded RGBA
rasters; every observation must be after the known Start capture counter
1663 and inside the 933949-input BK2 movie. The sanitized Start report
remains owner-supplied and not independently authenticated by this stage.

With Pillow installed:

```bash
umask 077
python3 -m tools.verify_map02_private_persistent_raster \
  /private/vh-bk2-inspection.json /private/vh-start-report.json \
  --first-markers /private/run1/candidate-markers.log \
  --first-manifest /private/run1/candidate-manifest.json \
  --first-images /private/run1/images \
  --second-markers /private/run2/candidate-markers.log \
  --second-manifest /private/run2/candidate-manifest.json \
  --second-images /private/run2/images
```

The verifier decodes the three selected images to RGBA in each supplied
run, compares the candidate and post frames to the last pre frame, and
requires a **common set of genuinely stable changed pixel values** of at
least 1% of image area (minimum 16 pixels). A pixel counts only when
its decoded RGBA value is **different in the candidate from the pre frame
and remains exactly the same in candidate and post**. Merely changing at
the same coordinates in both later frames is insufficient (e.g.,
RGB 10→100→120 fails). The qualifying positions must cover at least
**4 out of a 4×4 grid of screen tiles**. Screenshots must retain
identical dimensions and be at least 16×16. A one-pixel blinking cursor,
a transient single-frame effect, a tiny localized indicator or a remote
post-candidate frame will be rejected.

This stronger comparison is schema
`vh.map02.private-persistent-raster-witness.v2`. Added invented tests
explicitly reject two unrelated large frame changes, candidate/post RGBA
differences (including alpha changes), and 15 stable pixels among many
moving pixels. Exactly 16 stable positions across multiple tiles are
accepted. The original BK2 and user screenshots remain private.

These spatial/temporal cutoffs are conservative *heuristics for manual
screen review*. They might reject a genuine but small PS1 scene change,
and a large menu overlay, full-screen fade, HUD repaint or animated
background could still pass. The result therefore says only that the
**provided raster evidence** has a distributed change which lasts into
a later screenshot.

All provenance flags remain false: no source PS1 disc/BIOS/game
authentication, movie-to-displayed-frame offset, independent two-process
replay evidence, MAP02 scene identification or GPU/VRAM parity. Output
contains no screenshot pixels, frame IDs, private paths or PNG hashes.

GitHub Actions executes only invented 16×16 synthetic PNG fixtures
across Ubuntu Python 3.9/3.11 and Intel macOS Python 3.11. Original
screenshots, owner's BK2, ROM, BIOS and logs stay off GitHub. Keep all
PRs Draft. No changes to `main`.
