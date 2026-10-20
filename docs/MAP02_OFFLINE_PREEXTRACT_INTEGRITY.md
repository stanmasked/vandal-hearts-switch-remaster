# MAP02 — authenticate the ZIP before extraction on Intel Mac

The portable public-only kit in Draft PR #366 already checks the SHA-256
manifest of all source files **after extraction, before diagnostic execution**.
This stage adds the other trust boundary: validate the *downloaded ZIP
itself* without extracting or executing any of its contents.

The standalone `tools/verify_and_extract_map02_offline_kit.py` uses **only
Python's standard library** and must be obtained from the inspected,
version-pinned GitHub source **separately from the ZIP**. It does not
import the packed scripts.

## Owner-local offline sequence

From a trusted copy of this standalone extractor and the downloaded
`vh-map02-intel-catalina-offline-kit.zip`, use the independently
published **inner ZIP SHA-256** from the exact Actions build that produced
the downloaded kit. Example for the *verified parent PR #366*
[Actions #39502258974](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39502258974):

```bash
python3 verify_and_extract_map02_offline_kit.py \
  vh-map02-intel-catalina-offline-kit.zip \
  033c035c211a4af4a17baf065e4f0bfbeedfaa679e418f84bb3e2684fc45eb47 \
  map02-verified-kit

cd map02-verified-kit
sh run-selfcheck.sh
```

The hash shown above is tied **only** to the public-only ZIP from that
particular GitHub run and commit `8a484735`. It is **not** the hash
of a later PR artifact or the outer GitHub Artifacts wrapper. For later
builds, use the latest corresponding `VH_MAP02_OFFLINE_KIT_INNER_ZIP_SHA256`
value shown in the trusted provenance job.

The output directory must not exist yet. The script refuses overwriting
any existing directory, to avoid touching other user files. It requires
Python 3.9+ and has no Git, curl, network, ROM, emulator or disc
dependencies.

## Checks performed before writing ANY extracted file

1. Verify the entire ZIP's SHA-256 against the explicitly supplied
   trusted 64-character checksum; reject symlinked inputs and archives
   outside fixed size bounds.
2. Inspect ZIP member metadata with no extraction or execution.
   Reject absolute paths, parent traversal, hidden/extra payloads,
   duplicate or case-colliding names, unexpected ZIP directory entries,
   symlink/special-file modes, unsupported compression, encryption,
   implausible decompressed sizes and non-UNIX modes.
3. Read all bounded ZIP member bytes in memory. ZIP extraction errors,
   CRC mismatches and mismatched file sizes stop verification.
4. Check the complete `files.json` allowlist and SHA-256 of **every**
   packaged file: Python source, C headers, public PC raster, README,
   `verify-kit.py` and `run-selfcheck.sh`. Validate the original
   public PC raster Git blob identity
   `ba8a05d161ad778c0b75e452ff0a11ed163c65cd`.
5. Only after those checks, create the new destination directory,
   write files with exclusive-create and no-follow semantics, and
   preserve intended regular-file permissions. Reject if destination
   exists; do not overwrite. The extracted `run-selfcheck.sh` performs
   its own **second integrity pass** on the resulting tree before
   importing any diagnostic code.

Failures produce a sanitized diagnostic with no private file contents.
There is no automatic network fetching or packaging of user-owned
BIN/CUE, private MAP02 VRAM, retail textures or screenshots.

## Independent tests

The Linux job checks eleven adversarial cases (wrong trusted checksum,
internally consistent but forged archive, extra executable, zip-slip,
duplicated entries, symlink mode, case-insensitive collision, symlink
input, existing destination, invalid digest string and a legitimate
positive extraction). The macOS 15 Intel Python 3.9 and 3.11 jobs
repeat the full actual offline selfcheck **from the newly verified
extraction**, including 49 synthetic test cases and three Catalina-
targeted C helpers.

## Limits

A checksum acquired *only from inside the same untrusted archive*
does not prove authenticity. The expected hash must come from an
**independent trusted provenance channel**, e.g. the named GitHub
Actions job. The separate extractor source itself must likewise be
obtained from a trusted reviewed revision. A verified ZIP proves
integrity relative to that trust anchor; it does not authenticate
retail PS1 MAP02 data or certify a successful run on the owner's
specific macOS 10.15.7 Intel Mac. Tests on GitHub macOS 15 are not
tests on Catalina. Nintendo Switch hardware execution is not
demonstrated.

Keep this work in Draft; no merges and no original assets uploaded.


## Local host acceptance receipt (optional)

After verifying and extracting the public-only kit, use the included
`python3 -B -m tools.map02_intel_mac_local_acceptance` to run the actual
49-test synthetic suite and the three C helpers again, producing a
sanitized operating-system compatibility receipt. The stricter
`--require-catalina-10-15-7` option refuses any host other than actual
Intel macOS 10.15.7 *before running the suite*. In particular, GitHub's
macOS 15 Intel runners may verify the general receipt but must **reject**
a Catalina-specific acceptance claim. Do not interpret mocked unit tests
that simulate a Catalina environment as a real runtime demonstration.
No private game material is used and the receipt is not a remotely
trusted hardware attestation. Do not place the receipt inside the extracted
kit, where it would be an unexpected extra file for `verify-kit.py`.
