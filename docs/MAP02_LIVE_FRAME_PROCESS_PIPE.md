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

## Independent offline replay and digest-only joining

For a captured private output directory (containing ONLY process-frame.bgr555
and process-frame.json, both mode 0600 under a 0700 private directory),
the new independent replay reads the exact bytes through no-follow file
descriptors anchored to the directory FD and hashes the pinned executable
again. It refuses extra files, noncanonical/duplicate-key JSON, incorrect
frames, malformed dimensions/length, digest drift, modified files, inode
replacement, insecure permissions, or unexpected provenance/HD flags.

    python3 -m tools.replay_map02_live_frame_receipt \
      --live-frame PRIVATE_OUTPUT --executable PRIVATE_NATIVE_ELF

To make a *limited* link between this live pipe receipt and an already
claimed BGR555 pair, use the new conservative join:

    python3 -m tools.join_map02_live_frame_native \
      --frame-pair PRIVATE_COMPARISON_DIR \
      --live-frame PRIVATE_OUTPUT \
      --native-capture PRIVATE_GPU_DIR \
      --source-capture PRIVATE_SOURCE_DIR \
      --launch-receipt PRIVATE_LAUNCH_JSON \
      --preflight-report PRIVATE_PREFLIGHT_JSON \
      --executable PRIVATE_NATIVE_ELF

This reruns all existing strict ELF/probe GPU/FT4/VRAM validators through
bridge_map02_private_frame_native; it requires exact frame number,
dimensions and **candidate image SHA-256** to match the independently
replayed live pipe, and replays that pipe AGAIN after the native audit.
All raw images and journals stay private. The resulting public JSON
contains only hashes, counts and deliberately false claims for same-process
causality, retail/original-disc authenticity, PS1 parity and HD activation.

**Crucial:** Even perfect matching digests do not prove the live pipe and
native GPU logs were generated by the **same process run**. Separate runs
may have identical data, and both manifests are local untrusted claims.
This workflow is an independent consistency gate only. The next required
gate is a single instrumented session that emits both the terminal native
frame and its source-verified GPU/FT4 ledger, with a fail-closed session
boundary and no reliance on a caller-authored process label.

## Joint native GPU journal + terminal BGR555 frame (experimental)

The next opt-in diagnostic combines BOTH observers in one exact source-pinned
GPU translation unit: tools/instrument_map02_joint_gpu_frame.py transforms
the original pinned libgpu.c into a separate libgpu.joint.c. The build requires
both -DVH_MAP02_PRIVATE_FRAME_PIPE_TRACE=1 and -DVH_MAP02_GPU_CAPTURE=1.
Compiling with only the frame flag is an error. Normal, uninstrumented
baseline object builds contain neither observer.

The combined hook runs at the same post-DrawOTag completion boundary as
the standalone frame hook. It refuses terminal output unless the native
GPU recorder selected this frame and completed at least one even-numbered
before/after pair WITHOUT reaching its 64-record hard cap. The
native GPU recorder writes its bounded event journal and VRAM snapshots
before this terminal hook emits its full 1024×512 BGR555 native VRAM.

**One-launch private usage:**

1. Build the generated PC GPU source in an isolated, private PC build
   along with tools/map02_native_frame_pipe.c, with both diagnostic flags.
   The ordinary PC port and Switch builds are not modified.
2. Create TWO distinct initially empty, owner-only (0700) private
   directories. One holds the stdout frame/receipt; the other receives
   private journal snapshots.
3. Use the SHA-pinned Linux ELF launcher with the exact full framebuffer
   size, selecting the requested DrawOTag frame:

       python3 -m tools.capture_map02_live_frame_pipe \
         --executable PRIVATE_ELF \
         --executable-sha256 EXPECTED_SHA256 \
         --output-dir PRIVATE_FRAME_DIR \
         --gpu-journal-dir PRIVATE_GPU_JOURNAL_DIR \
         --frame 123 --width 1024 --height 512

   The launcher passes the same selected frame to both capture variables
   and the journal directory through a minimal environment, starts ONE
   verified ELF, then checks the journal before publishing frame/receipt.
   All child output files are owner-private under a 0077 umask.

4. Independently replay the two inputs:

       python3 -m tools.replay_map02_live_frame_receipt \
         --live-frame PRIVATE_FRAME_DIR \
         --gpu-journal-dir PRIVATE_GPU_JOURNAL_DIR \
         --executable PRIVATE_ELF

The strict audit verifies the GPU primitive/transfer before/after event
metadata and 1-MiB VRAM snapshots, requires an uncapped journal with at
least one DrawOTag primitive, a final post-draw event, exact journal
inventory and **byte-for-byte equality** of its last post-draw native
VRAM snapshot with the binary stdout frame. Subsequent offline replay
requires the same journal hashes, image SHA-256, executable hash and
receipt flags. Output reports never include original private pixels or
file paths.

Synthetic C11 tests exercise genuine host ELF execution, one full
1024x512 native VRAM frame, C-written before/after journal snapshots,
mismatch and tampering refusals using both GCC and Clang. Separately,
the pinned-upstream CI compiles and relocatably links the combined
original GPU translation unit on both host compilers without game assets.

**Evidence boundary:** both artifacts are collected during a single
launcher invocation, improving the *operational* process-session linkage.
This is **not** a kernel-verifiable proof of which process wrote the
journal files (another process with access to the private directory could
intervene), nor does the source transcript authenticate the retail game,
original disc assets, PS1 raster parity or completeness of every CPU VRAM
write. It is specifically the **native PC renderer**, not PS1 hardware.
No private game was launched in CI. Preserve Draft and HD-off.
