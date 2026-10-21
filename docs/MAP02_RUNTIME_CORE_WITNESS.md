# MAP02: runtime IEmulator core witness (Stage500)

## Why this exists

The original USA BK2 declares PSX/Octoshock, and the existing Lua
`client.getconfig().PreferredCores["PSX"]` check asks what the frontend
**prefers**. Neither establishes the *actual* core instance loaded by EmuHawk:
a forced-core selection can differ from the preference.

BizHawk's .NET `IEmulator` service exposes the *currently loaded* emulator
instance. Official upstream EmuHawk uses `Emulator.Attributes().CoreName`
when recording movie core metadata and displaying core information. The
public upstream External Tool example documents `[RequiredService]` for
injection of services after construction. The new tiny optional tool reads
**the injected live IEmulator**, not BK2 metadata or configuration.

This is a practical path to genuine owner-local runtime core evidence.
**It has not yet been compiled or run inside an authentic owner EmuHawk
session**; only the Python verifier has synthetic CI coverage.

## Owner-local build (requires a matching, unmodified BizHawk source tree)

1. Use your own BizHawk **2.11** source tree and local EmuHawk build/output.
   Do not place CUE, BIN, BIOS, BK2 or captures into this source tree.
2. Copy both public-source files from
   `tools/map02_runtime_core_witness/` into a **new**
   `ExternalToolProjects/VhMap02CoreWitness/` directory inside that
   private BizHawk checkout:
   `CustomMainForm.cs` and `VhMap02CoreWitness.csproj`.
3. From the directory containing the new `.csproj`, build using the
   upstream SDK/.NET Framework tooling, e.g.:

       dotnet build VhMap02CoreWitness.csproj -c Release

   This project imports the real upstream `NET48ExternalToolForm.targets`
   and `ExtToolCommon.props`. The upstream targets reference EmuHawk and
   other DLLs in the local output tree and copy the resulting assembly to
   `output/ExternalTools`. This is an **owner-local example**, not a
   prebuilt or runtime-validated distribution.
4. Start EmuHawk from that matching output installation with your original
   PS1 CUE/BIN and BK2 **locally**. In `Tools → External Tools`, open
   `VH MAP02 Core Witness`. This is a manual GUI action, not an
   automatically injected plugin or silently loaded DLL.

## Make two separate runtime observations

While the original PS1 game is running in each independently launched
EmuHawk process:

- Verify that the tool says the injected `IEmulator` reports PSX/Octoshock.
- Choose **Write private core witness...** and select an **existing,
  owner-private folder outside any Git repository or symlinked directory**.
  The tool creates a new uniquely named plain-text file without overwriting.
  It never copies a frame, game hash, BIOS or pathname into this file.
- Close EmuHawk completely, then launch a **new process** and repeat in the
  same owner-private folder. Two clicks in one process are not independent
  replays and the verifier rejects them.

**Privacy:** the folder chooser uses the operating system's permissions.
On Windows, restrict the selected folder to the owner in Windows security
properties. The tool does not grant or validate NTFS ACLs. It does not
attempt to read/write BIOS, BIN, BK2 or PNG content.

## Local paired audit

    python3 -m tools.map02_private_core_witness_audit \
      /private/vh-map02-runtime-core-witness-first.txt \
      /private/vh-map02-runtime-core-witness-second.txt

The filenames above are illustrative; the External Tool creates random
filenames. The verifier enforces a fixed, LF-only, ASCII schema and checks
for the literal `source=IEmulator.Attributes.CoreName` semantics, PSX,
Octoshock, reasonable frame/process identifiers, two **distinct**
`(PID, UTC process start time)` pairs, no unsupported fields, bounded
size, source stability, regular files, no symlinks and no Git checkout.
Reports expose **only** booleans and a count: never process IDs, start
times, original paths, hashes or media data.

The export records the system, **active core name sampled by the
external tool**, frame count, and process identity (PID/start time) in
a private file. All BIOS, disc and movie-sync fields MUST remain
`unverified`.

### What this does and does not prove

If the owner runs a matching authentic External Tool inside genuine
EmuHawk, it is direct testimony from the loaded `IEmulator` instance,
stronger than observing only the preferred core. However:

- The text file can be edited or fabricated. The verifier tests format
  and distinct *reported* process identities; it cannot cryptographically
  prove EmuHawk produced the text or that both tools came from the same
  sessions as the Lua/PNG captures.
- The witness does **not** reveal the served BIOS, mounted source disc,
  actual input delivery, original BK2 replay success or scene identity.
- The separate owner-private CUE/BIN, BK2, BIOS and MAP02 screenshot
  checks remain mandatory before authentic gameplay or remake fidelity
  can be claimed.

The CI suite exercises **20 invented witness pairs**; it does not build
the Windows BizHawk plugin, run EmuHawk, authenticate a live core or
touch original game assets. Keep the corresponding PR in Draft.

Official sources consulted: BizHawk
`src/BizHawk.Client.EmuHawk/MainForm.Movie.cs`,
`src/BizHawk.Client.EmuHawk/tools/ToolManager.cs`, and the
`ExternalToolProjects/HelloWorld` sample.
