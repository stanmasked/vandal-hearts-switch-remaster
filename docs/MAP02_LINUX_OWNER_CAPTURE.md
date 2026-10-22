# MAP02 owner-local capture on Linux x86_64 (Stage520)

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

The Linux workflow downloads that exact archive and verifies this digest before inspecting the package. It then records the managed `BizHawk.Emulation.Cores.dll` and native Octoshock module hashes and compiles the External Tool against the actual Linux package.

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
  --record-process-identity --mono-executable "$MONO_REAL_PATH"

python3 -m tools.map02_private_two_replay_runner \
  "$BIZHAWK_ROOT/EmuHawk.exe" "$CUE" "$BK2" "$WORKSPACE" \
  --private-full-bin-sha256-file "$FULL_BIN_SHA_FILE" \
  --auto-core-witness-plugin "$BIZHAWK_ROOT/ExternalTools/VhMap02CoreWitness.dll" \
  --private-core-witness-sha256 "$KNOWN_LINUX_DLL_SHA256" \
  --record-process-identity --mono-executable "$MONO_REAL_PATH" \
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
