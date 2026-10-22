# MAP02 Stage507 — owner-local paired Octoshock/PNG acceptance

## Scope

This **read-only** gate is intended to run **after** the two private
EmuHawk capture attempts from Stage506. It is not an emulator launcher,
not a replacement for visual MAP02 review and not a method to put
commercial game material in GitHub Actions.

It *re-runs* the private BK2/plan/Lua/PNG audit instead of believing a
previously saved JSON report; it also reads each launch's private OS
process-start receipt and the manual External Tool witness exported
inside that same live EmuHawk process. The strict witness parser requires
`system=PSX`, `loaded_core=Octoshock` and no invented BIOS/disc/movie
verification. Each PID **and** Windows process creation time must agree.
Both sessions must report separate process identities.

The PNG auditor independently checks the observed timeline, read-only
movie, fallback-disabled preference and byte/decoded-pixel comparisons.
A decoded mismatch or unsupported format returns exit status **2**;
missing/inconsistent/stale evidence fails **closed**. Status **0** means
only that the supplied local logs/receipts passed these limited checks.

## Prerequisites

1. Keep the retail CUE/BIN, PSX BIOS, BK2, PNGs, private text receipts,
   any identity/hashes and screenshots **outside Git** and private.
2. Use the existing two-runner **on the owner's Windows PC**, with
   `--record-windows-process-identity --launch-two`, only after
   successful local preflight and confirmation that BizHawk's PSX
   fallback is disabled.
3. While **each corresponding EmuHawk process is still alive and the
   actual PSX/Octoshock core is loaded**, manually save one witness
   through the C# External Tool, into an owner-only, non-Git folder.
   Do not reuse an older witness. If the emulator exits before the
   witness can be saved, the attempt **cannot** satisfy this gate.
4. Stage508 integrates the strict Windows owner-only NTFS checks from
   sibling PR #490 with Stage506 process binding and Stage507 PNG review.
   Restricted Windows folder ACLs are mandatory at workspace, capture
   and manual core-witness output locations. The verifier refuses
   public/shared Windows directories; it does not change ACLs.

## Local command (illustrative paths only)

From the project checkout with an owner-private capture workspace:

```text
python -m tools.map02_private_paired_capture_core_png_gate \
  C:\\Private\\vandalhearts.bk2 \
  C:\\Private\\review\\vh-map02-review-plan.txt \
  C:\\Private\\review \
  C:\\Private\\witness-for-cold-01.txt \
  C:\\Private\\witness-for-cold-02.txt
```

The workspace must contain exactly named run folders
`vh-map02-cold-01` and `vh-map02-cold-02`, each with its launch receipt
`vh_emuhawk_process_identity.txt`, capture log and planned PNGs.
The real C# External Tool generates random witness filenames; pass the
actual **private** witness paths in the same order as the runs.

**Never paste a command with real private paths into public CI, a PR
comment, a support ticket or this chat.** The tool prints only a
redacted JSON with counts/booleans. The CLI and tests intentionally
avoid showing private paths even on a failure.

## Claim boundaries

The two launch receipts and manual witness files are editable text:
matching them does not cryptographically prove their source or that
the witness was captured at the same instant as a particular PNG.
The original USA BK2 might also be incompatible with the owner's
RU 1.6 disc. Neither the running BIOS, mounted BIN/CUE, actual
controller delivery, cold-boot origin, MAP02 scene identity nor
Switch/PC rendering fidelity is independently authenticated by this
gate. Human inspection of original local PNGs and genuine runtime
capture are still required.

Public CI uses **17 entirely fictional acceptance cases** (including
swapped, stale, duplicated, missing or unsupported records) on three
Python runners. It never opens commercial image files, starts a PSX
emulator or claims to have captured a Vandal Hearts frame.

## Stage509 — explicit automatic process-bound core-only witness

On the owner's Windows machine, the optional `--auto-core-witness-plugin`
flag accepts an **already installed** `VhMap02CoreWitness.dll` from the
matching EmuHawk 2.11 installation's `ExternalTools` directory. It is
opt-in and requires `--record-windows-process-identity`. Without this flag,
the plugin does not automatically write anything, and the existing manual
procedure remains available.

Use this **illustrative** command shape (do not copy personal paths into
GitHub issues, logs or chat):

```text
python -m tools.map02_private_two_replay_runner \
  C:\\Private\\BizHawk-2.11\\EmuHawk.exe \
  C:\\Private\\Game\\Vandal_Hearts.cue \
  C:\\Private\\Game\\vandalhearts.bk2 \
  C:\\Private\\review \
  --record-windows-process-identity \
  --auto-core-witness-plugin C:\\Private\\BizHawk-2.11\\ExternalTools\\VhMap02CoreWitness.dll
```

