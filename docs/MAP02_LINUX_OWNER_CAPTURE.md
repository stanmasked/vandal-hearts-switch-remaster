# MAP02 owner-local capture on Linux x86_64 (Stage520)

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
