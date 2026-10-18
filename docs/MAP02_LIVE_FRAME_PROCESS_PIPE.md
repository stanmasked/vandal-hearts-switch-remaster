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

## Hardened private journal replay (filesystem identity)

The native journal auditor now freezes **every** journal file through
a held, no-follow directory descriptor before the independent native
GPU replay. It requires single-link regular files with 0600 permissions,
bounded file sizes, and a 0700 owner-private directory, including a
correctly bounded 1 MiB VRAM image for each recorded snapshot. Each
filename is relative to the held descriptor, never a caller-selected
path outside the private directory.

After replaying the native event/VRAM operations twice, the auditor
independently rehashes ALL snapshots, the JSONL log and upload data
and compares both content digests and filesystem identities
(device, inode, size, modification/change timestamps) to those
observed before replay. It also verifies that the original directory
path still refers to the same held inode. A symlink, hardlink,
world-readable snapshot, replaced file with identical bytes or
changed directory path is a hard failure.

This tightens local integrity only: an external actor with control
of the same files can still race after the audit, and no kernel
evidence identifies which process emitted those bytes. It does
not authenticate a PS1 reference or enable HD asset substitution.

## Inherited journal directory descriptor (Linux)

The launcher now opens the empty journal directory once, before starting
the private ELF, and passes its held directory FD with `pass_fds`. The
actual native C recorder receives `VH_MAP02_GPU_CAPTURE_DIR` as
`/proc/self/fd/N`, **not** the mutable on-disk directory pathname.
Original GPU event writes therefore resolve through that inherited inode
even if a path is renamed or replaced while the game is running.

The launcher still refuses to publish a completed frame if the original
private directory path no longer names the held directory. Synthetic
C11 tests require the producer to receive the descriptor-based procfs
path and simulate a live pathname swap to a symlink. They verify that
all journal bytes stay in the pinned original directory and nothing
appears in the attacker-selected replacement destination.

This narrows pathname redirection risk; it is not proof that only one
process writes the files. Inherited descriptors may be passed on by
forked children, and same-user attackers could still obtain other
access to the directory. All claims of kernel-authenticated journal
writer and original PS1 rendering remain false.

## Exclusive native journal file publication (joint source-pinned build)

A diagnostic weakness remained inside the PC GPU observer itself: normal
`fopen(...,"wb")` would truncate an existing snapshot file, and reopening
the JSONL log in append mode for every GPU event would follow a substituted
log pathname. For the **combined** source-pinned GPU/frame observer only,
the transformed C unit now creates snapshot and upload files with
`open(O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC, 0600)` and converts
those descriptors into `FILE*` streams. Existing files and symlinks cannot
be overwritten by the private diagnostic recorder.

The JSONL log is also created **once**, exclusively, and its stream
descriptor stays open across all captured events; after each completed
JSON record the writer flushes the stream. The terminal frame hook now
requires the number of successfully flushed records to equal the
recorder's event counter. Failed or incomplete event writes must not be
mistaken for a complete captured stream even when the counter is even.
Ordinary PC-port builds and standalone GPU-only instrumentation retain
their original compile-time behavior.

The new native GCC/Clang publisher tests exercise actual owner-private
file creation, overwriting refusal, symlink and hardlink rejection, and
a live JSONL pathname replacement whose second event is still written
to the pinned original log inode rather than a substituted file. Source
transformer tests also reject missing or duplicated pinned write sites.

**Boundary:** These measures reduce file replacement and truncation
risks, but they do not authenticate a running game binary beyond the
existing pinned ELF checks or prove the private journal writer's kernel
identity. The test environment contains no actual game resources and
no PlayStation hardware raster evidence. Keep HD replacement disabled.

## Linux child journal-writer FD witness before frame release

In **joint** diagnostic mode, the one-shot native GPU recorder keeps its
JSONL `FILE*` open after flushing the last bounded event and before the
post-`DrawOTag` framebuffer gate. The independent SHA-pinned Linux
launcher now waits **before sending the single-byte release signal**,
checks the actual `/proc/PID/fd` entries for the launched child,
compares their device+inode to the held private GPU journal directory
entry, and reads `/proc/PID/fdinfo/N` to require a real write-capable
(`O_WRONLY` or `O_RDWR`) open file descriptor. It checks the still-live
child, then re-verifies the pinned `/proc/PID/exe` image and releases the
terminal stdout frame only when the fd witness is present.

