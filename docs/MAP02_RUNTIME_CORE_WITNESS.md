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
**The C# External Tool now compiles against real SHA-256-pinned official
BizHawk 2.11 Windows binaries** in GitHub Actions (Stage501). However,
it has NOT been loaded or run inside an authentic owner EmuHawk
session. The Python witness verifier has separate synthetic CI coverage.

## Stage501: real official BizHawk 2.11 assembly compatibility

The Stage501 Windows GitHub Actions workflow downloads the exact
upstream `BizHawk-2.11-win-x64.zip`, independently verifies the GitHub
release SHA-256 before extraction, and compiles the **same
`VhMap02CoreWitness.csproj`** using `VH_BIZHAWK_RELEASE_ROOT`
against its real `EmuHawk.exe`, `BizHawk.Client.Common.dll` and
`BizHawk.Emulation.Common.dll`. The first run exposed a genuine C#
non-nullable late-injection error; it was fixed, and the next Windows
build passed with **zero warnings and zero errors**.

The Actions workflow also retains a **short-lived experimental DLL-only
artifact** (`vh-map02-bizhawk211-experimental-core-witness`) for
14 days. It contains only our compiled source, **no** original ROM,
BIOS, BIN, CUE, BK2, screenshots or official BizHawk binaries. For
testing it locally, download the artifact from the exact-head successful
GitHub Actions run and install the extracted
`VhMap02CoreWitness.dll` in the `ExternalTools` folder of the
**matching unmodified BizHawk 2.11 Windows installation**. This is
an experimental build, not a runtime-certified plugin. Keep the
original game files entirely separate from GitHub checkouts.

The original owner-local source build workflow described below
remains supported. CI only confirms compilation, **not** runtime load,
service injection, movie replay, BIOS, actual disc mount or MAP02
frames.

## Stage502: real DLL discovery and constructor smoke

An additional **Windows .NET Framework** executable now inspects and
instantiates the compiled witness against the exact official BizHawk 2.11
assemblies. Its test mirrors the source of
`ExternalToolManager.GenerateToolTipFromFileName()`, checking that:

- the DLL directly references BizHawk;
- there is exactly one concrete `IExternalToolForm` entry class annotated
  `[ExternalTool]`, with the expected tool name;
- the `IEmulator` property is publicly writable and decorated with
  `[RequiredService]`;
- creating the Windows Form in the standalone host succeeds, and calling
  `Restart()` without an injected PSX core leaves the **Save** button
  disabled (failure-closed).

The workflow uses the pinned release binaries and places only our
experimental DLL into the release's `ExternalTools` directory in CI.
It deliberately does **not** launch `EmuHawk.exe`, load a PS1 game,
attach BIOS, deliver controller inputs or capture frames.

A passed Stage502 smoke test therefore supports **DLL discovery
metadata and constructor safety in a release-compatible .NET process**,
not in-process injection by the genuine EmuHawk UI. True loaded core,
firmware/media identity and BK2/MAP02 visual parity still require
owner-local runtime evidence.

## Stage503: synthetic IEmulator injection in the real Windows loader host

After Stage502 established that the Windows Form could be instantiated
against official BizHawk 2.11 binaries, Stage503 tests its **core-gating
logic** with five fictional `IEmulator` implementations compiled into
the standalone Windows loader smoke program.

The test constructs a dummy C# class annotated `[Core("Octoshock", ...)]`
whose `SystemId` says PSX and `Frame` is 1666. It injects this mock
through the same publicly writable `[RequiredService] IEmulator`
property that the real EmuHawk host is expected to populate; calls
`Restart()`; and checks that the Save button enables. It invokes the
private `Snapshot` helper **only in memory** and verifies that its
structured text retains all explicit `bios=unverified`,
`disc=unverified` and `movie_sync=unverified` fields.

Four other invented cores must fail closed: an annotated Nymashock,
an Octoshock-named non-PSX system, a negative frame counter, and an
unannotated IEmulator class. Clearing the injected service must disable
Save again. The plugin also initializes Save as disabled **before any**
BizHawk service injection and tolerates missing CoreAttribute metadata.

These examples do **not** implement real PlayStation frame advancement
or provide a BIOS, game disc, BK2 input or verified runtime injection.
The test's fake `[Core("Octoshock")]` attribute can impersonate an
actual core: its acceptance only confirms **the implementation's
decision logic**, not authentic provenance.

The Windows CI requires an exact `fake_iemulator_positive=1`,
`fake_negative_gates=4`, `in_memory_fake_witness_schema=1` success
marker, with `emulator_process_started=0`. No private witness,
process identifier or sample data is published.

## Stage504: genuine EmuHawk process with no original media

BizHawk 2.11's **real** `ArgParser` supports
`--open-ext-tool-dll VhMap02CoreWitness.dll`. Upstream `MainForm`
uses it to find an enabled External Tool menu item and call its actual
`ToolManager` loader. `NullEmulator` provides an `IEmulator` service
even with **no game loaded**; the plugin must then refuse saving since
the platform is not PSX.

The Stage504 Windows CI launches the exact SHA-256-pinned official
`EmuHawk.exe` with **only** that external-tool argument, without a
ROM, BIOS, disc, movie, Lua script or network input. A short,
process-ID-scoped Win32 window enumerator looks for the plugin's
actual window title and its **disabled** `Write private core
witness...` button. The probe makes no clicks, saves no
witness or screenshots, terminates the tested EmuHawk process, and
prints only a fixed success marker. It will fail closed if the form
never appears, EmuHawk exits, or the Save button is active without
a PSX core.

This provides an opportunity to verify real in-process
`MainForm → ExternalToolManager → ToolManager → Form.Restart`
interaction without putting game data in CI. It still proves
**nothing** about real Octoshock injection, BIOS, original
BK2 playback or MAP02: the no-media core is `NullEmulator`.
The ability to show a GUI depends on the hosted Windows runner's
desktop environment, so a Windows CI failure must be diagnosed
rather than interpreted as a game or core bug.

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
for the literal `core_source=IEmulator.Attributes.CoreName` semantics, PSX,
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

The Python CI suite exercises **20 invented witness pairs**; the
Stage501 Windows CI additionally **compiles** the plugin against
official SHA-256-verified BizHawk 2.11 binaries. Neither CI workflow
runs EmuHawk, authenticates a live core or touches original game
assets. Keep the corresponding PR in Draft.

Official sources consulted: BizHawk
`src/BizHawk.Client.EmuHawk/MainForm.Movie.cs`,
`src/BizHawk.Client.EmuHawk/tools/ToolManager.cs`, and the
`ExternalToolProjects/HelloWorld` sample.
