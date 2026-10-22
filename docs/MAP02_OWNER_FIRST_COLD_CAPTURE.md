# MAP02 Stage512 — first owner-private PS1/Octoshock cold capture

This is a **single** diagnostic run of the owner's own original PlayStation
disc and BK2, not a proof of MAP02 gameplay. It runs **only on the owner's
Windows workstation**, not in public CI. Do not upload BIN/CUE, BIOS, BK2,
screenshots, full-disc digests, absolute paths, process logs or witness
receipts to GitHub or paste them into a PR/issue/chat.

## What changed

`tools.map02_private_two_replay_runner` now accepts `--launch-one`
(in addition to the existing `--launch-two`). **Without either option,
the runner only validates media and builds an in-memory candidate plan:
it does not create files or start EmuHawk.**

`--launch-one` starts exactly one new local EmuHawk subprocess, using
the same complete media, BK2, firmware, private-output ACL and source-stability
checks as `--launch-two`. It writes a private plan and a single
`vh-map02-cold-01` folder. It independently validates the Lua log, every
planned private PNG, and, in automatic mode, the early PSX/Octoshock core
receipt against the real Windows process ID/start-time receipt **and the
first planned capture frame**. The original CUE/BIN and BK2 are checked
for changes after the run. A requested private full-BIN checksum reference
is reread and rechecked before and after the capture.

It never creates `vh-map02-cold-02`, never invokes the two-run RGB/pixel
comparison, and never claims two cold boots. If the first process fails,
the command fails with redacted output rather than proceeding to a second.

## Owner-only prerequisites

1. Use your **own** official BizHawk 2.11 Windows installation with
   `EmuHawk.exe`; the separately built and previously smoke-tested
   `VhMap02CoreWitness.dll` must be installed under that exact
   installation's `ExternalTools` directory.
2. Have the original privately stored CUE and its sibling BIN, a separately
   stored original BK2, and the required local PSX firmware configured in
   BizHawk. BIOS cannot be authenticated merely by the presence of a file.
3. Use a new, empty, absolute output directory owned exclusively by
   your Windows account. The NTFS guard rejects shared/everyone-readable
   folders; it does **not** automatically fix ACLs. Never use a Git checkout.
4. Start with one capture window (`--max-windows 1`) and a bounded
   watchdog. The BK2 is 933,949 frames long and may be incompatible with
   the owner's RU v1.6 disc even though its original metadata references
   USA PSX/Octoshock. The local media preflight checks the known disc
   profile; it does not assert that the chosen movie is playable.

## Windows PowerShell — use local variables, never publish real values

Example paths here are fictional placeholders. Run from a local source checkout,
but **keep all original game files, BIOS, outputs, and tool DLL in separate
owner-private directories outside the checkout**.

```powershell
$emuhawk = 'C:\\ExamplePrivate\\BizHawk-2.11\\EmuHawk.exe'
$cue = 'C:\\ExamplePrivate\\Game\\Vandal_Hearts.cue'
$bk2 = 'C:\\ExamplePrivate\\Game\\vandalhearts.bk2'
$workspace = 'C:\\ExamplePrivate\\MAP02-first-check'
$tool = 'C:\\ExamplePrivate\\BizHawk-2.11\\ExternalTools\\VhMap02CoreWitness.dll'
$common = @(
  $emuhawk, $cue, $bk2, $workspace,
  '--max-windows', '1',
  '--record-windows-process-identity',
  '--auto-core-witness-plugin', $tool
)
# First validate privately without writing or launching anything.
python -m tools.map02_private_two_replay_runner @common
# Only after the local preflight succeeds: explicit ONE-process capture.
python -m tools.map02_private_two_replay_runner @common --launch-one
```

The owner may additionally specify `--private-psx-bios-candidate` or
`--private-full-bin-sha256-file` if the corresponding private files
and metadata have been inspected. The preflight may reject original
media/movies with a mismatched profile; do not bypass the rejection by
replacing game bytes or weakening the check.