The command above is **dry run only**: it never starts an emulator or
creates screenshots. After a successful owner-local dry run and confirmation
of all original media requirements, add `--launch-two` to explicitly run
two separate local EmuHawk processes. The child appends official
`--open-ext-tool-dll=VhMap02CoreWitness.dll`, forwards the intended output
directory using a child-only environment variable, and still enforces the
existing exclusive private-file, NTFS and launcher safety checks.

On each `Restart()` with the **injected current** PSX/Octoshock
`IEmulator`, the C# tool makes **one attempt only** to create
`vh-map02-runtime-core-auto.txt` in that individual run folder, using
`CreateNew` and a verified owner-only NTFS DACL. It never overwrites
a prior witness. An unavailable/rejected/late export is a failed run:
the launcher rejects a zero exit when the PSX receipt is missing or its
PID/birth time differs from the launch receipt. The parent additionally
requires both distinct process identities and matching per-run core files.

No manual witness filename is needed to rerun the **offline** combined
core+PNG review in automatic mode:

```text
python -m tools.map02_private_paired_capture_core_png_gate \
  C:\\Private\\Game\\vandalhearts.bk2 \
  C:\\Private\\review\\vh-map02-review-plan.txt \
  C:\\Private\\review
```

The auditor detects `vh-map02-runtime-core-auto.txt` in each
`vh-map02-cold-0N` directory only when **both** manually specified
witness arguments are omitted. Passing one manual witness alone is
rejected. It still checks original BK2/plan, Lua logs and RGB PNGs
independently. In all cases the returned JSON contains no owner paths,
process identifiers, game hashes, ROM bytes or image pixels.

**Important:** This code is validated against a *synthetic fake*
`IEmulator` and a **no-game** real NullHawk; it has **not** proven
that the genuine owner's PSX/Octoshock load invokes `Restart()` before
the capture's Lua exit. A matching editable text file attests neither
correct BIOS nor mounted CUE/BIN, actual BK2 controller delivery, original
MAP02 scene, real cold boot nor Switch renderer parity. The owner must
run and examine authentic screenshots locally. Do not publish them.

## Stage510 — pre-first-PNG receipt gate

When Stage509 automatic mode is enabled, the exact Lua script that calls
`client.screenshot()` must first see a small, schema-checked, owner-private
`vh-map02-runtime-core-auto.txt` file in that same output folder. The
receipt must explicitly report `system=PSX`, `loaded_core=Octoshock`
and `bios=unverified`, `disc=unverified`,
`movie_sync=unverified`. If absent, malformed, over 512 bytes, or stored
under a different folder selected by the child environment, the Lua
capture fails with a redacted diagnostic **before writing the first PNG**.
It checks the exact receipt bytes again before each later screenshot
and rejects changes during the capture.

Only successful owner-opted-in mode emits the fixed redacted
`VH_PRIVATE_NEUTRAL_AUTOWITNESS_PREFLIGHT` marker **before** the first
`VH_PRIVATE_NEUTRAL_CAPTURE` marker. The independent Python parser
validates the order and the combined two-run audit requires this
observation on **both** runs before it will treat automatic witness
mode as accepted. Manual mode does not require an auto witness and
cannot accidentally acquire this claim.

This temporal ordering is based on editable local files and Lua logs,
not a trusted timestamp or cryptographic attestation. The Python owner
launcher independently requires both receipts to match the recorded
EmuHawk Windows PID and creation-time identities; even together the
tests do **not** establish which original PS1 disc or BIOS was loaded,
that the BK2 controller stream reached the emulated game, or that any
pixel belongs to MAP02. The public CI uses fictional Lua/PNG/PSX mocks,
never commercial assets or original gameplay.

## Stage511 — witness frame-clock consistency with the first PNG

The automatic PSX/Octoshock receipt includes C#'s `IEmulator.Frame`.
Stage511 requires this claim to be **no later than** the Lua
`emu.framecount()` sampled at each image capture. Thus an owner-local
auto receipt claiming a **future emulated frame** can no longer satisfy
the Lua pre-first-PNG gate, even if its system/core name is syntactically
correct. Equality is deliberately accepted: the two public BizHawk API
values can legitimately name the same current frame.

Independently, the paired capture auditor calculates the exact counter
of the **first planned screenshot** from the private BK2-derived capture
plan. The combined process/core/PNG auditor then reads both complete
canonical auto core receipts and requires each `frame_count` to be no
greater than that counter. The PNG-audit report adds only that first
frame count, not media identifiers, absolute paths, PID, birth-time
ticks, hashes or pixel bytes.

This is a **logical consistency** check of two editable owner-local
sources, not a trusted wall-clock timestamp and not proof that the
Octoshock emulator actually loaded the correct disc/BIOS or reached
MAP02. Manual witness mode remains unchanged, as a manually exported
witness may legitimately be saved after the screenshots.

The pre-existing Intel macOS group-termination failure on Stage509's
first CI attempt did not recur on the targeted rerun: all three
launcher jobs then succeeded without changing process-kill behavior.
A future recurrence should be investigated independently rather than
silently ignoring POSIX process-cleanup errors.
