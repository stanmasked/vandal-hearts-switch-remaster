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
