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
4. Verify owner-private NTFS folder permissions. PR #490 contains a
   stricter Windows NTFS ACL verifier, but is a **sibling** of the
   Stage506 process-binding PR #491. Until those branches are integrated,
   do not assume Stage507 includes that ACL enforcement.

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
