# MAP02 — validate a local digest-only report without sharing the original disc

After the user runs the separate, local **MAP02 Private Disc Toolkit v2** on
their owned, private `Vandal_Hearts_(RU)_v1.6.bin` and matching single-track
`MODE2/2352` CUE, the toolkit emits exactly one owner-private JSON
`vh-map02-local-disc-digest-receipt.json`. It contains **hashes and counts
only**, never sectors, pixels, private paths, PS-X executable bytes or game
textures. Do not upload the BIN/CUE or private captures to public GitHub.

To inspect that JSON report in a checked-out copy of this repository:

```sh
chmod 600 "/private/map02/vh-map02-local-disc-digest-receipt.json"
python3 -m tools.check_map02_local_disc_receipt \
    "/private/map02/vh-map02-local-disc-digest-receipt.json"
```

The read-only validator requires a singly-linked owner-private regular JSON
file, rejects symlinks, duplicate/unknown/missing fields, invalid framing,
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
python3 -m unittest tests.test_check_map02_local_disc_receipt -v
```

The focused CI workflow runs the same tests without any original game
resources. A report produced in a later local session must still be inspected
as a new input and not treated as a signed independent attestation.
