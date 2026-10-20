# MAP02 — reproducible, asset-free Intel Mac offline diagnostic ZIP

This adds a portable **developer self-check kit**, not the Vandal Hearts
game, remake artwork, any retail PS1 data or a console build.

The previous child Draft PR #359 passed native Intel macOS 15 Python
3.9/3.11 checks for three actual pinned-PC `SampleTexture` helper
binaries, all built with an x86_64 macOS 10.15 minimum. This step makes
those verified tests independently usable on the owner's Intel Mac
**without GitHub connectivity or a mounted PS1 drive**.

## Build (public source only)

With the project checked out and the exact public PC-port
`platform/pc/src/pc_raster.c` already downloaded from the pinned
revision `14552fffa0e0b47e02b57592e274fc6e7a649923`:

```bash
python3 -m tools.build_map02_intel_mac_offline_kit \
  /path/to/public/pc_raster.c \
  /tmp/vh-map02-intel-catalina-offline-kit.zip
```

The builder validates the Git **blob SHA-1** of the public PC raster:
`ba8a05d161ad778c0b75e452ff0a11ed163c65cd`. It follows checked-in
Python imports and local C `#include` paths starting from the owner-local
selfcheck, the pinned helper Mach-O auditor, the genuine private-format
source/native FT4 CLI and the exact synthetic test fixtures. The archive
has a strict `tools/*.py`, `tests/*.py`,
`tests/test_map02_vram4_frame.c`, `source/*.h` allowlist. The single
pinned public raster is the only external source file.

No `.git`, private disk catalog, original MAP02 media, BIN/CUE/ROM,
PS1 executable, VRAM captures, private file metadata, screenshots, game
art, or other binary resources are added. Paths are normalized and
bounded; unknown suffixes, symlinks, traversal and overwritten output
fail closed. Source bytes are checked for embedded binary NULs. Archive
entries have stable sorting, timestamp and permissions, ensuring two
builds from identical inputs yield identical ZIP bytes.

The `files.json` file stores per-file SHA-256 hashes, the pinned public
source Git blob identity and explicit false provenance flags. The
builder emits only an aggregate JSON report with total member count and
the ZIP's SHA-256, not source contents or private paths.

## Use after unzipping on the owner's Intel Mac

With Python 3.9+, Xcode command-line Clang and `otool`/`lipo`
available, navigate to the extracted kit directory and run:

```bash
sh run-selfcheck.sh
```

The script uses only files inside its extracted directory; it makes no
network calls and requires no private disk. It performs:

- 49 synthetic source/GTE/VRAM and native FT4 tests, including ten
  actual command-line acceptance/refusal tests;
- a C11 three-face OT/CLUT frame test and Mach-O minimum-macOS 10.15
  check; and
- a separate audit of all **three genuine pinned-PC source C helper
  programs**, with system-library-only dependency requirements,
  2,097,152 page samples, 196,608 per-FT4 samples, and refusal to
  pretend that an absent private snapshot is real evidence.

No original PS1 inputs are authenticated in this kit.

## Independent CI

The dedicated workflow has three jobs: Linux deterministic ZIP and
clean-room CLI test; extracted-archive execution on Intel macOS 15 with
Python 3.9; the same on Intel macOS 15 with Python 3.11. The ZIP artifact
uploaded by the workflow contains **public code and synthetic
diagnostics only** and has a limited retention period.

A successful extracted-kit run on macOS **15** and a Mach-O 10.15
minimum deployment target **do not prove operation on macOS Catalina
10.15.7** or on the owner's physical Intel Mac. Actual original
PS1 game capture, source provenance and retail Vandal Hearts MAP02
graphics parity remain wholly untested.

Keep Draft. Do not merge into `main` or publish licensed/private
game data.
