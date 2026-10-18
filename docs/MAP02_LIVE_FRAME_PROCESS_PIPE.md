# MAP02 — experimental live ELF-to-frame pipe

The existing private BGR555 two-frame/native journal bridge proves replay
consistency, not which process originated the supplied pixels. The optional
tools/capture_map02_live_frame_pipe.py adds a narrower experiment: it
launches one SHA-256-pinned Linux ELF, checks the running kernel
/proc/<pid>/exe image before releasing it, and reads one exact BGR555 frame
from the launcher's bounded stdout pipe rather than trusting a pre-existing
frame file.

## Producer protocol

The native producer must:

1. Block reading one byte from stdin until it receives 0x01.
2. Write only a 20-byte little-endian header on stdout:
   struct.pack("<8sIII", b"VHM2FRM1", frame, width, height).
3. Write exactly width * height * 2 bytes of little-endian BGR555 pixels.
4. Close stdout and exit with status zero.

The frame, width and height must match the caller's selection. The output
limit is 2 MiB, with each dimension between 1 and 1024. Missing/extra
bytes, wrong header, a nonzero exit, timeout or unverified /proc executable
cause hard failure before publication. No shell or inherited loader
override is used.

The caller creates an initially empty owner-only private directory (0700)
outside public CI artifacts. Example for an instrumented native producer
that implements the above protocol:

    mkdir -m 700 PRIVATE_OUTPUT
    python3 -m tools.capture_map02_live_frame_pipe \
      --executable PRIVATE_NATIVE_ELF \
      --executable-sha256 EXPECTED_64_CHAR_HEX_SHA256 \
      --output-dir PRIVATE_OUTPUT \
      --frame 123 --width 320 --height 240

Two files are created exclusively with permission 0600 relative to a
held directory FD: process-frame.bgr555 and process-frame.json.
The JSON report includes only dimensions, SHA-256 digests and narrow
observation flags; it never copies private pixels, process arguments,
executable paths or raw GPU trace data.

## Exact limits of this evidence

- A successful capture demonstrates that a held, SHA-matched Linux ELF
  was observed alive at launch and a complete binary payload arrived through
  its stdout channel. File descriptors may be inherited by subprocesses;
  this is not a cryptographic proof of which instruction wrote each byte.
- It does not authenticate Vandal Hearts, original-disc resources, a
  specific raster callback, source FT4/VRAM correlation, PlayStation video,
  pixel accuracy or permission for HD replacement.
- The local receipt is not signed by an independent trusted observer;
  its JSON alone cannot authenticate historic process causality.
- The tool does not alter the existing frame-pair/native join. It remains
  separate until a genuine GPU-flush hook provides the frame and a trusted
  end-to-end chain connects that output to the native journals.
- Private ELF/game capture is not run in public CI. Only a synthetic C11
  producer is compiled and executed under GCC and Clang.

Local test:

    CC=gcc python3 -m unittest discover -s tests \
      -p 'test_capture_map02_live_frame_pipe.py' -v

Use CC=clang for the second compiler. Keep the PR in Draft, HD replacement
disabled and private game resources outside the public repository.