The joint receipt carries
`child_writable_gpu_journal_fd_observed=true`. The independent offline
replay requires this exact flag alongside the existing executable hash,
GPU journal hashes, BGR555 payload hash, final native VRAM byte identity,
and deliberately false source/authenticity flags.

Tests execute a real synthesized Linux C11 ELF that writes two complete
VRAM event snapshots and a JSONL journal **before waiting for release**,
leaving its writable journal stream open. They also verify fail-closed
behavior when the journal is absent, the child closes the journal before
release, the only remaining journal descriptor is read-only, or a local
actor falsifies the receipt flag.

**Evidence boundary:** `/proc` confirms the pinned live child *held*
a writable descriptor to the journal inode at that moment. It does NOT
cryptographically prove that every byte was written by that process,
guarantee that nobody else wrote the file, prove any retail disc was
loaded, or authenticate original PlayStation GPU output. For this
reason `gpu_journal_writer_kernel_authenticated` remains **false**
in receipts and reports. The observer is Linux-specific and is not
compiled into normal Nintendo Switch gameplay. Preserve HD-off and
private local file handling.

### Hold journal inode identity across the terminal-frame gate

A further race was closed: merely observing a writable child journal
descriptor **before** release was not sufficient if another process
replaced `gpu-native-events.jsonl` with a different inode carrying
identical bytes **after** the gate was released. The Linux observer now
returns the actual device/inode tuple and the launcher verifies it
both before and after the private GPU/VRAM replay. A different inode
fails, even when every event and SHA-256 digest is unchanged; no
BGR555 image or receipt is published.

A synthetic C11 regression creates two correct native VRAM event
snapshots, flushes and holds the original journal open through the
gate, then deliberately swaps in a new same-byte JSONL inode before
writing the terminal frame. This must be rejected at the independent
held-inode boundary.

The bound is still to a journal **file inode**, not to every individual
write or the original game software. It cannot replace trusted PS1
capture evidence or enable HD replacement.

## One-shot GPU journal → independent private native bridge (digest join)

The former `tools/join_map02_live_frame_native.py` consumed only the
legacy two-file live BGR555 receipt, so it could not verify the newer
full-size same-launch GPU journal/terminal-frame receipt. The digest
join now accepts the optional private `--gpu-journal-dir` and replays
the **journal-aware receipt twice** across the independent FT4/VRAM
and frame-pair bridge. It requires exactly the journal-aware v2 schema,
a positive child writable-fd observation, exact BGR555 equality with
the final post-`DrawOTag` snapshot, and deliberately false claims of
kernel-certified log writer identity.

A full-size synthetic 1024×512 C11 ELF integration test exercises:
- actual Linux ELF child execution and a bounded GPU event journal;
- independent receipt and journal verification against the full frame;
- the real `compare_map02_private_bgr555_frames.compare` parser and
  pixel-by-pixel comparator for a private claimed pair;
- the real `bridge_map02_private_frame_native.bridge` implementation
  with only its original-source FT4/VRAM witness simulated;
- the actual `join_map02_live_frame_native.join`, verifying shared
  candidate BGR555 SHA-256 across separately replayed stages.

It rejects a changed candidate even when its claimant recomputes the
entire frame manifest, a missing joint GPU journal, a mutated journal,
and an upstream witness that claims unproven causal authenticity.
The combined public report contains digests and counts only; the
claim-labelled reference does NOT prove any original PS1 disc bytes,
and any separate original-source witness may be from another run.
Despite observing a writable journal FD, the pipeline does not
authenticate the process which wrote every journal byte, physical
PlayStation pixels, or permission to replace HD assets.

## Private claimed-frame inode continuity during source-native replay

The independent `bridge_map02_private_frame_native.bridge` formerly
compared the **same report** before and after the original FT4/VRAM audit.
A local same-byte replacement of `reference.bgr555`,
`candidate.bgr555` or `frames.json` could produce exactly the same
SHA-256 and pixel statistics on both passes while changing the files
used as the claimed evidence.