After a successful one-run check, inspect the screenshot(s) **locally**
to decide if the scene is actually MAP02. Keep an independent note of
the screenshot's contents; do not upload the original image. If the
process fails, inspect the private `vh_emuhawk_process.log` and
`vh_private_capture.log` on the workstation only.

For an independent two-run repeatability test, use a **different new
empty private workspace** with the original `--launch-two` path.
Do not reuse the one-run folder or treat the first diagnostic as the
second independent cold boot. The combined auditor requires two
separately witnessed capture folders.

## CI versus real acceptance

Public GitHub CI uses invented file contents and subprocess mocks only.
It can confirm CLI opt-ins, no-public-output behavior, absence of a
second process, preflight guards, and unchanged two-run semantics.
It **cannot** load the owner's original game. Even a successful owner
single-run report does not prove actual BIOS/disc identity, BK2 input
delivery, original MAP02 scene identity, a second independent cold boot,
Nintendo Switch GPU parity or gameplay on physical hardware.

## Stage513 — independently recheck the saved first capture without starting EmuHawk

After **one owner-local `--launch-one` attempt** completes and leaves an
existing protected `vh-map02-cold-01` directory, run the offline review
in the same private Windows environment. This step never starts a process,
does not modify the movie, plan, witness or PNG files, and does not create
or assume a second capture.

```powershell
# Reuse the PRIVATE $bk2 and $workspace variables from above.
python -m tools.map02_private_first_run_audit $bk2 $workspace
```

In the default automatic-witness mode, the review expects a
`vh-map02-runtime-core-auto.txt` under the first capture directory
and a matching owner-local `vh_emuhawk_process_identity.txt`. It
reconstructs the capture plan from the original BK2, checks the Lua
log and every PNG, requires the strict core/process PID and Windows
creation-time match, and rejects any reported core frame after the
first planned PNG. The tool fails closed if the expected witness was
never recorded before the first image.

For a separately exported *manual* C# witness, explicitly opt into
manual audit, passing its private path:

```powershell
python -m tools.map02_private_first_run_audit $bk2 $workspace \
  --manual-core-witness 'C:\\ExamplePrivate\\manual-core-export.txt'
```

Manual-mode records must **not** contain the early automatic-witness
Lua marker. A manual core witness may have a later frame than the first
PNG, so it is not misrepresented as pre-screenshot evidence.

The offline reviewer refuses a workspace that already contains
`vh-map02-cold-02`, because one-run proof and two-run repeatability
are different acceptance procedures. To compare two replay attempts,
use a new owner-private workspace and the dedicated two-run reviewer.

**Never copy the owner's complete output JSON, game files or captured
images into GitHub.** The offline reviewer prints only counts, flags
and fixed schema names, never filenames, file digests, game bytes,
screenshots, Windows PIDs or private machine paths. Its passing result
still does not prove that the original MAP02 appeared, that the correct
BIOS/disc was mounted, that BK2 controller input arrived in-game or that
a Switch renderer matches the original.

## Stage515 — prepare one new owner-only Windows NTFS workspace

Before the local dry-run or `--launch-one`, create a **brand-new empty**
output folder using the owner-local PowerShell helper. This avoids
manual ACL mistakes. The helper does not touch original PS1 media or
start any emulator. It never prints private paths, SID values or ACLs.

Run these commands on your own Windows workstation in **Windows PowerShell
5.1**. The parent directory must already exist, and both the parent and
chosen workspace must be **outside a Git checkout**. The example folder
names are fictional:

```powershell
$workspace = 'C:\\ExamplePrivate\\MAP02-first-check'

# No folder is created by the default preflight.
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\\tools\\map02_owner_private_workspace_prepare.ps1 -Workspace $workspace

# Only this explicit switch creates an empty owner-exclusive folder.
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\\tools\\map02_owner_private_workspace_prepare.ps1 -Workspace $workspace -Create
```

