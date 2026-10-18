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

## Native C11 framebuffer producer (new)

The repository now includes tools/map02_native_frame_pipe.h and
tools/map02_native_frame_pipe.c. It can serialize a **completed in-memory**
BGR555 pixel array in exactly the Linux ELF pipe protocol above, including
explicit little-endian 16-bit words. Rows may have a larger native source
stride than the requested output width (for example, a 1024-word PS1-style
VRAM buffer with a smaller crop); padding pixels are not transmitted.
The helper validates frame, width, height, pointer, stride, output descriptor
and total byte count before writing its header. It uses bounded stack storage,
does not allocate, and retries interrupted writes.

For any hypothetical native renderer integration, first wait on
vh_map02_frame_pipe_wait_release(input_fd) and **only after the requested
frame is completed** call vh_map02_frame_pipe_emit(output_fd, frame,
width, height, completed_pixels, stride_pixels). The caller is solely
responsible for ensuring the pointer refers to the actual finished framebuffer
and that its width * stride storage is valid. This helper does not instrument
or alter the upstream GPU rasterizer automatically.

The C11 implementation deliberately rejects builds without
-DVH_MAP02_PRIVATE_FRAME_PIPE_TRACE=1 and rejects non-Linux platforms.
It must not be linked into regular Switch/retail binaries. This is
a *debug-only transport*, not evidence of a genuine GPU flush or proof that
the requested image originated from the game. Neither the producer nor the
launcher authenticates loaded disc resources or original PS1 pixel output.

Additional asset-free end-to-end regression, through a compiled native
ELF using a two-row pitched synthetic framebuffer:

    CC=gcc python3 -m unittest discover -s tests \
      -p 'test_map02_native_frame_pipe_c11.py' -v

The same test is run with CC=clang in the dedicated GitHub Actions matrix.
It checks exact BGR555 ordering, stride/padding exclusion, gating, strict
parameter refusal, invalid frame/header rejection and disabled-build errors.

**Outstanding:** add a source-pinned renderer call site at a proven
framebuffer-flush boundary, then connect that *same launch session* to
native GPU/FT4/VRAM journals. Until then, the frame stream and the previous
log replay have no proven pixel-generation causality and HD remains off.

## Original pinned PC-GPU DrawOTag integration — opt-in experiment

tools/instrument_map02_frame_flush.py now requires the *exact* original
Git blob of platform/pc/src/libgpu.c in pinned upstream revision
14552fffa0e0b47e02b57592e274fc6e7a649923. It produces a separate
source file by exclusive creation and refuses modified inputs, repeated
instrumentation, a missing DrawOTag completion marker or changed
presentation order. It never edits the upstream checkout.

The one-shot hook is inserted immediately after PC_MaybeDumpVram(), after
TrcFrameEnd() and the optional HiresRasterizeThreaded() call, but before
native VRAM/hires presentation. It reads **native 1024 x 512 PC GPU VRAM**
from PC_GpuVram(), *not* the deferred hires output and not a PS1
console's video signal. All VRAM bytes include textures and potentially
other private game content, so the destination must remain private.

The strict Python launcher now supplies the selected requested frame
as VH_MAP02_PRIVATE_FRAME_PIPE_FRAME. A diagnostics-enabled native
libgpu.c waits until s_drawFrame reaches that positive value, flushes
its C stdio journals, consumes the one-byte release signal, streams
the entire native 1024x512 BGR555 VRAM to stdout using the native C
pipe helper, and then immediately exits by _exit(0) so no later
game output can corrupt this one-shot stream. This intentionally
**terminates gameplay at the target frame** and is inappropriate for
normal game or Switch builds. An unselected frame or a build without
the compile flag does not emit this stream.

Example transformation (does not launch any game or copy resources):

    python3 -m tools.instrument_map02_frame_flush \
      PRIVATE_PINNED_CHECKOUT/platform/pc/src/libgpu.c \
      --output PRIVATE_NEW_DIR/libgpu.frame.c

Compile that generated source **only in an isolated private host build**
with -DVH_MAP02_PRIVATE_FRAME_PIPE_TRACE=1 and link with
tools/map02_native_frame_pipe.c and its header. The pinned GPU CI
checks compilation and relocatable linking on GCC and Clang in
diagnostic and baseline modes; synthetic C11 tests separately
exercise the pipe. The private launcher must request width 1024
and height 512 for this hook.

A successful CI compile means only that the hook is source-pinned and
buildable. Public CI has no original game assets and does not execute
retail gameplay; a full private game build/link, successful frame capture,
proof of loaded original-disc resources, and a same-session GPU/FT4/VRAM
journal join remain outstanding. Existing independent frame-pair
comparisons must **not** be promoted to game rendering evidence.
