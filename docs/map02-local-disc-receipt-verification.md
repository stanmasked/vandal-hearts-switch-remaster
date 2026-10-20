# MAP02 — validate a local digest-only report without sharing the original disc

After the user runs the separate, local **MAP02 Private Disc Toolkit v2** on
their owned, private `Vandal_Hearts_(RU)_v1.6.bin` and matching single-track
`MODE2/2352` CUE, the toolkit emits exactly one owner-private JSON
`vh-map02-local-disc-digest-receipt.json`. It contains **hashes and counts
only**, never sectors, pixels, private paths, PS-X executable bytes or game
textures. Do not upload the BIN/CUE or private captures to public GitHub.

## One-command private handoff on Mac (recommended)

When the **complete owned RU v1.6 BIN and CUE** are visible as mounted
ordinary files in Google Drive for desktop, open Terminal inside your
local checkout of this repository and create a **new local-only parent**.
Do **not** put this output in Google Drive, iCloud, Dropbox, or
`~/Library/CloudStorage`.

```sh
mkdir -m 700 "$HOME/vh-private"
BIN="/path/to/mounted/GoogleDrive/Vandal_Hearts_(RU)_v1.6.bin"
CUE="/path/to/mounted/GoogleDrive/Vandal_Hearts_(RU)_v1.6.cue"

python3 -m tools.run_map02_private_disc_audit "$BIN" \
  --cue "$CUE" \
  --private-parent "$HOME/vh-private"
```

The command invokes the **already tested** secured staging,
full-byte SHA-256 copy/readback, 2352-byte CD-XA Form 1 boot and MAP02 sector
EDC checks, pinned compressed PRS SHA-256, receipt-schema validation,
atomic owner-private JSON publication and final readback.
It refuses to overwrite an existing local stage directory.
It prints **only** a success marker and the JSON basename, not original
game sectors or local source paths.

On success the only report to consider sharing privately is:

`$HOME/vh-private/vh-map02-private/receipt/vh-map02-local-disc-digest-receipt.json`

The local 665-MB BIN and CUE remain `0600` in the private
`0700` directory and **must not be committed or uploaded to GitHub**.
A JSON report itself is self-reported evidence of local checks, **not**
proof of exact original-US executable identity or a true PlayStation
DrawOTag/VRAM framebuffer. If CD-XA/PRS checks fail, **no receipt is
published**; the private local staged copy remains for deliberate
investigation, and a later attempt must use a fresh local staging parent.
Do not modify source Drive permissions or delete the original disc.

The dedicated asset-free CI for this one-command orchestration mocks only
the unavailable original-CD inspection. It does **not** claim that synthetic
input has passed real retail sector checks; those checks retain their
separate independent CI tests.

## Safe Mac staging from a mounted Google Drive (no changes to Drive originals)

If the original BIN/CUE are available through a mounted Drive volume and
cannot or should not be `chmod 0600`, first make a private **local copy**
without touching the cloud files. The optional stage tool checks the pinned
filenames, source CUE, 664,849,248-byte layout, source stability and local
`0700` destination; then streams both files to owner-only `0600` copies.
Before the first image byte is copied, the tool checks free space on
the pinned private destination volume via `fstatvfs` and requires enough
room for the **whole 664,849,248-byte BIN plus a 128-MiB reserve**. The
check fails closed on invalid/inaccessible filesystem capacity. It is
not a disk reservation: other processes can still consume space. Keep
**at least 1 GiB free** as a practical margin on the local Mac volume.

It re-opens and independently SHA-256 hashes the copied BIN from its
private destination, and byte-compares the staged CUE with the source CUE,
**before** publishing the folder. A mismatch, truncation or changed inode
causes cleanup; the observed source and staged-image hashes must match.
It publishes the complete copy folder only after copying and syncing the
files, using an **atomic no-replace directory rename**: macOS
`renameatx_np(RENAME_EXCL)` or Linux `renameat2(RENAME_NOREPLACE)`.
This prevents a second process from creating an empty destination between
the preflight check and publication; an existing directory or symlink is
never overwritten. Unsupported filesystems fail closed without falling back
to `os.rename`. An incomplete temporary folder is removed if copying or
publication fails. Allow at least 1 GiB free locally.

### Full-size synthetic validation, without your original disc

The additional `tests/test_stage_map02_fullsize_synthetic.py` constructs a
**sparse fake** 664,849,248-byte file. It contains only zero-filled space
and three literal `SYNTHETIC_TEST_BYTES_ONLY_NOT_A_GAME_DISC` markers.
It then streams the **entire** fake image through the protected staging
logic, independently compares source and local-copy SHA-256 digests, checks
the first/MAP02-offset/end markers, and confirms the 0600/0700 permissions.

Dedicated `map02-fullsize-synthetic-disc-staging.yml` jobs run the test
on Linux and macOS Intel without downloading, publishing or inspecting the
user's BIN/CUE. This checks full-length I/O behavior and filesystem space,
not CD-XA payload authenticity, ownership of the retail image or real
gameplay/VRAM rendering.

The following is for **when the Drive files are mounted on your Mac**;
replace the two source placeholders with actual, existing filesystem paths.