The preflight prints a fixed marker with `created=0`. Successful
creation prints `created=1 acl=owner_only original_media=0`, only
**after** assigning a protected owner-only NTFS DACL and passing the
same strict ACL guard the capture tools use.

It deliberately refuses an existing directory (even if empty),
missing intermediate parents, drive-root locations, reparse-point
ancestors, paths within Git, and unsafe relative paths. **Never**
repeat `-Create` against a previously used capture workspace.
For a second independent capture, choose a different new private
folder and run the preparation again. The helper will not open,
copy, modify, rename, delete or checksum your original game or BK2.

The helper has no ability to install the experimental
`VhMap02CoreWitness.dll`, configure PSX firmware in BizHawk,
or authenticate which original disc loads. Those are still
separate owner-local prerequisites. A passing workspace check
alone is not evidence of original MAP02 graphics or Switch gameplay.

## Stage516 — safely install the experimental Octoshock core-witness DLL

The Windows compiler workflow for Stage516 retrieves the **official
BizHawk 2.11 x64 ZIP**, verifies the pinned release SHA-256, builds
`VhMap02CoreWitness.dll` against its original assemblies, and uploads
**only** that public experimental DLL as a GitHub Actions artifact.
The owner can download the artifact from the successful
**MAP02 real BizHawk 2.11 External Tool compile (no game media)**
workflow; it contains NO original disc, BIOS, BK2, PNG or game data.

On the owner's Windows machine, verify the original BizHawk ZIP itself
before extracting it. The pinned 2.11 release ZIP SHA-256 is:

```text
722b5aac5e1d89f890b2875b0150f4a86f5762d211f7cd47029cac70434955c0
```

The extracted BizHawk folder must include `EmuHawk.exe` plus
`dll/BizHawk.Client.Common.dll` and
`dll/BizHawk.Emulation.Common.dll`. Keep it outside the project Git
checkout. This protects against mixing different release versions, but
checking the DLL alone cannot authenticate every file in a user-modified
BizHawk installation.

The successful Stage516 compilation workflow prints
`VH_MAP02_EXPERIMENTAL_DLL_PUBLIC_SHA256=<digest>`. Obtain that value
from the **same trusted CI run** where you downloaded the
`vh-map02-bizhawk211-experimental-core-witness` artifact. Do **not**
use a hash calculated solely from an untrusted download as its own
trusted comparison.

Extract the DLL from the Actions artifact into a temporary, private
folder outside Git. Run from the project checkout in Windows
PowerShell 5.1; only the following explicit `-Install` switch writes:

```powershell
$bizhawk = 'C:\\ExamplePrivate\\BizHawk-2.11'
$sourceDll = 'C:\\ExamplePrivate\\Staging\\VhMap02CoreWitness.dll'
$expectedDllSha256 = '<64-hex-digit-SHA256-from-the-matching-CI-run>'
$installer = '.\\tools\\map02_owner_core_witness_install.ps1'
$installArgs = @(
  '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
  '-File', $installer,
  '-BizHawkRoot', $bizhawk,
  '-SourceDll', $sourceDll,
  '-ExpectedDllSha256', $expectedDllSha256
)

# Preflight without creating any files.
powershell.exe @installArgs
# Explicit, first-time-only installation. Existing plugins are never replaced.
powershell.exe @installArgs -Install
```

The installer checks the file's .NET assembly name, filename and
bounded size, absolute non-reparse local paths outside Git, expected
BizHawk assembly layout, and the caller-supplied SHA-256. It installs
using exclusive `FileMode.CreateNew` and rechecks both source and copied
DLL hashes before reporting a **fixed, redacted** success marker. It
refuses existing `ExternalTools/VhMap02CoreWitness.dll` even when
identical. It never overwrites the existing emulator, DLLs, BIOS,
configuration, game or captured images. Default mode is read-only.

