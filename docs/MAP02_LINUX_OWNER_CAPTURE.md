# MAP02 owner-local capture on Linux x86_64 (Stage520)

> **Stage547 update (2026-10-24):** The official BizHawk 2.11 Linux
> archive still omits the native Octoshock module. In contrast, our pinned
> Linux CI has successfully **built a native Octoshock port independently**
> and staged a real no-game-media BizHawk/Octoshock runtime (413 files;
> most recent exact-head tar roundtrip 139,113,480 unpacked bytes).
> This runtime existed **only inside a temporary CI runner**. It was not
> permanently archived to the owner's private Google Drive, no independently
> trusted owner manifest pin has been established, and no genuine MAP02
> PS1 cold boot has been proven. The historical Stage520 warnings below
> concern the **upstream official package**, not the newer standalone
> compatibility build. Do not infer that the owner-host capture gate is open.
>

## Current blocking finding — do NOT start a real PSX capture yet

On the official, SHA-256-verified BizHawk 2.11 Linux x64 release,
`liboctoshock.dll.so` / `liboctoshock.so` / `octoshock.dll` are absent.
The game's BK2 was recorded with Octoshock; Nymashock cannot be silently
substituted. The Linux capture workflow intentionally fails the terminal
Octoshock availability gate even when a game-free managed assembly compiles.
This matches upstream [BizHawk issue #2423](https://github.com/TASEmulators/BizHawk/issues/2423),
whose Linux core checklist leaves Octoshock unchecked. A verified compatible
Linux Octoshock native build is a prerequisite before following the owner
capture commands below. No current Linux runtime is authenticated for MAP02.


## Why this path exists

The current BizHawk 2.11 EmuHawk build does not support current macOS. The supported no-Windows route is the official Linux x86_64 release running in a Linux x86_64 environment (a private VM on an Intel Mac is acceptable). Do not try to run the Linux package directly on macOS or substitute Wine.

Stage520 adds a Linux-specific path without weakening the existing Windows checks:
- launch the official `EmuHawk.exe` through an explicitly supplied Mono executable, without a shell;
- use `/proc/PID/stat` start-time evidence and the same integer UTC-tick conversion in Python and the C# External Tool;
- inspect the actually mapped Octoshock shared object in `/proc/self/maps`;
- check POSIX ownership and owner-only output directory permissions;
- preserve the original-media/BK2 private preflight, full-BIN hash checkpoint, screenshot chain audit and fail-closed module pins.

The Linux path is not considered usable until the Linux build workflow has passed for the exact PR head and emitted its verified artifact and hashes. It uses fictional media in CI; no private game data is uploaded.

## Verified upstream runtime

The official BizHawk 2.11 Linux x64 release archive is:

- Asset: `BizHawk-2.11-linux-x64.tar.gz`
- Official release URL: `https://github.com/TASEmulators/BizHawk/releases/download/2.11/BizHawk-2.11-linux-x64.tar.gz`
- SHA-256: `cdaf9650d880bae660d63a388430f630b8d8a96b1ba59ebf0e0195a645c3bab8`

The Linux workflow downloads that exact archive, verifies this digest, and checks the managed assembly. Its native Octoshock inventory is currently empty. It may compile the game-free External Tool as a compatibility probe, but the final PSX gate remains blocked until the correct native module can be independently built and authenticated.

Install the documented Linux dependencies from the distribution package manager: Mono complete, OpenAL, Lua 5.4, `lsb_release`, and the host's X11/OpenGL dependencies. Keep this release in its own directory; do not mix files from another BizHawk version.

## Artifact and module pins

From one successful **MAP02 real BizHawk 2.11 Linux External Tool compile (no game media)** run, use only these three values from that same run:

- `VH_MAP02_LINUX_EXPERIMENTAL_DLL_SHA256`
- `VH_BIZHAWK211_LINUX_CORE_ASSEMBLY_SHA256`
- `VH_BIZHAWK211_LINUX_NATIVE_OCTOSHOCK_SHA256`

Download `vh-map02-bizhawk211-linux-experimental-core-witness` from that exact run and verify the DLL's SHA-256 against its marker. Do not reuse the Windows DLL digest or Windows module hashes. If the artifact and hash markers come from different runs, stop.

Install the plugin without overwriting any existing file:

```bash
python3 -m tools.map02_owner_core_witness_install_linux \
  "$BIZHAWK_ROOT" "$DOWNLOADED_DLL" \
  --expected-plugin-sha256 "$KNOWN_LINUX_DLL_SHA256"
```

The installer verifies the official Linux package layout, source digest and destination; it refuses symlinks, Git checkouts, malformed hashes and an existing destination. The installed DLL is owner-only (mode 0600).

## First local launch — one capture only

Keep the original CUE/BIN, BK2, BIOS, hash reference, capture workspace and screenshots local to the private Linux environment. Do not upload them to GitHub, CI artifacts, issues or PR comments. The workflow does not need these files.

Set the actual paths in a private shell. `BIZHAWK_ROOT` must point to the directory containing `EmuHawk.exe` and `EmuHawkMono.sh`. Resolve Mono to a real executable path, rather than passing a shell command:

```bash
export BIZHAWK_ROOT='/absolute/private/path/BizHawk-2.11'
export MONO_REAL_PATH="$(readlink -f "$(command -v mono)")"
export CUE='/absolute/private/path/Vandal_Hearts_(RU)_v1.6.cue'
export BK2='/absolute/private/path/vandalhearts.bk2'
export WORKSPACE='/absolute/private/path/map02-first-run'
export FULL_BIN_SHA_FILE='/absolute/private/path/vandal-hearts-bin.sha256'
export KNOWN_LINUX_DLL_SHA256='VALUE_FROM_THE_SAME_SUCCESSFUL_LINUX_BUILD_RUN'
export KNOWN_LINUX_CORE_SHA256='VALUE_FROM_THE_SAME_SUCCESSFUL_LINUX_BUILD_RUN'
export KNOWN_LINUX_NATIVE_SHA256='VALUE_FROM_THE_SAME_SUCCESSFUL_LINUX_BUILD_RUN'

export VH_MAP02_CORE_EXPECTED_CORE_ASSEMBLY_SHA256="$KNOWN_LINUX_CORE_SHA256"
export VH_MAP02_CORE_EXPECTED_NATIVE_MODULE_SHA256="$KNOWN_LINUX_NATIVE_SHA256"
```

Create a private, owner-only full-BIN digest reference locally. This pins the exact copy being tested; by itself it is **not** independent release-authenticity proof.

```bash
umask 077
sha256sum '/absolute/private/path/Vandal_Hearts_(RU)_v1.6.bin' \
  | awk '{print $1}' > "$FULL_BIN_SHA_FILE"
chmod 600 "$FULL_BIN_SHA_FILE"
mkdir -m 700 "$WORKSPACE"
```

First run the no-launch preflight, then explicitly request one launch. Supply the verified Linux DLL digest, both Linux runtime-module pins, and the resolved Mono path:

```bash
python3 -m tools.map02_private_two_replay_runner \
  "$BIZHAWK_ROOT/EmuHawk.exe" "$CUE" "$BK2" "$WORKSPACE" \
  --private-full-bin-sha256-file "$FULL_BIN_SHA_FILE" \
  --auto-core-witness-plugin "$BIZHAWK_ROOT/ExternalTools/VhMap02CoreWitness.dll" \
  --private-core-witness-sha256 "$KNOWN_LINUX_DLL_SHA256" \
  --record-process-identity --mono-executable "$MONO_REAL_PATH" \
  --trusted-runtime-manifest-pin-file "$TRUSTED_PIN"

python3 -m tools.map02_private_two_replay_runner \
  "$BIZHAWK_ROOT/EmuHawk.exe" "$CUE" "$BK2" "$WORKSPACE" \
  --private-full-bin-sha256-file "$FULL_BIN_SHA_FILE" \
  --auto-core-witness-plugin "$BIZHAWK_ROOT/ExternalTools/VhMap02CoreWitness.dll" \
  --private-core-witness-sha256 "$KNOWN_LINUX_DLL_SHA256" \
  --record-process-identity --mono-executable "$MONO_REAL_PATH" \
  --trusted-runtime-manifest-pin-file "$TRUSTED_PIN" \
  --launch-one
```

The first command must complete before the explicit launch. If either runtime-module pin is absent or malformed, the trusted capture must fail before starting EmuHawk.

Audit the single saved capture locally with the same three pins:

```bash
python3 -m tools.map02_private_first_run_audit \
  "$BK2" "$WORKSPACE" \
  --private-core-witness-sha256 "$KNOWN_LINUX_DLL_SHA256" \
  --private-core-assembly-sha256 "$KNOWN_LINUX_CORE_SHA256" \
  --private-native-module-sha256 "$KNOWN_LINUX_NATIVE_SHA256"
```

If this audit fails, preserve the private diagnostics locally and do not start a second run. The two-run coordinator requires a fresh empty workspace; after the one-run audit passes, use a different private workspace for any later `--launch-two` experiment.

## Evidence limits

A passing Linux workflow proves that the code compiles against the official Linux package, that the real no-game EmuHawk process starts in CI, and that the synthetic guards pass. It does **not** prove that the owner's BIOS was mounted, that the original disc or BK2 was used by the running core, that MAP02 was reached, that the recorded frames are authentic, or that Nintendo Switch rendering matches the PS1 original.

The process receipt binds a Linux PID to a kernel process-start tick converted to UTC ticks using `/proc`; it is not cryptographic OS attestation. The C# witness hashes the mapped shared object's on-disk file, not its in-memory pages. Preserve these limits in all reports.

No Windows machine is required for this route, but a real Linux x86_64 runtime is required. A macOS host alone cannot execute the official BizHawk 2.11 Linux binary natively.

## Stage532 — owner-private manifest trust anchor (mandatory before capture)

The independent native Linux staging workflow now builds and verifies an installed
runtime **without** original game data. The manifest contains component digests,
but a self-consistent manifest alone is not an independent trust anchor.

After a verified owner-private build, calculate SHA-256 for the **exact raw bytes**
of `map02-owner-runtime-manifest.json`. Save this digest in a new line-oriented
owner-only file **outside** the runtime directory and outside public Git checkout.
Do not print it in CI, public PRs or public technical reports:

```bash
umask 077
export RUNTIME='/absolute/private/path/owner-runtime'
export TRUSTED_PIN='/different/private/directory/map02-runtime-manifest.sha256'
sha256sum "$RUNTIME/map02-owner-runtime-manifest.json" |
  cut -d ' ' -f1 > "$TRUSTED_PIN"
chmod 600 "$TRUSTED_PIN"
```

**Storage is a separate mandatory step.** Upload an immutable copy of the
actual manifest and its original SHA-256 to the project's private Google Drive
`00_Manifest_and_SHA256` folder, read back the Drive copy, and verify its
byte count and checksum before using the saved pin as trusted evidence.
Recording only a link or hash without verifying the stored copy is not enough.
The CI-created example pin is *synthetic*, and no owner-private runtime
manifest has yet been archived by CI.

Once the private Drive copy has been independently checked, verify a locally
retained trusted pin file using the new fail-closed gate:

```bash
python3 tools/map02_linux_octoshock/verify_owner_runtime.py "$RUNTIME" \
  --trusted-manifest-pin-file "$TRUSTED_PIN" --require-trusted-pin
```

The verifier requires the pin file to be a real, non-symlinked owner-owned
`0600` file outside the runtime with exactly one lowercase 64-digit SHA-256
line. It refuses missing pins, altered manifests and jointly modified native
libraries/manifest records. A successful result confirms file-level agreement
with the **supplied** trust anchor; it does not cryptographically attest live
loaded pages, BIOS selection, BK2 replay, MAP02 or Nintendo Switch parity.

Run this check before each private capture, and never treat the builder's
ordinary no-pin verification as authorization to load real media. Stage533
integrates this mandatory check into the private Linux Mono launcher and
coordinator; the independent Drive archival/readback of the owner pin remains
an essential prerequisite and is not supplied by public CI.

## Stage533 — mandatory Linux trusted-manifest gate in capture launcher

The Linux Mono capture route requires `--trusted-runtime-manifest-pin-file`
for both dry-run and real EmuHawk capture. This private owner-only file must
contain the previously trusted SHA-256 of the exact runtime manifest and must
reside outside the runtime directory. Pass it to both launcher and coordinator.
The parent coordinator verifies before reading private game files, before and
after each emulator process and again during final auditing. The child verifies
independently before reading game files, immediately before starting EmuHawk
and after the process exits. Any missing or mismatched pin fails closed.
Windows legacy launch behavior remains unchanged.

Append to every Linux owner capture command shown above:
`--trusted-runtime-manifest-pin-file "$TRUSTED_PIN"`.
Establish and read back the original private runtime pin in Drive before use;
CI-created ephemeral test values are never production trust anchors.
Successful file checks are not evidence of MAP02, BIOS load or in-memory pages.

## Stage534 — persistent private runtime archive readback

The canonical Vandal Hearts Project Evidence Archive currently contains no
runtime binaries in `07_Builds_and_Test_Artifacts`, and no owner-verified
runtime manifest/pin from a persistent installation in `00_Manifest_and_SHA256`.
Past CI proved a temporary no-media build, but the GitHub Actions runner's
runtime was not durably saved.

An **actual private Linux x86_64 owner environment** must execute the pinned
`build_and_stage_owner.py` to install a fresh runtime outside Git. Use the
Stage532/533 protocol to create a separate `0600` trusted manifest digest,
then upload that manifest and digest privately to
`00_Manifest_and_SHA256`. Upload a lossless **tar** archive of the entire
verified runtime, preserving modes, to `07_Builds_and_Test_Artifacts`. Keep
the archive outside GitHub/Actions and do not mix original BIOS/disc/movie.

Only a completely downloaded Drive copy counts as readback. For example, in a
private shell after a fresh runtime has been staged and pinned:

```bash
umask 077
tar -C "$(dirname "$RUNTIME")" -cpf /private/backup/vh-map02-owner-runtime.tar \
  "$(basename "$RUNTIME")"
sha256sum /private/backup/vh-map02-owner-runtime.tar \
  | cut -d ' ' -f1 > /private/backup/vh-map02-owner-runtime.tar.sha256
chmod 600 /private/backup/vh-map02-owner-runtime.tar.sha256
```

Retain the local archive digest separately, upload the tar and its checksum to
private Drive (tar in folder 07 and checksum in folder 00), download the
archive back from Drive to another private path, verify the downloaded tar
SHA-256 against the previously trusted digest, then extract only that checked
archive into a new private, non-Git directory. Do not trust an unverified
tar or extract it with privileged permissions.

```bash
sha256sum /private/readback/vh-map02-owner-runtime.tar \
  | cut -d ' ' -f1 \
  | diff - /private/backup/vh-map02-owner-runtime.tar.sha256
mkdir -m 700 /private/readback/extracted
tar -C /private/readback/extracted -xpf \
  /private/readback/vh-map02-owner-runtime.tar
python3 -m tools.map02_linux_octoshock.archive_owner_runtime \
  "$RUNTIME" /private/readback/extracted/"$(basename "$RUNTIME")" \
  --trusted-manifest-pin-file "$TRUSTED_PIN"
```

This gate verifies *both* trees separately against the external trusted
manifest SHA-256, then compares every regular file path, byte length,
SHA-256 and file/directory permission mode. It rejects omitted, additional
or corrupted files and empty directories, symlinks, permission drift and
nested/aliased source/destination roots. It emits only counts/status, never
private file paths or hashes.

Passing this tool means the downloaded-and-extracted copy matches the source
**as checked**, not that it originated from Google Drive: the owner must
confirm the download came from the actual private archive and preserve the
upload/readback evidence. CI exercises only synthetic tiny runtimes; it
does not archive any owner binaries or validate game playback.

## Stage535 — controlled private runtime tar pack / restore

Stage535 adds an owner-only alternative to generic `tar -xpf`: the
`private_runtime_tar.py` CLI. Use it for retained evidence; the earlier
Stage534 `tar` commands describe legacy/manual steps but do not validate
tar entry structure or independently detect path-escape entries.

After a *real* owner-private Linux runtime and independently trusted manifest
pin have been established, create a private tar and checksum file exclusively
outside Git and outside runtime (both output files absent, parent mode 0700):

```bash
python3 -m tools.map02_linux_octoshock.private_runtime_tar pack \
  "$RUNTIME" /private/backup/vh-map02-owner-runtime.tar \
  /private/backup/vh-map02-owner-runtime.tar.sha256 \
  --trusted-manifest-pin-file "$TRUSTED_PIN"
```

Upload the tar to the private Google Drive project folder
`07_Builds_and_Test_Artifacts`, and separately preserve the trusted tar SHA256
and original manifest pin under `00_Manifest_and_SHA256`. Only the tar should
contain runtime binaries, never original game BIN, CUE, BIOS, BK2 or PNG.

After independently downloading the actual archived tar into
`/private/readback/vh-map02-owner-runtime.tar`, run:

```bash
python3 -m tools.map02_linux_octoshock.private_runtime_tar restore \
  "$RUNTIME" /private/readback/vh-map02-owner-runtime.tar \
  /private/backup/vh-map02-owner-runtime.tar.sha256 \
  /private/readback/extracted/runtime \
  --trusted-manifest-pin-file "$TRUSTED_PIN"
```

The `/private/backup/...` SHA256 reference in the command is a previously
trusted LOCAL reference, not a checksum recalculated from the downloaded
tar or blindly accepted from an attacker-provided pair of files. The target
must not exist and its parent must be owner-only mode 0700.

Before creating the restored directory, this command checks the tar digest,
all member paths/types/modes/sizes and SHA256 payloads against the original
source tree. It forbids symlinks, extra/missing files, absolute/escaping paths
and duplicated entries. Extraction uses exclusive regular file creation, not
`tarfile.extractall`, and is followed by the Stage534 full-tree readback
check and both independently trusted manifest gates.

The tool makes NO uploads or downloads and always reports
`drive_upload_authenticated=0`: authentic Google Drive cloud provenance must
be established separately by checking the actual private Drive upload and
download. CI regression tests use only synthetic sample files.

## Stage536 — no-media native runtime archive roundtrip in CI

The pinned native Linux workflow now additionally tests the **complete**
installed BizHawk 2.11 / Octoshock runtime, not merely invented tiny fixture
files. After building and verifying the temporary installed runtime, it uses
Stage535's `private_runtime_tar pack` and `restore` commands, copies the tar
to a separate temporary readback location, and re-verifies the restored
manifest with the same CI-generated test pin. Any altered/missing file,
incorrect mode, symlink or unsafe tar member fails this workflow.

This is a **local CI copy**, not a Google Drive upload or a real owner-private
archive. The temporary trust pin is generated inside the same CI job and is
not independently established provenance. On every successful run the marker
`VH_MAP02_STAGE536_NATIVE_RUNTIME_TAR_ROUNDTRIP_PASS` explicitly reports
`drive_upload=0 trusted_owner_pin=0 capture_ready=0`. The real owner
runtime must still be installed durably and separately uploaded, downloaded
and checked in private Google Drive before accepting MAP02 capture evidence.

## Stage537 — actual owner-only Google Drive upload and readback utility

Stage536 confirmed that the real no-media Linux BizHawk/Octoshock runtime
passes complete tar pack/restore in CI (413 files and 139,113,480 bytes).
That temporary CI result is NOT a preserved backup. Stage537 introduces
`tools/map02_linux_octoshock/private_runtime_drive.py`, an owner-Linux-only
command that uses a pre-authenticated local `rclone` Google Drive connection
to upload files and actually download them again, validating all bytes.

Configure two **private local** rclone Drive remotes (OAuth token only
in the owner's private rclone config, never public code or CI):
- `vh_builds`: Google Drive type `drive`, root_folder_id of the project's
  *private* `07_Builds_and_Test_Artifacts` folder
- `vh_manifests`: Google Drive type `drive`, root_folder_id of the project's
  *private* `00_Manifest_and_SHA256` folder

Store the two **actual** folder IDs in a separate local `0600` JSON file
outside the runtime, Git checkout, and public CI, for example:

```json
{
  "builds_folder_id": "YOUR_PRIVATE_07_FOLDER_ID",
  "manifests_folder_id": "YOUR_PRIVATE_00_FOLDER_ID"
}
```

The tool compares the folder IDs from this privately saved map with the
authenticated remote configuration but never prints either the map or token.

The command independently inspects each remote's locally redacted config,
requires exactly these canonical folder IDs, and refuses environment overrides
of the backend config. It refuses collisions with existing remote filenames
and uses rclone `copyto --immutable` to avoid overwriting retained evidence.

After a *real* persistent owner runtime has been staged, its exact manifest
SHA-256 has been independently established as a mode-0600 file outside the
runtime, and Stage535's tar pack has created an archive plus local tar SHA,
run in a persistent owner-private Linux environment (not public Actions):

```bash
python3 -m tools.map02_linux_octoshock.private_runtime_drive \
  "$RUNTIME" "$TRUSTED_PIN" \
  /private/backup/vh-map02-owner-runtime.tar \
  /private/backup/vh-map02-owner-runtime.tar.sha256 \
  /private/readback/map02-owner-run-001 \
  --builds-remote vh_builds --manifests-remote vh_manifests \
  --session owner-run-001 \
  --private-folder-map /private/config/vh-map02-drive-folders.json
```

The readback path must not already exist, must be outside Git and runtime,
and its parent must be an owner-only mode-0700 directory. The session ID
must be globally unique for this archive and may not be reused.

The owner tool first locally extracts and verifies the entire tar in a
preflight directory before any upload, preventing a jointly tampered tar and
checksum from accidentally exposing other/private game files. It blocks
BIOS/disc/ROM/movie filename extensions in the source runtime.

The owner tool uploads an actual tar into the private builds folder and
the trusted manifest, manifest SHA256 and tar SHA256 into the manifest folder.
It then queries each remote file's ID and size, downloads each **separately**
into a new owner-private readback directory and hashes its actual bytes.
It extracts the separately downloaded tar only via the Stage535 strict
safe restore and Stage534 full-tree comparison. Finally, it writes an
owner-private JSON receipt with Google Drive IDs, per-object byte counts
and digests; it uploads that receipt to the manifest folder, downloads
it anew and verifies its full contents too.

The tool never uploads original CUE/BIN/BIOS/BK2/saves or private captures,
does not print paths, checksums or OAuth configuration, and does not run
any gameplay. An outcome marked `PASS` means actual local rclone remote
operations returned expected object IDs and the downloaded files matched
the originals byte for byte; separately verify folder privacy and preserve
the receipt in private Drive. It is still **not** proof that PS1 boot/MAP02
or Nintendo Switch parity succeeded.

GitHub Actions tests here run only a fake in-memory transport; public CI
must not carry a real rclone token or publish the owner-private tar.
The utility cannot be executed against the true Drive until a persistent
owner runtime and private authenticated rclone environment actually exist.

## Stage538 — sealed payload snapshot before private cloud transfer

Stage537 validated an owner-private tar before upload, but then passed mutable
original build-output paths to rclone. Stage538 closes that gap: the upload
utility now snapshots the verified tar, tar digest, manifest and independently
trusted manifest digest into a new owner-only `0700` staging directory with
exclusive `0600` files. Each snapshot is checked against the source SHA-256.

The tool performs a **second full safe tar extraction and complete runtime
comparison** on the sealed tar snapshot before invoking any rclone command.
Actual uploads use only these sealed paths, never the live runtime, and
downloaded bytes must match the recorded SHA-256 for each snapshot. The final
receipt is refused if any original source or sealed snapshot changed during
the transfer. This reduces the possibility of accidentally uploading
unverified or mutated original files. It does not protect against a compromised
owner system capable of modifying the sealed staging directory.

Public CI exercises only fictional backend transfers, including a test that
mutates the original tar during upload and verifies that no changed tar bytes
were sent or acceptance receipt created. It makes no authentic Google Drive
upload and creates no new original-game capture evidence.

## Stage539 — independently pinned recurring Drive restore audit

Stage537/538 proved an owner-private upload/download protocol with both
original runtime and original tar still available. Stage539 adds an independent
repeat-audit tool: `private_runtime_reaudit.py`. It can restore and inspect
an archived no-media runtime **after the original owner installation has been
lost**, provided three separately trusted owner-local SHA-256 pins survived:

1. SHA-256 of the original owner runtime manifest (mode 0600)
2. SHA-256 of the exact archived tar bytes (mode 0600)
3. SHA-256 of the original verified transfer receipt JSON (mode 0600)

Important: the trusted receipt digest must be calculated from the **locally
verified original receipt after Stage538's actual successful upload/readback**,
and kept outside Drive as an independent reference. Do not trust a digest
recalculated from a newly downloaded or possibly modified receipt. Keep the
SHA reference independently in the protected owner backup and record its
provenance in private handoff notes. Without it, do not claim the full
independent receipt audit succeeded.

Use two already authenticated folder-scoped rclone Drive remotes, with the
actual folder IDs saved privately in the existing mode-0600 JSON map:

```bash
python3 -m tools.map02_linux_octoshock.private_runtime_reaudit \
  --private-folder-map /private/config/vh-map02-drive-folders.json \
  --owner-manifest-pin /private/config/map02-owner-manifest.sha256 \
  --trusted-archive-pin /private/backup/map02-owner-runtime.tar.sha256 \
  --trusted-receipt-pin /private/config/map02-owner-receipt.sha256 \
  --new-readback-root /private/readback/independent-reaudit-001 \
  --builds-remote vh_builds --manifests-remote vh_manifests \
  --session owner-run-001
```

The audit refuses pre-existing or insecure local outputs. It checks two
Google Drive folder-scoped remotes, re-downloads the precise receipt,
verifies against the independently stored receipt digest, then downloads
the four runtime objects and compares each Google Drive object ID, size
and SHA-256 to the pinned receipt. It separately compares tar and manifest
bytes to their externally trusted SHA-256 files and verifies that the
downloaded digest files agree. It extracts the tar manually after inspecting
all member names and types, refusing links, path escapes, duplicate paths,
large payloads or extra archive roots. Finally it runs the pinned runtime
verifier with the owner's separate manifest hash and checks restored file
counts and size against the receipt.

A successful re-audit proves the preserved **no-media runtime archive is
recoverable against retained trust anchors**. It does not prove private
cloud sharing controls by itself or authenticate the real PS1 disc/BIOS/
BK2, cold MAP02 runtime evidence, or native Nintendo Switch playback.
CI runs only fictional small remotes and cannot substitute for a real
owner/private archive.

## Stage540 — automatic owner receipt pin and no-media re-audit parity

To remove the manual gap between Stage538's successful cloud readback and
Stage539's independently anchored re-audit, the **real owner-only** uploader
CLI now requires `--new-owner-receipt-pin /private/config/map02-owner-receipt.sha256`.
The chosen path must not already exist, must be outside Git/runtime and
the Drive readback directory, and must have an owner-only (0700) parent.
A new exclusive mode-0600 file is written **only after the originally uploaded
receipt has been downloaded from the Drive remote and byte-verified**.
It contains exactly the hex SHA-256 of those validated receipt bytes.
Preserve this pin independently of both the Drive archive and the staging
directory; do not treat a digest regenerated from a later Drive download as
an independent trust anchor. No owner/private backup is claimed until the
actual private upload command has run and the receipt pin is retained safely.

Add the flag to Stage538's private upload example:

```bash
  --new-owner-receipt-pin /private/config/map02-owner-receipt.sha256
```

Stage539's source-free re-audit also re-enforces the same conservative
original-media exclusions as Stage537/538, including nested or uppercase
`.bin` BIOS images and `.bk2` gameplay movies in tar entries. An archive
matching a trusted tar SHA is **not** a license to accidentally restore
original game/BIOS assets as part of the no-media runtime. Fictional CI tests
cover both rejected inputs and the new receipt-pin creation, without
downloading or uploading actual owner content.

## Stage541 — one-command private owner backup and source-free readback

Stage541 adds `tools/map02_linux_octoshock/owner_drive_session.py`.
It connects Stage535 pack, Stage538/540 sealed private Drive upload with
receipt-pin creation, and Stage539 independent source-free download/restore
audit into a **single fail-closed, owner-local** invocation.

An actual persistent private Linux x86_64 host with pinned `BizHawk 2.11`
and `Octoshock` build, installed `rclone`, and two already authenticated
folder-scoped owner-only Drive remotes is required. The command **does not**
build that runtime or manufacture the independently trusted manifest pin.

Before running: install and verify the real owner no-media runtime outside
Git; establish the SHA256 of the exact runtime manifest *independently* as a
private mode-0600 file and retain that anchor outside the cloud/runtime
session; save the real private Drive folder map in a separate mode-0600 file;
verify Drive folder access and correct private sharing permissions.

Example (run only on a persistent owner-private Linux host):

```bash
python3 -m tools.map02_linux_octoshock.owner_drive_session \
  --runtime /private/runtime/vh-map02-owner-runtime \
  --trusted-manifest-pin /private/trust/map02-owner-manifest.sha256 \
  --private-folder-map /private/config/map02-private-drive-folders.json \
  --new-session-root /private/evidence/sessions/owner541001 \
  --new-owner-receipt-pin /private/trust/map02-owner541001-receipt.sha256 \
  --builds-remote vh_builds --manifests-remote vh_manifests \
  --session owner541001
```

The parent of the new session root and of the receipt-pin output must be
existing owner-only `0700` directories, outside Git and the runtime. Both
destination paths must not exist. Failure does not silently delete
intermediate private files or retry using the same cloud session name;
inspect any partial uploads privately and choose new session identifiers.
The trusted manifest SHA must be an **independently established prior
reference** — simply hashing an unverified build and calling that owner
provenance is not acceptable.

On success the program verifies a locally packed complete no-media runtime,
uploads sealed snapshot files, confirms fresh downloads of all Drive
objects, creates a new independent local receipt pin, then **downloads the
archive and receipt once again** for the source-free auditor, safely restores
the runtime, and compares its file counts/bytes and owner pins. It prints
only a sanitized success marker, without credential contents, private
Drive folder IDs, raw file paths or per-file hashes. All original
PS1 CUE/BIN/BIOS/BK2 and game captures remain excluded.

Public GitHub Actions runs ten tests using fake in-memory Drive transport,
including a complete upload -> independent SHA -> re-audit -> simulated
loss of original runtime -> repeat restore sequence. Public CI cannot
create actual owner-private binary backups, does not contain OAuth tokens
and never constitutes evidence of authentic MAP02 gameplay.

## Stage542 — owner-only read-only archive preflight

Before creating a possibly large runtime tar or transferring any bytes, run
`python3 -m tools.map02_linux_octoshock.owner_session_preflight`
using the exact same flags as Stage541's owner-private full session.

The preflight checks: verified owner runtime against an independently trusted
mode-0600 manifest SHA, no BIOS/game/media files anywhere inside the runtime,
safe non-existing output paths with owner-only mode-0700 parents, available
local disk space of at least 10x unpacked runtime size or 512 MiB (whichever
is larger), redacted authentication/configuration of two folder-scoped
Google Drive remotes, and the absence of all five proposed remote object
names. It prints only safe counts and minimum free bytes — never private
paths, Drive IDs, access tokens, or file hashes.

On failure it refuses before any upload, output-directory creation or
manifest/receipt generation. Stage541's real complete archive command now
runs this gate automatically again before any local archive is written.
The preflight is **not** a proof of Google Drive sharing settings or
successful real binary backup, and it does not establish independent
provenance for an owner-generated manifest SHA. Public CI uses exclusively
fictional remotes and synthetic runtime bytes.

Example:

```bash
python3 -m tools.map02_linux_octoshock.owner_session_preflight \
  --runtime /private/runtime/vh-map02-owner-runtime \
  --trusted-manifest-pin /private/trust/map02-owner-manifest.sha256 \
  --private-folder-map /private/config/map02-private-drive-folders.json \
  --new-session-root /private/evidence/sessions/owner542001 \
  --new-owner-receipt-pin /private/trust/map02-owner542001-receipt.sha256 \
  --builds-remote vh_builds --manifests-remote vh_manifests \
  --session owner542001
```

## Stage543 — real rclone CLI compatibility gate

Stage543 adds an actual command-contract check in the owner-only Drive
transport. Before reading a remote's redacted configuration and before any
cloud upload, the tool calls `rclone version` and requires a parseable
version **1.64 or newer**. The `rclone config redacted [remote]` subcommand
used by our exact Drive backend/root-folder security check was introduced
in rclone 1.64; accepting older versions would make an otherwise correct
owner-private backup unexpectedly fail after provisioning. An unreadable
or outdated rclone version is rejected without emitting private host
details, remote IDs or credentials.

This does **not** substitute for actual authenticated Google Drive upload,
or assert that rclone remotes belong to the owner. The remote's backend
type, exact owner-private root folder IDs, forbidden environment overrides,
existing cloud object collisions and byte-for-byte receipt readbacks are
still checked separately. Public CI exercises version and flags against
an in-memory stand-in and never uses original PS1 media or owner tokens.

## Stage544 — independent tar trust survives loss of the owner session

Stage541 created an independent owner-private receipt SHA256 outside the
throwaway session, but the tar SHA256 itself was retained **inside** that
session. This meant Stage539's later source-free restore could not
honestly prove independent integrity after both the original installed
runtime **and** the temporary owner session directory were lost.

Stage544 closes that recovery gap. The full owner-only archive-session CLI
now requires `--new-owner-archive-pin /private/trust/owner544001-tar.sha256`.
The chosen output must be a NEW private regular file path outside the
installed runtime, Git, entire session directory, existing manifest pin,
folder-map file and receipt SHA pin. Parent must already be owner-owned
mode-0700. It cannot reuse or overwrite prior anchors.

The utility only creates the exclusive mode-0600 independent tar digest
**after the complete authenticated archive readback, receipt pin creation,
and separate source-free re-audit have all succeeded**. It compares the
local tar's freshly computed full SHA256 to the retained archive digest
before and after writing the external reference. Partial or corrupted
cloud transfers cannot yield a completed external tar pin.

The Stage544 synthetic integration test now simulates loss of BOTH the
owner runtime and **the entire disposable owner archive session** and
then re-downloads and verifies the fake cloud archive from the three
separately retained anchors: owner manifest SHA, external archive SHA,
and independent cloud receipt SHA.

For a real backup, store the three SHA256 trust references and their
generation/provenance in a protected owner-controlled offline backup
**independent of the cloud archive**. Moving files elsewhere on the same
machine alone does not protect against whole-host loss. The public CI
simulation does not actually save an owner binary to Google Drive.

## Stage545 — admission of an existing owner-private Drive archive

Once the real owner Linux host, authenticated Drive remotes and three
independently verified SHA-256 files exist, the command
python3 -m tools.map02_linux_octoshock.owner_archive_admission
accepts the same remote/session identity and trust anchors used for
Stage544. It does NOT require the original runtime installation or
disposable owner upload directory. It downloads all five original
Drive objects anew to a FRESH owner-only readback directory, verifies
the Drive object IDs and bytes against the pinned upload receipt,
compares archive and manifest against independent owner SHA-256 references,
and safely restores the entire runtime before creating a separate NEW
private mode-0600 admission JSON file.

Owner host command template (fill with actual private paths and the SAME
original archive session name):

python3 -m tools.map02_linux_octoshock.owner_archive_admission
  --private-folder-map /private/config/map02-private-drive-folders.json
  --owner-manifest-pin /private/trust/map02-owner-manifest.sha256
  --owner-archive-pin /private/trust/owner544001-tar.sha256
  --owner-receipt-pin /private/trust/owner544001-receipt.sha256
  --new-readback-root /private/evidence/independent-admission/owner545001
  --new-private-proof-file /private/trust/owner545001-admission.json
  --builds-remote vh_builds --manifests-remote vh_manifests
  --session owner544001

The arguments above must be supplied in ONE shell invocation, not as
independent shell commands. Private paths must exist only on the owner
host, not in the public repository. Offline pins must have been
independently retained BEFORE the cloud recovery trial; downloading
untrusted remote pins does not produce independent trust.

The proof records the three owner digest references, runtime count/bytes,
session and date, but no OAuth tokens or private Drive folder IDs. It
identifies whether the test injected a fake transport and explicitly
records that cloud folder sharing ACL and original PS1 MAP02 gameplay
are NOT verified by this check. Persist the proof through an independent
private Drive or offline backup. Public CI performs eight source-free
synthetic transport regressions only: successful restore after removal
of both source and upload session, corrupted remote tar or receipt,
altered local tar digest, wrong Drive remote, existing proof and unsafe
paths. These results must not be misreported as a genuine owner binary
archive or two original PS1 cold runs.

## Stage546 — independently SHA-sealed owner admission record

A fully verified source-free Google Drive archive admission produces a new
private JSON proof, but the proof itself previously lacked an independently
retained SHA256 reference. The owner-only Stage545 CLI now additionally
REQUIRES `--new-private-proof-pin`, a never-before-existing mode-0600
file outside the disposable readback, existing proof, runtime and Git.
It writes this reference only after the full independent cloud restore
and owner proof JSON have succeeded; it then rehashes the proof and the
SHA reference. An interrupted admission is never endorsed with a pin.

`verify_sealed_owner_admission` checks the original proof bytes against
the external SHA file, private file permissions, three referenced original
SHA256 anchors, provenance schema, safe record flags and real-vs-fake
transport distinction. With `require_real_transport=True` it refuses
fictional CI results. This is an *offline proof-integrity check*, not
independent confirmation of Google Drive folder permissions, owner
identity, original PS1 MAP02 gameplay or Nintendo Switch parity.

Run the prior Stage545 owner-only command with an added flag:
`--new-private-proof-pin /private/trust/owner545001-admission.sha256`.
Preserve JSON and its trusted SHA outside the source host, in the
private project's appropriate reports and manifest areas, with a
separate offline reference to its trusted origin. Public GitHub CI
tests only fictional remotes and owner-free invented bytes.

## Stage547 — owner trust-pin directory confinement

Stage539 source-free re-audit previously required the SHA files and
private-folder config to be owner-owned mode 0600, but did not explicitly
verify their *containing directories*. Direct calls to the re-auditor
could therefore accept a private-looking trust reference from a public
Git checkout, through a symlinked folder alias, or from a mode-0755
directory.

Stage547 strengthens `_private_input` used by both the source-free Drive
reauditor and the Stage545–546 admission verifier. Each private source
must be under an immediate owner-owned mode-0700 directory, with no
symlinked ancestor and no `.git` folder in the ancestor chain.
All referenced files retain their preexisting owner-owned mode-0600
requirement. The checks run before the private cloud download or the
creation of a restored runtime.

Three new fictional-only CI tests reject public directory permissions,
a SHA located inside a Git worktree and a SHA path with a symlinked
parent. Only source code, synthetic tests and safe documentation go
into public GitHub. Owner manifest, tar SHA, receipt SHA, admission
proof and admission proof SHA remain owner-controlled private files
stored separately and backed up outside the potentially ephemeral host.

Drive connector metadata checked on 2026-10-24 also showed
`shared=false` and an owner-only permission entry for the canonical
private Project Evidence Archive root and all eight child directories,
including `07_Builds_and_Test_Artifacts`. This is a current folder-level
configuration audit, **not** proof of any binary upload, file-level
visibility of future uploads, authenticated owner `rclone` use, or MAP02
gameplay. The canonical private builds folder is still empty. Do not
mark game capture or persistent backup as complete.

## Stage548 — mandatory repeat owner-backup gate before private MAP02 boot

**The real binary archive must ALREADY exist on owner-authenticated,
folder-scoped private Google Drive remotes.** Stage548 adds
`tools/map02_linux_octoshock/owner_capture_backup_gate.py`,
which takes the earlier Stage545–546 SHA-sealed owner admission JSON,
its independent SHA pin, the three externally trusted owner manifest,
tar and transfer receipt SHA files, and a NEW readback destination.
It first authenticates the prior admission's integrity and checks it
belongs to this exact owner archive session, then re-downloads all five
Drive objects again, safely reconstructs the entire runtime, and
compares file count, bytes and all trusted references with the
previously sealed admission report.

Owner-private execution template (all flags in ONE invocation):

```bash
python3 -m tools.map02_linux_octoshock.owner_capture_backup_gate \
  --private-folder-map /private/config/map02-private-drive-folders.json \
  --owner-manifest-pin /private/trust/map02-owner-manifest.sha256 \
  --owner-archive-pin /private/trust/owner544001-tar.sha256 \
  --owner-receipt-pin /private/trust/owner544001-receipt.sha256 \
  --admission-proof /private/trust/owner545001-admission.json \
  --admission-proof-pin /private/trust/owner545001-admission.sha256 \
  --new-restored-root /private/evidence/pre-capture/owner548001 \
  --builds-remote vh_builds --manifests-remote vh_manifests \
  --session owner544001
```

**Only actual rclone subprocess execution with an independently
SHA-sealed admission that already recorded real rclone may report
`owner_backup_proven_against_trusted_pins=true`.**
Even then it reports `capture_ready=false` because original PS1 CUE/BIN,
matched BIOS and original BK2 playback are different mandatory checks.
No game media is read or played in this backup test. A successful
fictional or public-CI fake Drive test always reports no real backup
and zero actual cold launches, regardless of restored fake bytes.

Seven regression tests emulate upload, destruction of the runtime and
disposable upload directory, independent first admission and deletion
of the first local readback, and only then the second fresh remote
restore. They also reject tampered earlier proof, session mismatch,
changed owner tar SHA, changed cloud tar or receipt and reused
download folder. **No OAuth secrets, original game, BIOS, BK2 or
owner runtime binary are placed into public GitHub.**

## Stage549 — rollback of unfinished owner archive trust references

Before Stage549, the owner archive orchestrator could leave a NEW,
owner-only receipt SHA-256 on disk if a later source-free independent
re-audit failed. The receipt represented an earlier successful remote
readback, **not** the completion of the complete owner archive session,
so such a leftover was unsafe to treat as final owner backup evidence.

Stage549 treats the newly allocated external `--new-owner-receipt-pin`
and `--new-owner-archive-pin` as an admission pair. **Only after**
the read-only owner manifest/remote preflight succeeds does the session
mark these two new outputs as belonging to the current attempt. If the
subsequent upload, first receipt sealing, independent remote restore,
tar-pin write or final rehash fails, any newly created mode-0600
owner-owned external references from this attempt are removed.
Pre-existing or unrelated owner trust files are never overwritten
or removed. Cloud objects and the temporary owner session directory
are deliberately **left intact on failure** for private forensic
inspection; a fresh upload attempt must use a NEW session name and
fresh private output paths.

Four additional fictional CI regression tests simulate a failure
after all five cloud uploads, a failure after writing an archive SHA,
a failure during receipt sealing and preservation of a separate
pre-existing owner reference. They check absence of misleading
external owner SHA files after rejection. Public CI includes no actual
Google Drive credentials, original PS1 disc, BIOS, BK2, extracted
audio, runtime binary artifacts or private captures.

**This is a fail-closed workflow safety improvement, not a real owner
authenticated upload.** The private canonical `07_Builds_and_Test_Artifacts`
folder still requires a genuine persistent owner Linux runtime upload
and independently verified readback, and original MAP02 cold game
launches remain separate checks.

## Stage550 — persistent owner build + three independently read-backed upload stages

Stage549 protected incomplete owner SHA references. Stage550 provides the
single **owner-host entrypoint**:
`python3 -m tools.map02_linux_octoshock.owner_persistent_backup`
with two explicitly separated commands, `prepare` and `publish`.
This is NOT a public CI upload; it must execute in a private persistent
Linux x86_64 host with explicitly authorized owner-controlled
folder-scoped `rclone` Google Drive remotes.

**First phase — build without game media:**

```bash
python3 -m tools.map02_linux_octoshock.owner_persistent_backup prepare \
  --new-runtime-root /private/persistent/vh550/runtime
```

The prepare command builds the verified upstream-pinned Octoshock and
BizHawk 2.11 runtime and the experimental witness plugin; it does not
accept, read or require the original game, BIOS or BK2. **It cannot
create an independently trusted manifest SHA file.** Independently
verify the resulting runtime manifest from an owner-controlled trust
source and retain the pin **outside** the runtime before publication.
A hash newly copied from the same untrusted runtime is not
independent provenance.

**Second phase — publish a pre-trusted runtime, then three readbacks:**

```bash
python3 -m tools.map02_linux_octoshock.owner_persistent_backup publish \
  --runtime /private/persistent/vh550/runtime \
  --independently-trusted-manifest-pin /private/trust/manifest.sha256 \
  --private-folder-map /private/config/private-drive-folders.json \
  --private-work-parent /private/persistent/vh550/work \
  --private-trust-parent /private/trust/handoff \
  --builds-remote vh_builds --manifests-remote vh_manifests \
  --session owner550001
```

This command never generates the original trusted manifest SHA:
it verifies a pre-existing externally supplied owner pin. It checks
**all seven new output locations before ANY upload**, refuses nested
work/trust roots, Git working trees, symlinked directories and reused
session names. It runs the owner-private upload+first authenticated
remote readback, independent admission+second readback with a sealed
proof, then the Stage548 pre-capture audit+third readback. The last
result compares the restored inventory and the original three pins.
A fake injected Drive transport reports
`authentic_owner_backup_claim_permitted=false`; real owner commands
require default `rclone` and scoped folder configuration.

All paths above are *examples*, not actual created owner archives.
The two output parent directories must exist, be separate,
owner-owned, mode 0700 and on **persistent storage**; the folder-map,
trusted manifest pin and rclone config must be established privately
ahead of time. Save new receipt/archive/admission SHA references and
the admission JSON independently beyond the single source machine
with a trusted origin. Unfinished remote objects and private work
folders are retained for diagnosis; a retry must use a new session
name. This tool never deletes the source runtime and does not mark
original PS1 MAP02, Switch gameplay or hardware parity as complete:
`capture_ready=false`, `cold_map02_launches=0`.

Ten synthetic regression cases exercise three fake-cloud readbacks,
the missing/incorrect independent manifest pin, output collision
before upload, nested/symlinked parents, fake-transport nonpromotion,
failed final-stage readback, duplicate session and prepare not issuing
a trust reference. The test-only synthetic suite is **not**
evidence of owner-authenticated Google Drive binary retention.

## Stage551 — persistent host storage gate (not a CI-only filesystem)

The Stage550 two-phase `prepare`/`publish` commands now enforce a
**read-only host storage check** on the real owner execution path before
any new build or cloud upload. The check refuses:
- non-Linux / non-x86_64 hosts; GitHub Actions/CI-related environment
  markers, including `RUNNER_TEMP` and `GITHUB_WORKSPACE`;
- private work, trust or runtime directories that are not owner-owned
  mode 0700, contain a symlinked directory component or are within Git;
- folders on temporary `overlay`, `tmpfs`, `ramfs`,
  `aufs`, `squashfs` or other ephemeral mounts, evaluated from
  `/proc/self/mountinfo` using the **most-specific mountpoint**;
- known temporary directory roots such as `/tmp` and `/run`;
- insufficient available filesystem space (at least 4 GiB for
  private runtime preparation and 2 GiB for the upload path).

The validator never creates files or opens original game media, and
never accesses OAuth tokens or contacts Drive. `prepare` verifies
the parent of the new runtime; real owner `publish` verifies the
runtime and both independent owner trust/work directories before
performing remote writes. Simulated CI Drive transport intentionally
bypasses any claim that the runner has persistent owner storage.
The new synthetic test suite checks temp mounts, CI environment,
public or symlinked private directories, Git checkouts, capacity,
mountpoint precedence, incorrect platforms and malformed mount tables.

A PASSED host filesystem check verifies only **current filesystem
placement and access mode**, not that a real cloud binary upload
occurred or that the disk will survive every host failure.
Persist a separate independently verified copy of the archive and
external trust pins in private Google Drive and verify remote ACLs.
No private original-game media, audio, BIOS, CUE/BIN or BK2 belongs
in public source CI; MAP02 real cold captures remain unverified.

## Stage552 — validate ALL owner backup storage, including source trust references

The Stage551 mount gate checked runtime and the new work/trust output folders,
but overlooked two equally important **input** locations: the containing
directory of the pre-existing independently trusted runtime-manifest SHA,
and the containing directory of the private Drive folder-ID configuration.
Stage552 adds both to the real owner `publish` filesystem audit, with
duplicate directories de-duplicated. If either source depends on a CI
overlay or other temporary mount, **stop before any Drive operation**.

The filesystem audit now accepts only an explicit set of reviewed local
Linux disk formats (`ext2/3/4`, `xfs`, `btrfs`, `zfs`,
`f2fs`, `bcachefs`, `jfs`, `nilfs2`). It rejects
unknown filesystem types, cloud/FUSE/network mounts such as `nfs`,
`cifs`, `9p`, `virtiofs` and `fuse.rclone`, plus
`overlay` and `tmpfs`; and refuses read-only mounts both in the
mountpoint flags and superblock flags from `/proc/self/mountinfo`.
The OS-owned mount table is parsed with its octal-escaped mount names,
and the most-specific mountpoint still wins.

New entirely source-free tests check unknown/remote filesystems, read-only
mounts, escaped-space mountpoints, and the *actual real-transport
branch* requiring both source trust-directory and folder-map-directory
audits before any upload. This confirms only code enforcement under
simulation; it does NOT certify that an actual persistent owner host or
rclone Drive account was used.

All original PS1 game assets/audio/BIOS/BK2 stay private and unchanged.
Canonical private `07_Builds_and_Test_Artifacts` still needs an actual
owner-authenticated binary runtime archive; synthetic native CI does
not satisfy this gate or genuine two-cold-launch MAP02 proof.

## Stage553 — match the mounted filesystem with the actual Linux directory device

Stage552 made the owner-persistent preflight allowlist-only for local,
writeable Linux file systems and covered **all five owner data locations**.
However, identifying a matching mountpoint and its declared filesystem
type was not yet sufficient to establish that the mount record belonged
to the *actual visible filesystem* of the private directory.

Stage553 reads the Linux mountinfo `major:minor` device identifier and
uses `os.makedev()` to compare it against `stat().st_dev` on each
owner-private directory. A forged, stale, buried or inconsistent
mountinfo entry may no longer claim `ext4` to pass a directory that
the kernel identifies as being on another filesystem. Equally specific
mountpoint entries with conflicting device/type/write-permission state
are rejected fail-closed instead of accepting the first match.

Four additional **fictional-only** tests cover mismatching device IDs,
duplicate stacked mounts with different devices, conflicting mounted
read-only state, and invalid mount device fields. Existing simulated
mounts are updated to use the real temporary test directory's
`st_dev` so tests prove both positive and negative identity checks.

This is still a runtime **observation** of the owner host; it does not
certify physical disk redundancy, cryptographic origin of a trusted
owner manifest SHA, or a persistent authenticated Drive upload.
The CI runner uses entirely synthetic Drive transport and does NOT
store the original game's CUE/BIN, BIOS, BK2, audio or raw private
captures in GitHub. The original MAP02 two cold gameplay captures
remain unverified.

## Stage554 — owner-private ancestor directory write protection

The Stage551–553 owner host gate checked the private directory itself,
local disk filesystem, writeability, and kernel filesystem device identity,
but an owner-only mode-0700 leaf can still be located under a directory
writable by other users or groups. Another writer of that ancestor may
replace a pathname between the preflight and the real operation.

The gate now inspects **each ancestor directory** of every private path
before any build or cloud write. It refuses group- or world-writable
ancestors unless an ancestor is a **root-owned sticky directory** (the
normal Linux `/tmp` exception). The production temporary-path policy
still independently rejects `/tmp`, `/var/tmp`, `/run`, and related
temporary roots, so the exception does not make owner runtime under
a temporary path permissible.

Four additional synthetic tests exercise safe nested ancestry, group
writability, world writability, and a writable ancestor separated
from the private leaf by another directory. This is a conservative
placement check, **not** a claim of race-free openat/fd-based path
anchoring, physical disk persistence, actual owner-authorized Drive
upload or MAP02 gameplay proof. Original PS1 data and audio remain
owner-private and outside GitHub and synthetic CI.

## Stage555 — detect owner-host directory replacement across long operations

Stage551–554 checked the private host placement at the beginning of
`prepare` and `publish`, but a directory can be renamed and replaced
after those checks while preserving the same final path and mode 0700.
The Stage555 owner-only safety checkpoint records the Linux filesystem
device, inode, UID and permission bits of **every private directory
and each ancestor**. It compares this read-only identity record with
fresh kernel stat results and reruns the full persistent filesystem
preflight after the long build, after runtime digest checking and before
owner-authenticated upload, and at boundaries before and after the
subsequent independent archive readbacks. Any mismatch prevents the
command from reporting success.

Five new synthetic host tests check unchanged inode acceptance, replaced
leaf rejection, replaced ancestor rejection, modified permissions and
an invalid empty baseline. Three fictional-Drive orchestration tests
exercise fail-closed rejection immediately before upload, refusal to
start admission after a directory swap following upload, and refusing
a successful `prepare` marker after a build-time storage change.

This is **checkpoint-based replacement detection**, not a lock, an
atomic file-descriptor-anchored traversal, or a way to rule out all
time-of-check/time-of-use races between checkpoints. Rejection after
a partial upload deliberately retains any already uploaded private
objects for forensics but must never be treated as a sealed final owner
backup. Retrying requires a fresh session and a new independently
verified trust path. The prior externally supplied manifest SHA remains
a separate mandatory input and may never be manufactured by the build.

Game CUE/BIN, BIOS, BK2, original audio, raw private MAP02 captures and
OAuth credentials remain outside public GitHub. Passing synthetic and
source-free native CI does **not** demonstrate authentic persistent Drive
binary retention, two independent PS1 gameplay launches or Switch parity.
The PR remains Draft pending those independent evidence gates.

## Stage556 — descriptor-anchored read of private Drive folder-map

The Stage555 storage checkpoints can detect changes between observations,
but they do not pin an individual file during the read. Previously the
folder-scoped Google Drive mapping was checked by path, then reopened with
`Path.read_text`. An attacker able to replace its directory entry between
the two operations could redirect the requested Drive destination.

Stage556 confines this specific sensitive read to an owner-private directory
file descriptor opened with `O_DIRECTORY|O_NOFOLLOW`. The mapping itself
is opened relative to that directory with `O_NOFOLLOW`, under its existing
owner-only mode-0600 rule. The reader compares device/inode and metadata
against the original path observation, checks bytes before JSON parsing,
enforces a 2048-byte limit, and rechecks both directory and file identity
after reading. If a path is replaced before open, after open, or with a
symlink, the operation rejects instead of interpreting the mapping. The
old normal behavior remains for an unchanged valid private mapping.

Five new simulated-only tests exercise accepted owner-only mapping, an
identical-content inode swap before open, a pathname swap after open,
a symlink swap, and oversized input. All existing fictional transfer
and independent readback checks must continue to pass.

The scoped directory FD prevents a swapped leaf from being silently read.
It is **not** a comprehensive FD-anchored traversal of all ancestors or a
cryptographic attestation of owner identity; the wider Stage555 path
checkpoints and independently trusted manifest references remain mandatory.
No original game, BIOS, BK2, audio, private captures or OAuth secrets are
used in public tests. CI and its fictional transport never prove genuine
owner-authenticated binary retention. Original MAP02 two-cold-run evidence
and Switch parity remain pending; PR #505 stays Draft.
