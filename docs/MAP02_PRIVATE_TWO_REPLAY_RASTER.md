# MAP02 BK2 — private two-replay decoded raster consistency

This stage follows Draft PR #403. It does **not** authenticate an original
PlayStation disc, emulate Vandal Hearts, identify MAP02, prove movie-to-video
frame alignment, or establish GPU/VRAM parity. It compares only *user-owned,
privately retained* captured PNG rasters against manually entered candidate
labels and existing BizHawk PLAY markers.

## Owner-local procedure

1. On the owner's private computer, play the exact BK2 in BizHawk Octoshock
   with the owner-held PS1 game/BIOS. Start two separate sessions and record
   console markers using the existing read-only Lua observer. Reuse the same
   unverified candidate input frame indices in both sessions.
2. Capture corresponding PNG screenshots into different private image
   directories. Save *separate* marker logs and visual manifests in each
   session directory. The image manifests use the established
   `vh.map02.private-visual-candidates.v1` schema from PR #402 and must
   contain a `pre_map02` observation followed by a
   `map02_candidate`. Counter, candidate input and manual label sequences
   must match exactly in both runs.
3. Store the two full evidence sets and the BK2 inspection JSON **outside
   the public GitHub checkout** with permissions `umask 077`. Do not upload
   original BK2, game/BIOS, marker logs, screenshots or image SHA-256.
4. With Pillow installed locally, run:

```bash
umask 077
python3 -m pip install 'Pillow>=10,<12'
python3 -m tools.compare_map02_private_replay_rasters \
    /private/vh-bk2/inspection.json \
    --first-markers /private/vh-bk2/run1/markers.txt \
    --first-manifest /private/vh-bk2/run1/manifest.json \
    --first-images /private/vh-bk2/run1/images \
    --second-markers /private/vh-bk2/run2/markers.txt \
    --second-manifest /private/vh-bk2/run2/manifest.json \
    --second-images /private/vh-bk2/run2/images
```

Both sessions are checked independently by the existing marker, PNG CRC,
bounded-IDAT and SHA-256 validators; then Pillow **actually reconstructs**
each PNG image to RGBA and compares the width/height and per-pixel digest
at each matching input candidate. Different PNG compression levels or byte
encodings can pass if the decoded RGBA pixels are identical; changed pixels,
metadata markers, manual labels, symlinks and reused input paths fail.

A second, independent **visible-change witness** now compares the last
captured `pre_map02` raster against the first captured `map02_candidate`
raster **within each replay**. A candidate pair with identical decoded
pixels is rejected, even if both sessions are otherwise perfectly
repeatable: two still screenshots are not evidence of a visible transition.
At least one changed decoded pixel is required. Later `post_map02`
screenshots are allowed to repeat. The sanitized report adds
`candidate_boundary_raster_change_observed=true` but explicitly keeps
`scene_transition_authenticated=false`.

This check does **not** mean that the changed pixels depict MAP02: it could
just be a flashing cursor, sprite animation or unrelated UI transition.
No scene classifier, timing calibration or emulator provenance is implied.

The printed report contains no image names, paths, pixels or original hashes.

The two inputs are merely *separate user-supplied file sets*. The script
cannot authenticate that BizHawk was really run twice, that the ROM is the
original game, or that the screenshot belongs to the declared frame.
A successful private comparison proves **repeatability of the supplied
raster evidence**, not correctness against the PS1 game. The source MAP02
boundary remains unknown until authentic game replay and independent
scene/GPU witnesses are obtained.

GitHub Actions runs only tiny invented PNGs and invented frame markers.
No original BK2 or owner screenshots enter CI. Keep this chain Draft.