This is a **local component preparation**, not a real PS1 startup or
authentication of the loaded original disc. After installation, proceed
with the separate owner-private directory preparation in Stage515 and
the Stage512 non-launching preflight before any explicit
`--launch-one`. The owner-local Octoshock/BK2/BIOS capture itself remains
unverified until run with the owner's original private files.

## Stage517 — pin the *installed* DLL through the first real capture

Stage516 established a **known compiled** experimental DLL and checked it
at installation. A DLL can still be accidentally replaced later, without
changing its installed filename. Stage517 adds the opt-in
`--private-core-witness-sha256` flag to both owner-local capture launchers.
It rereads the installed DLL at preflight, immediately before the child
EmuHawk launch and after process return, and again around PNG/capture
auditing. Both the coordinator and its child enforce the same independent
expected SHA-256. If the file changes at any of these checkpoints, the
owner process fails closed without accepting the evidence.

For the exact experimental DLL built in the successful **Stage516**
[BizHawk 2.11 CI run #39822878309](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39822878309),
the observed **DLL file** SHA-256 was:

```text
BA44578D78135CF32DEAAB7C21A76E299567488510FDF34C002C0161C1C8B8B5
```

This pin belongs to the *unpacked DLL*, not the ZIP archive containing it,
and is **not** the game's disc hash. If using an artifact from any other
CI run, get the DLL digest printed by **that exact trusted successful
run**, not from an unknown file or an unrelated artifact.

For the first-owner run, augment the Stage512 `$common` array:

```powershell
$knownDllSha256 = 'BA44578D78135CF32DEAAB7C21A76E299567488510FDF34C002C0161C1C8B8B5'
$common += @('--private-core-witness-sha256', $knownDllSha256)

# No game launched and no new files created on this first invocation.
python -m tools.map02_private_two_replay_runner @common

# Use this ONLY when all private source, movie, BIOS and output checks pass.
python -m tools.map02_private_two_replay_runner @common --launch-one
```

If you downloaded the **exact** Stage516 CI artifact and installed it
under the official BizHawk 2.11 `ExternalTools` folder without modification,
the pin should match. If the DLL differs, **do not** disable the check or
invent a new expected hash to force success; verify the provenance of the
installed DLL or replace it through a fresh, separately verified installation
outside any existing capture workspace.

This is a check on the local experimental C# tool file and its stability,
not cryptographic attestation of the emulator process or its loaded modules.
In particular it does **not** authenticate a mounted CUE/BIN, BIOS,
BK2 controller delivery, original MAP02 scene, a second cold boot or
Nintendo Switch gameplay. Original game files and local screenshots must
remain on the owner's private workstation.


## Stage518 — compare the witness's executing-tool file hash to the pin

Stage518 adds a tool_assembly_sha256 field to the private runtime receipt (V2 schema).
The external tool computes SHA-256 for the file at its own executing assembly
location. When --private-core-witness-sha256 is supplied, the launcher passes
that exact pin to the child EmuHawk process through a dedicated environment
variable. Before writing an automatic witness, the tool checks its observed
file hash against the pin; after capture, the Python verifier also requires
the receipt's digest field to match the same expected value. Malformed,
missing, or mismatching digest evidence fails closed.

The raw tool digest remains local: it is not copied into public JSON reports,
logs, GitHub artifacts, or screenshots. The existing Stage517 checks still
re-hash the installed DLL before and after launch and audit checkpoints.

**Evidence limit:** this is an additional in-process self-check of the file at
the executing assembly's reported location. It is **not** independent OS
attestation of the loaded module's in-memory bytes; a malicious or modified
assembly could falsify its own receipt. A passing result therefore means the
self-reported file hash matches the externally pinned DLL digest, not that
the CLR's loaded module has been cryptographically authenticated. It also
does not authenticate the original disc, BIOS, movie synchronization, MAP02
scene, or Nintendo Switch gameplay.
