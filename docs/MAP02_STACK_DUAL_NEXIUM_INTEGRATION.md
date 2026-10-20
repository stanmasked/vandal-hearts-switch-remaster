# MAP02 — unified stacked tactical NRO and two genuine NeXium replays

This is a **Draft, no-merge** integration test stacked on the already green
read-only eleven-PR integration preflight (#302). It contains no original PS1
retail sector contents. It adds the exact tested guard-boundary Python route
from Draft #306 (same Git blob), its three screenshot-forgery negative cases,
and a new dual-replay workflow.

## One build, two runtime acceptance scenarios

The workflow checks out one commit, compiles the combined native tactical C
test, runs host rules and sanitizers, and builds **one** devkitPro/libnx
`vandal-hearts-prototype.nro`. That identical Actions artifact is consumed by
the following two independently restarted NeXium sessions on an Xvfb Linux
runner:

1. Previously proven READY → ARMED → expired and ARMED → BLOCKED guard status
   with an actual mitigated enemy hit. The existing guard-HUD Python driver
   must emit `VH_MAP02_NEXIUM_GUARD_HUD_PASS` after comparing genuine PNG frames.
2. Previously proven guard reset on L scene changes, R roster switches
   (4v4/3v3/1v4/4v4), L+R exit/reentry, exact restored legacy board and
   an actual unprotected enemy phase. The unchanged approved boundary driver
   must emit `VH_MAP02_NEXIUM_GUARD_BOUNDARY_PASS` from authentic PNGs.

Both have strict *full-line* success markers. Partial operation, an empty
emulator window, wrong controller mapping, missing PNGs, an altered board, or
an inherited shield after reentry fail the job. In particular, successful
synthetic oracle unit tests alone **never** count as a real NeXium pass.

The NeXium Linux archive is pinned to GitHub release asset ID `658656899`
and SHA-256 `c933fbbcf8d1b011de8d4a79c9d8eb55c0678a305947af9388ddb40ce5960a66`;
a checksum mismatch blocks both guest runs. The CI retains the identical
NRO artifact, both separate genuine screenshot directories and execution
logs, including on failure. Independent compilation and emulation protects
against accidentally relying on an older child's NRO or mixing unrelated
earlier screenshots into the latest-HEAD result.

## Read-only chain integrity

The inherited `map02-stack-integration.yml` must run at the same HEAD and
reconfirm all 11 pinned staged PRs, one examined diverged history edge,
source/fixture integrity, absence of added licensed retail assets, simulated
`git merge-tree` safety and combined GCC/Clang/UBSan battle tests. The
additional paths trigger it if either new script/workflow is changed.

## Not yet established

Even two successful guest playbacks and the simulated integration audit are
**not** a literal integration of all branches into `main`, a certified
retail PS1 MAP02 restoration, source-owned disc identity, pixel-perfect
DrawOTag/VRAM rendering, genuine retail soundtrack or physical Nintendo
Switch hardware validation. No proprietary game data is uploaded, no PR
is merged, and no user action on private discs is requested.
