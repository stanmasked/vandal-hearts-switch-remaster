# MAP02 private BK2 chronology: Start → later unverified candidates

This tool links **two separately maintained Draft pipelines**, without
merging them or copying personal media into GitHub.

- [PR #407](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/407)
  produces a **sanitized local JSON report** after validating three private
  screenshots around the known first Start input at BK2 index 1661.
- [PR #409](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/409)
  validates *both* privately supplied candidate logs, manifests and full
  screenshots; the first manually labelled candidate must visibly differ
  from the most recent preceding image.

This stage rejects **any** candidate observation at or before the Start
capture's third emulator counter (1663). The full movie has 933,949 input
frames; all candidate frames must remain inside it. It does not reinterpret
the first Start itself as MAP02.

## Use on the owner's private computer

First run the #407 Start-capture verifier exactly as documented on its branch
using the owner-held BK2 and PS1 game/BIOS. Save its sanitized JSON result in
a private file such as `/private/vh-start-report.json`. The owner must keep
the original Start logs and PNGs; this bridge does **not** independently
reverify Start PNG bytes or authenticate that sanitized report.

Then, using distinct owner-local candidate logs, screenshot manifests and
PNG roots as described in #409:

```bash
umask 077
python3 -m tools.verify_map02_private_start_candidate_order \
  /private/vh-bk2-inspection.json \
  /private/vh-start-report.json \
  --first-markers /private/run1/candidate-markers.log \
  --first-manifest /private/run1/candidate-manifest.json \
  --first-images /private/run1/images \
  --second-markers /private/run2/candidate-markers.log \
  --second-manifest /private/run2/candidate-manifest.json \
  --second-images /private/run2/images
```

The script strictly checks the report schema and conservative provenance
flags, requires the same **933,949-frame** BK2 inspection and known Start
index **1661**, and independently runs the full decoded-RGBA private
candidate checks on both owner-provided observation sets. It then enforces
that all candidate counters exceed **1663** and all input indices stay
inside the movie. The output only contains booleans and aggregate counts,
not user paths, frame-candidate numbers, image bytes or SHA-256 values.

**Critical limitations:** the Start JSON is a user-supplied assertion,
not a signed report. This stage cannot independently authenticate its
underlying screenshot bytes. Two separate file trees do not prove two
actual emulator processes. All image labels and the candidate scene
boundary remain manually assigned. A visible pixel difference might be
a cursor, animation or unrelated menu screen, **not necessarily MAP02**.
Neither PS1 game provenance nor movie→video offset nor GPU/VRAM parity
has been established. Every such output flag remains `false`.

GitHub Actions uses **only invented movie inspection and 1×1 PNG
fixtures**; it has no original BK2, game image or private capture data.
Do not upload private files or original assets. PRs remain Draft;
`main` is not changed.
