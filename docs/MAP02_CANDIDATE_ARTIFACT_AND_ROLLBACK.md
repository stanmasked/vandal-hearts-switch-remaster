# MAP02 — immutable NRO candidate and reversible integration plan

This is the **last artifact-identity gate** for the authored Nintendo Switch tactical prototype, stacked on [Draft PR #305](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/305). It is not a release of retail PlayStation Vandal Hearts content, and nothing is merged into `main` by this procedure.

## Why this stage exists

GCC, Clang, UBSan, the Switch NRO build and three genuine NeXium playback routes passed together on PR #305. Those runs all downloaded an artifact named `vandal-hearts-prototype.nro`, but its filename alone is not a cryptographic guarantee that every route used **exactly the same candidate bytes**. The new gate binds each job to an exact NRO digest and source commit/tree.

`tools/map02_candidate_receipt.py` records a small deterministic JSON receipt, for example:

```json
{
  "schema_version": 1,
  "kind": "map02-original-asset-free-homebrew",
  "filename": "vandal-hearts-prototype.nro",
  "size_bytes": 123456,
  "sha256": "<64 lowercase hex characters>",
  "source_commit": "<the exact 40-hex CI checkout commit>",
  "source_tree": "<the exact 40-hex CI Git tree>"
}
```

The number and hashes above are placeholders; CI records **actual measurements**. There are no private local paths, images, game keys, timestamps, passwords or retail ROM details in the receipt.

The real devkitPro/libnx build job checks out the PR **head SHA** explicitly, generates a receipt from the built nonempty regular NRO and verifies it immediately. The exact same NRO and receipt are uploaded as a single Actions artifact. Every subsequent real NeXium job (archer, medic and guard HUD) checks out that same head SHA and refuses to start unless the receipt's filename, byte count, SHA-256, source commit and Git tree all match. Each emulator evidence bundle includes a copy of the checked receipt. The script rejects symlinks, duplicate/missing JSON keys, unknown fields, malformed/uppercase digests, a zero-byte NRO, tampered bytes and mismatched source identifiers.

`tests/test_map02_candidate_receipt.py` runs adversarial tests on **synthetic byte strings**, not proprietary data. It explicitly tests one-byte changes with unchanged length, truncated artifacts, unrelated source commits/trees, symlink artifacts, duplicate JSON keys and wrong artifact types. The receipt detects accidental artifact mix-ups or corruption, **not a malicious CI builder**: it is not a signed software supply-chain attestation.

## Preconditions before *considering* integration

- All parent Draft PRs have reviewed, successful CI. The ancestry-repair commit `551e4dd4e5545e4e1bf91dca2b4791ab82609977` must remain a true descendant of PR #262, retaining the identical gameplay tree.
- Full combined GCC/Clang/UBSan and native Switch NRO build pass on the **current** candidate head.
- The real NeXium bow shot, medic restoration and guard-state HUD checks all pass using the **same SHA-256 receipt**.
- The four originally authored MAP02 fixture files still match the reviewed baseline. No original game image is committed or uploaded.
- Any branch-head movement invalidates older receipt/CI claims; rebuild and revalidate for the **new SHA**. A green result for a former head is not sufficient.
- The normal opt-in mode remains disabled unless explicitly selected; existing two-map gameplay remains accessible.

## Integration and rollback boundaries

**Do not automatically merge:** keep all stacked PRs Draft, leave `main` untouched, and do not force-push historical branches. The integration candidate is an isolated, reversible branch.

If a later reviewed default-branch integration is authorized:

1. Record the exact old `main` HEAD and the candidate SHA, retain GitHub Actions artifacts plus the candidate receipt.
2. Compare the final files and required checks again on the intended default-branch merge/squash commit. If that commit differs, rebuild; old NRO checks are not proof of new bytes.
3. Preserve the old `main` ref/tag outside the release branch. Integrate only through a reviewable PR with explicit approval.
4. On a failure before merging, simply close/abandon the isolated candidate PR: **no rollback on `main` is needed**.
5. On a failure *after* an approved merge, stop distribution, restore the previous known-good build and prepare a reviewed **revert PR** of the actual default-branch merge/squash commit(s). Do not blindly hard-reset or force-push `main`; merge parents and other concurrent changes must be reviewed.
6. Re-run hardware validation on the specific Intel Mac/real Nintendo Switch combination when available. A successful NeXium run is not a real-hardware test.

**No original retail PlayStation disc data, full game recreation or commercial release is claimed here.**