The private bridge now snapshots the identity of all three files and
the containing directory using an owner-held, no-follow directory FD.
Device, inode, mode, link count, size and modification/change times
must remain identical before comparison, after that comparison, and
after the source-native audit and second comparison. Symlink and
multi-linked candidate/reference/manifest files are refused. Only
internal snapshots hold these identifiers: **public digest reports
continue to exclude private inode and path information**.

Synthetic tests replace the candidate, reference, manifest and full
directory with byte-identical copies during the native witness,
as well as present a hardlinked image. All are refused. A full-size
C11 ELF → native GPU JSONL → terminal BGR555 → private comparison →
FT4/VRAM bridge integration test also deliberately swaps the claimed
candidate's inode without changing a pixel or manifest hash.

This prevents an undetected local file-identity change **during the
bounded audit window**, not changes after that window or forged PS1
source labels. Retail/gameplay authenticity and HD substitution
remain unproven and disabled respectively.

### Single-read pathname continuity for claimed BGR555 inputs

The standalone private frame comparator has also been strengthened.
After each `O_NOFOLLOW` image or JSON manifest read, it compares the
original held file descriptor's device/inode/size/time identity with
the **current pathname entry**. This rejects a same-byte replacement
that occurs during the read itself, before the source-native bridge
has an opportunity to take a second witness. Asset-free tests swap
each of the two image names and `frames.json` at the exact point of
an in-progress `os.read` and require a hard refusal. No file paths,
pixels or inode numbers appear in the final comparison report.

## One-command private MAP02 GPU capture with two complete replays

A practical local wrapper is now available as
`python3 -m tools.run_map02_private_joint_capture_audit`.
The user must supply their *own* previously prepared SHA-pinned Linux ELF,
two **existing empty** owner-private 0700 directories and the desired
source-native frame selector. The tool does not search for ROM/disc
files, obtain original assets, or commit private data.

Example (replace the paths and SHA with locally computed private values):

```sh
mkdir -m 700 /private/capture-frame /private/capture-gpu
python3 -m tools.run_map02_private_joint_capture_audit \
  --executable /private/pinned-map02-elf \
  --executable-sha256 YOUR_LOCAL_ELF_SHA256 \
  --frame 123 \
  --output-dir /private/capture-frame \
  --gpu-journal-dir /private/capture-gpu
```

The wrapper runs the pinned native ELF **once**, requesting its full
1024×512 little-endian BGR555 terminal frame and bounded before/after
GPU snapshots. It requires the observed writable journal descriptor
of the actual live Linux child, exact equality of the final native
post-draw VRAM and stdout bytes, and the deliberately unauthenticated
source/provenance flags.

After the child exits it performs **two independent full replays** of
the private BGR555 frame, JSON receipt, original ELF SHA-256, complete
GPU journal and the native GPU operation/snapshot validator. To detect
a byte-identical file swap *between* these replays, it also snapshots
the inode/mode/size/time identity of the two output files and every
journal file through owner-private no-follow directory descriptors
before and after each replay. File changes make the command fail.
Only SHA-256 digests, counts and explicit false provenance flags are
printed; no filenames, private paths, BGR555 pixels or inode numbers
appear in its success report.

The wrapper is an offline development aid, **not a runnable remade
level**, and it does not merge the independently captured PS1 source
FT4/VRAM witness by itself (that remains the optional private digest
join). It cannot prove the child wrote every GPU record, that the
private upstream PC port rendered the original disc resources, that
PS1 console pixels match, or that HD substitution is authorized.
It cannot detect every possible concurrent modification or an inode
replacement that occurred before the first post-capture audit; only
the strict live launch gate and within-audit checks address that
earlier window. HD replacement remains disabled.

### Publication-time inode binding (same-launch held descriptors)

A new `post_publish_witness` callback is available internally on the
private Linux ELF launcher. After successfully writing and `fsync`ing
the exact private BGR555 frame and receipt, and **before** the original
held frame and GPU-journal directory FDs are closed, the launcher calls
the callback with **those FDs**, never new path-derived replacements.
The one-command private runner uses them to pin both directory inodes
and all owner-private file identities in memory, then requires the
entire inventory to stay identical after the launcher returns, after
the first full native replay, and after the second replay.

