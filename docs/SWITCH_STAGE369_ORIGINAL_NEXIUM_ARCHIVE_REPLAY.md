# Stage369 — independently replay the *preserved* genuine Stage368 NeXium artifact

## Original observed result — strictly software-level

The complete [NeXium runtime workflow #39388027581](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39388027581)
returned **success**, and its genuine original Stage351, Stage357 and
Stage368 steps succeeded before the later runtime controls.
The exact guest console statements for that SAME original run were:

```text
Stage351 original software tail result: return_confirmed
Stage357 original guest wait Result bits: 0 Stage351 reason: 7
Stage368 real source-bound raw Result: 0 release count: 1 pointer matched: True
```

Original retained archive:
[GitHub Actions artifact #12249301260](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39388027581/artifacts/12249301260),
named `nexium-runtime-evidence`.

This **does not reproduce the older original `0xEA01` timeout**.
The old failed run lacks the Stage368 returned-descriptor field and
cannot be assigned a fabricated returned count or pointer status.
The successful NeXium case proves neither audible output nor a
physical Nintendo Switch test.

## Stage369 design

The independent [Stage369 workflow](../.github/workflows/stage369-original-nexium-archive-replay.yml)
uses GitHub's original run/job/artifact endpoints. It downloads that
archived artifact again, then reopens the **unmodified** Stage351,
Stage357 and Stage368 guest CSVs plus their individual receipts and
the original same-run NRO preflight JSON.

`tools/audit_stage369_original_nexium_archive.py` verifies:

- Original run ID, completed state, GitHub source commit, attempt,
  and repository identity; build job and source-attestation steps
  independently reported success by GitHub.
- Original archive name, ID, SHA-256 digest as reported by GitHub,
  head commit binding, non-expiration, and nonzero byte size.
- The same-run NRO SHA-256, manifest, source commit and run attempt.
- Exact original guest CSV order and schema; actual bytes hashed anew.
  Those three byte digests must agree with the preserved Stage351,
  Stage357, Stage368 receipts.
- Service Result, tail reason, descriptor count and pointer identity
  must agree with all three source files; no address is serialized.
- Invalid or substituted inputs fail closed, and no original evidence
  is rewritten, synthesized or silently selected from mixed runs.

The native/Python synthetic negative controls reject conflicting
source commits, run attempts, missing or duplicated job steps, forged
original results, altered CSV, fake archive metadata, illegal pointer
claims and old-kernel-cause overstatements. An independently emitted
Stage369 JSON verdict is uploaded only after all validations succeed.

A successful original Stage368 guest step is *not* itself independent
verification of preserved archive bytes. Stage369 must pass
[its own CI](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/workflows/stage369-original-nexium-archive-replay.yml)
before the archival replay is declared verified.

**Scope:** software result `0` with exactly one matching returned
descriptor. Queue depth at exit, the old kernel wait's exact subcall,
DAC timing, speaker sound and physical Switch hardware remain unknown.
