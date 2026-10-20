# Stage372 — independently re-audit two archived genuine Stage371 guest exits

The [completed Stage371 run #39396243731](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39396243731) saved two guest-originated, isolated source sets. The run completed successfully at **2026-10-20 09:40:48 UTC**. Its PR head was `8ccf7b4c`; the actual workflow checkout was the merge commit `7322cd89`, built against base `61143dcf`. One NRO digest `cfc49a8ac8dcfe4704e697c1bea8fc750ea32d498c2942176c2ca9b9cbcae71b` binds both trial receipts. The immutable original source artifact has ID **12255245917** and GitHub-reported ZIP digest `sha256:a8382e51c326e64e09f9ae7dedd238d5494b7c95bdb328fab534b2ed0d0e5f3c`.

## Independent CI scope

The [dedicated Stage372 workflow](../.github/workflows/stage372-original-stage371-pair-replay.yml) fetches the **finished** source run/jobs, merge-commit parents and artifact digest directly from GitHub. It downloads the original completed Stage371 artifact using `gh run download`, then a **different verifier** (`tools/audit_stage372_original_pair.py`) reopens both original three-file Stage351/357/368 CSVs, parses all canonical fields, and compares every file's SHA-256 against independently pinned digests. It also CRC-verifies all optical PNG chunks, checks the original source/NRO/attempt binding and both distinct isolated run tags. Optional software telemetry is preserved as opaque hashes, not interpreted as a live queue-depth measurement.

Previously observed guest results in the immutable artifact:

| Original guest | Exit dwell | `audoutWaitPlayFinish` software Result | Reported returned descriptors | PCM software acquired / released pages | Abandoned sessions |
|---|---:|---:|---:|---:|---:|
| a | 6 s | 0 | 1 | 2235 / 2235 | 0 |
| b | 12 s | 0 | 1 | 2672 / 2672 | 0 |

Six synthetic negative/positive tests include forged artifact provenance, failed original workflow steps, changed merge parents, altered original CSV/claims, duplicate files, missing/corrupted optical PNG, and changed NRO identity. The validator accepts only the original pinned cohort in its normal command-line mode; digest overrides are usable **only** by Python unit tests.

**Evidence boundary:** Stage372 does not create new guest runs, measure a direct audout queue at exit, decode optical pixels semantically, measure physical Nintendo Switch output, explain the earlier `0xEA01` failure or establish that the different dwell durations caused either result. A successful archival replay is separate from passing the newer Stage371 source changes on the current PR head. The workflow stores only a compact JSON verdict and uploads no raw game assets or PCM. No game audio, audio worker, libnx wait call or 12-ms bounded wait is changed.
