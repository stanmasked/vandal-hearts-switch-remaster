# MAP02 branch — NeXium boot and tactical movement smoke

This check is deliberately narrow. It validates the **asset-free current Switch
prototype** compiled from this branch, **not the original PlayStation MAP02
mission or a retail-game port**.

## Evidence boundary

A dedicated workflow builds a real NRO with devkitPro/libnx, validates its NRO0
header and native host/sanitizer tests, then loads the uploaded NRO artifact
into a NeXium Linux GUI in an Xvfb virtual display. Its Python input driver
uses only mapped keyboard/controller events and ImageMagick screenshot capture.
It never patches emulator memory, reads an original disc, or claims source
pixels have been restored.

The screenshot oracle independently verifies eight states: original blue
hero and red enemy, A selection, Right cursor, an invalid three-cell move,
a legal one-cell move, A re-selection, B cancellation, and a legal return to
the initial position. It requires matching actor-colored pixels, actual
cursor coordinates, persistent enemy sprite and an **identical tactical board
crop after returning**. A changing unrelated status/heartbeat cannot satisfy
these conditions.

Three ROM-free negative tests reject blank, wrong-resolution and frozen
hand-drawn screenshots. Their success **does not** constitute real gameplay
evidence. The real-emulator marker is printed only after the NRO is launched,
controller events are delivered and captured frames independently pass the
oracle.

Expected success marker:

`VH_MAP02_NEXIUM_PROTOTYPE_MOVE_PASS boot=1 select=1 cursor=1 invalid_range=1 move=1 cancel=1 return=1 enemy_preserved=1 frame_replay=1 retail=0`

The workflow preserves original X11 screenshots, a tool result and an emulator
log as GitHub Actions artifacts even when the test fails. The tested NeXium
nightly is pinned to GitHub release asset ID `658656899` and SHA-256
`c933fbbcf8d1b011de8d4a79c9d8eb55c0678a305947af9388ddb40ce5960a66`,
observed on 20 October 2026. The mutable nightly tag can no longer silently
replace the binary: changing the asset requires an explicit reviewed hash
update. This does not independently establish source-build equivalence.

## Scope exclusions

This does not run an original PS1 CD, execute the real user-owned RU v1.6
binary, verify original US ELF/EXE identity, emulate actual PlayStation
DrawOTag/VRAM traffic, test historical MAP02 battle scripts, or demonstrate
physical Nintendo Switch hardware parity. It is not a merge acceptance for
private-source/retail work.

Run locally only in a suitable Linux/X11 environment with a legitimate
NeXium binary and the compiled asset-free NRO. The CI job is the
recommended repeatable proof; do not upload any owner-private BIN/CUE.