```sh
# A new, local-only destination (not inside the synced Google Drive):
mkdir -m 700 "$HOME/vh-private"
BIN="/path/to/mounted/GoogleDrive/Vandal_Hearts_(RU)_v1.6.bin"
CUE="/path/to/mounted/GoogleDrive/Vandal_Hearts_(RU)_v1.6.cue"

python3 -m tools.stage_map02_private_disc "$BIN" \
  --cue "$CUE" \
  --private-parent "$HOME/vh-private"

# Now run the original-sector verification on the private local copies:
LOCAL="$HOME/vh-private/vh-map02-private"
python3 -m tools.emit_map02_local_disc_receipt \
  "$LOCAL/Vandal_Hearts_(RU)_v1.6.bin" \
  --cue "$LOCAL/Vandal_Hearts_(RU)_v1.6.cue" \
  --output-private-dir "$LOCAL/receipt"
```

**Guardrail:** The staging tool refuses a destination inside the mounted
source BIN/CUE directory and inside the standard macOS
`~/Library/CloudStorage` File Provider sync tree (including Google Drive).
Choose a truly local private directory such as `$HOME/vh-private`, **not**
another folder synced to Google Drive, iCloud or Dropbox. The guard does not
discover every third-party sync configuration; verify the output location is
not being backed up or synchronized before running the tool.

The stage command does **not** emit game bytes, upload files, make the original
Drive files public or change their permissions. Only `$LOCAL/receipt`
contains the generated digest-only JSON; keep both it and the 665-MB local
staged copy off public GitHub. This is a source-copy and checksum readiness
step, not a gameplay/VRAM capture or a claim that the RU executable equals
the exact required US retail build.

The repository now also provides a self-contained **private producer**
(`tools/emit_map02_local_disc_receipt.py`) which can replace the original
standalone Toolkit v2 receipt generator. On the computer that already holds
the **complete** owned BIN and CUE, first create an empty private directory:

```sh
chmod 600 "/private/owned/Vandal_Hearts_(RU)_v1.6.bin"
chmod 600 "/private/owned/Vandal_Hearts_(RU)_v1.6.cue"
mkdir -m 700 "/private/map02/receipt"
python3 -m tools.emit_map02_local_disc_receipt \
  "/private/owned/Vandal_Hearts_(RU)_v1.6.bin" \
  --cue "/private/owned/Vandal_Hearts_(RU)_v1.6.cue" \
  --output-private-dir "/private/map02/receipt"
```

The producer reads the local BIN only through owner-private `0600`
file descriptors, hashes its full 664,849,248 bytes, checks the pinned
US-layout boot sector plus 12 `M_MAP02.PRS` sectors (including Form 1
CD-XA EDC), verifies the prior RU v1.6 compressed PRS SHA-256 and
writes and fsyncs an owner-only temporary JSON in a pinned `0700` directory,
then atomically creates the final receipt name using an exclusive same-directory
hard link. Only a **complete** JSON is visible at the final name; a link,
fsync, or directory-identity failure removes the publisher's own files
without touching unrelated files. The filesystem must support same-directory
hard links and directory fsync; there is no unsafe fallback. It then runs
the separate receipt validator before reporting success. The source
sector bytes, source filename and local paths are not included in the
JSON. A private read/write on this user's computer is required; public
CI has no original disc. Keep all original images and frame captures out
of GitHub and CI artifacts.

To inspect that JSON report in a checked-out copy of this repository:

```sh
chmod 600 "/private/map02/vh-map02-local-disc-digest-receipt.json"
python3 -m tools.check_map02_local_disc_receipt \
    "/private/map02/vh-map02-local-disc-digest-receipt.json"
```

The read-only validator requires a singly-linked owner-private regular JSON
file (mode `0600`) inside an owner-only `0700` directory; it opens the file
relative to a held, no-follow directory descriptor and checks directory identity
again before returning. It rejects symlinks, duplicate/unknown/missing fields, invalid framing,
incorrect scalar types and false retail/PS1/gameplay claims. It checks the
previously audited **RU v1.6** size (664,849,248 bytes / 282,674 raw sectors),
12 source-pinned MAP02 PRS sectors at LBA 0x1BCC, 13 reported Mode 2 Form 1
EDC sector checks (12 PRS + US-layout boot), and the prior verified PRS
content digest. The whole-disc SHA-256 must be a lowercase 64-digit hex
string; it is reported unchanged, not verified against physical image bytes.

**Limits:** A structurally valid **self-reported receipt** is not authenticated
original-disc evidence. This module does **not** read the actual BIN, recompute
its hashes or prove the claimed CD-XA checks occurred. It does not prove
the translated RU v1.6 executable matches the byte-exact US build-generator
requirement or that the original PC GPU produced a real MAP02 frame. Keep the
private original-PC executable MD5 gate, real-session/GTE/OT/VRAM checks and
HD/PS1 parity requirements intact.

Asset-free synthetic tests:

```sh
python3 -m unittest -v tests.test_check_map02_local_disc_receipt tests.test_emit_map02_local_disc_receipt
```

The focused CI workflow runs the same tests without any original game
resources. A report produced in a later local session must still be inspected
as a new input and not treated as a signed independent attestation.
