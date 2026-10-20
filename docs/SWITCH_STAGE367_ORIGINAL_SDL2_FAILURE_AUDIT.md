# Stage367 — independently audit Stage366 original SDL2 HTTP 403 artifact

## Real original evidence

The [original Stage366 SDL2 workflow #39384172009](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39384172009)
kept its SDL2 job **failed** during package installation, as required.
The job ID was `118499937561`: the devkitPro mirror returned HTTP 403,
compilation and NRO upload were skipped, but the two diagnostic files
were uploaded by the new `if: always()` step.

The [preserved artifact #12246243370](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39384172009/artifacts/12246243370)
contains `stage366-sdl2-install.log` and
`stage366-sdl2-diagnostic.txt`. The GitHub artifact metadata
reports 905 ZIP bytes and the digest
`sha256:3a1565e7b9b7e125dcb83e58a7a332b23c06fc454bd0b0f28ac9b165a046a676`.

## Independent audit procedure

The Stage367 workflow fetches original artifact metadata and original
job steps from the GitHub API, downloads only the named original
artifact from run `39384172009`, and checks the extracted files.
Its verifier demands the exact pinned artifact ID, GitHub-reported
digest, original run and commit `f9a4354a9c98a29ff2676b2325c926587d2b897a`.
It insists the original install step **failed**, evidence upload
**succeeded**, and compilation and SDL2 NRO upload were **skipped**.
The source files must be exactly the two expected names, not links,
duplicates, empty or oversized data. The raw log must contain the
actual HTTP 403 and failed package-database synchronization. The
original classifier must still deny SDL2 compilation and hardware
testing. SHA-256 hashes of both decoded source files are recorded in
the independent verdict.

The separate synthetic negative tests reject metadata substitutions,
wrong source run/head commit, false green job statuses, missing or
linked files, altered raw logs and falsified classifier results.

**Scope:** GitHub-reported ZIP digest binds to the artifact metadata;
the report hashes independently read file contents. This is an audit
of an **external dependency failure**, not remediation of the devkitPro
mirror, and it cannot verify SDL2 music compilation, audibility on
physical Nintendo Switch, or explain the historical `0xEA01` wait.

**Stage367 confirmed:** the independent real-archive [GitHub Actions #39385583138](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39385583138) passed all **6/6** negative-control tests and reaudited the actual failed original installer job and both preserved files. The independent verifier returned `STAGE367_ORIGINAL_SDL2_HTTP403_EVIDENCE_REAUDITED_CI_STILL_FAILED`. The resulting JSON audit is retained as [artifact #12246514516](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39385583138/artifacts/12246514516). This confirms the authenticity and retention of the external failure, not successful SDL2 compilation.
