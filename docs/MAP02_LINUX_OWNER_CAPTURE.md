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