This closes a same-byte file replacement window **between successful
capture publication and the first offline replay**. The callback is
optional for legacy launcher users, but is mandatory in the new
two-replay wrapper. A callback exception makes the launcher remove
the just-published BGR555 image and receipt, rather than accepting
an unwitnessed launch. Synthetic tests swap same-byte GPU journal,
frame and receipt inodes immediately after capture returns, omit the
callback, check that the callback receives real held directory FDs,
and force a callback error to verify image/receipt rollback.

The identity witness is only a local process-memory snapshot; it
cannot authenticate the executable's game resources or prove that
all GPU journal bytes were written by that child. No inode numbers,
directory paths, raw pixels or per-event data are emitted in the
public summary. HD substitution and original PS1 fidelity assertions
remain disabled.

## Optional private PS1-labelled reference image comparison

The one-command Linux capture wrapper now supports an **optional**
`--frame-pair-dir /private/claimed-frame-pair`. This must be a
locally held three-file directory containing `frames.json`,
`reference.bgr555`, and `candidate.bgr555` in the existing
`vh.map02.private-bgr555-frame-comparison.v1` schema; see
`docs/MAP02_PRIVATE_BGR555_FRAME_DIFF.md`. Both raw frames must be
1024×512 little-endian BGR555 with a matching selected frame number.
The original console/disc resources never need to enter GitHub.

With this option the tool uses the **real private comparator**,
checks the complete frame-pair device/inode/file metadata before and
after the one-shot ELF capture, and requires the claimed PC candidate's
SHA-256 to equal the actual stdout frame received from the pinned
Linux ELF. A modified reference is *not* itself a failure: the report
includes the aggregate differing-pixel count, exact matches, affected
scanlines, STP-bit difference count and the pixel-difference mask SHA.
The raw image bytes, coordinates, private paths and inode numbers stay
out of this report.

For example, append `--frame-pair-dir /private/claimed-frame-pair`
to the previously documented local capture command. The report field
`claimed_reference_ps1_hardware_authenticated` **always remains
false**. A self-labelled PS1 reference, even when bit-exact against
the current PC frame, is not trusted original hardware evidence; it
is simply a byte-by-byte claim comparison. Synthetic regression cases
exercise equal claimed pairs, one reference STP/color mismatch,
self-consistent fake candidate bytes, an identical-byte reference
inode swap while the child runs, mismatched frame labels and actual
CLI digest-only output. The original-source FT4/VRAM provenance audit
is still a distinct optional private input, not silently inferred.

### Private reference pair permissions and inventory preflight

The optional `--frame-pair-dir` is now refused **before running the ELF**
unless it names an owner-held directory without group/other access
(typically `0700`). It must contain **exactly** `frames.json`,
`reference.bgr555` and `candidate.bgr555`; all three must be
owner-owned regular files with mode `0600` and exactly one hard link
each. Symlinks, hardlinked aliases and extra files are not permitted.
The same preflight is run again after the frame/journal capture and
double replay, in addition to the already existing byte/hash/inode
checks.

This prevents accidental sharing of locally owned claim-labelled
game screenshots through common `0755` directories or `0644`
files. It does not claim the reference was captured from authentic
PlayStation hardware. Asset-free tests confirm that a shared directory,
world-readable claimed reference, symbolic/hard link, or extra file
fails before the ELF starts.

### Double-read owner and inode inventory at the publication/replay boundary

The private two-replay wrapper now requires **both** frame-output and GPU
journal directories to belong to the caller's effective Unix UID, in
addition to having no group/other access. Each original 0600 file must
also be owned by the same caller. The inventory walker checks every
entry's device, inode, UID, mode, link count, length, mtime and ctime
**twice through the same held directory FD** before returning its
private in-memory identity witness. A file that changes metadata during
the scan is rejected, even if its raw bytes remain unchanged.

