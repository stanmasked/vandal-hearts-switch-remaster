# MAP02 — validate a local digest-only report without sharing the original disc

After the user runs the separate, local **MAP02 Private Disc Toolkit v2** on
their owned, private `Vandal_Hearts_(RU)_v1.6.bin` and matching single-track
`MODE2/2352` CUE, the toolkit emits exactly one owner-private JSON
`vh-map02-local-disc-digest-receipt.json`. It contains **hashes and counts
only**, never sectors, pixels, private paths, PS-X executable bytes or game
textures. Do not upload the BIN/CUE or private captures to public GitHub.

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