The checks are repeated as before at successful frame publication,
immediately after the launcher returns and between/after the two
independent full native GPU + frame replays. All owner IDs and inode
numbers stay internal to the invoking process, never in the returned
JSON report. Asset-free Linux regressions simulate a directory with
an alien UID, a privately readable file attributed to another UID,
and a file whose timestamp changes between the two descriptor-relative
inventory scans. No retail image or original console capture is
authenticated by these checks.

## Optional full original-source FT4/VRAM witness join

The one-shot Linux joint GPU/BGR555 capture wrapper now optionally
accepts all four *private*, pre-existing original-source/native
inputs, in addition to `--frame-pair-dir`:

```sh
  --frame-pair-dir /private/claimed-pair \
  --native-capture /private/native-gpu-evidence \
  --source-capture /private/source-ft4-evidence \
  --launch-receipt /private/launch-receipt.json \
  --preflight-report /private/native-preflight.json \
  --compiler gcc
```

Use these options with the main command from the previous section
rather than as a separate command. `--compiler` may also be
`clang`. **All four witness paths and the claimed reference pair
are required together**: any partial combination is refused before
launching the ELF or publishing a frame.

With this option, the wrapper first performs its usual one-shot
SHA-pinned Linux ELF BGR555 stdout + same-launch GPU-journal capture,
owner/identity pinning, and two complete private replay passes.
It then invokes the independently implemented
`join_map02_live_frame_native.join`, which does *another two*
private GPU+frame replays and a strict FT4/GTE/native VRAM
validation using the original private launcher/receipt source
evidence. It verifies frame number, 1024×512 dimensions,
the candidate BGR555 hash, claimed reference hash and terminal
native VRAM/journal SHA/count against the initial one-shot
capture, and finally checks the original held directory-FD
file identities and claimed reference bytes are still unchanged.
A forged, self-signed or mismatched source witness is refused.

When the complete optional chain succeeds, the digest-only report
adds `source_keyed_native_ft4_vram_independently_replayed=true`,
the checked original-launch receipt and source GPU event digests,
and explicitly
`source_original_trace_same_session_as_live_elf_authenticated=false`.
These are **separately recorded capture sessions**; the join
does not establish kernel-attested process causality, authenticate
the retail PS1 resources, or prove that PS1 hardware pixels
match the PC BGR555 output. No private pixel bytes, source paths,
inode IDs, or original disc materials are published. HD substitution
stays disabled.

Synthetic Linux C11 regressions cover correct complete source
joining (mocking only the unavailable original FT4/VRAM witness),
wrong native frame, falsely positive provenance, same-byte
reference inode substitution during the independent source replay,
incomplete witness arguments and invalid compiler selection.

### Sanitized private capture command diagnostics

The one-shot local capture CLI now routes expected filesystem errors,
timeout exceptions, and internal validation failures through a bounded
failure-category formatter. A missing private ELF, absent source
reference, or error message from an untrusted witness will no longer
cause the CLI to echo the original absolute filenames in its stderr.
Recognized error categories such as SHA-256 mismatch and incomplete
original-witness arguments are preserved without embedding caller
paths; other errors use a generic validation-failed category.

Three asset-free regressions check missing ELF/reference paths and
deliberately path-bearing arbitrary exception messages. This affects
the command's displayed **error** text, not its validation behavior or
the existing digest-only successful report. The CLI command line
supplied by the user may still be visible through the local shell
history/process listing; this tool does not promise secrecy from
local administrators or other privileged processes.

### Untrusted original-witness digest field validation

When the full optional original FT4/VRAM native source replay is used,
its result is required to be a structured dictionary with all the
existing provenance flags and verified live-frame correlations. The
two independent source digest fields that appear in the public success
summary (original-launch receipt SHA-256 and original native GPU event
log SHA-256) must additionally be **exactly 64 lowercase hexadecimal
characters**. Missing, non-string, uppercase, malformed, or
path-bearing fields fail validation instead of being copied to a
public JSON success report.

The CLI still uses only bounded, path-free error categories. Three
asset-free regression cases cover forged full-chain source digests
(including an attempted private-path string), malformed source-join
result types and the digest-only publication helper itself. These
checks do not authenticate the original disc/console evidence or
establish that independently acquired source traces were recorded by
the same Linux child.
