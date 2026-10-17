# Switch Stage 270 — Same-NRO NeXium audout repeatability

**Hardware status: HARDWARE NOT TESTED. No speaker/DAC measurements.**

## Established baseline

Two separate successful NeXium workflow runs use the **exact same NRO byte hash**
\`60dc486339331de6c5d24f6e2b049c8ba24ee095a8534746af9f42d18a8a1b91\`.
Their Git commits differ because of tests and CI infrastructure; the NRO bytes
themselves did not differ. Each run passed full NRO build, same-run SHA-256
manifest verification, real optical scene/SD/PCM evidence, and the strict guest
audout CSV / export-receipt checker:

| Observation | Run 39065603152 | Run 39065671551 |
| --- | ---: | ---: |
| Guest original / copy CSV size | 2,065 bytes | 2,065 bytes |
| Full host PCM duration | 60.903 s | 60.718 s |
| Guest scene events | 53 | 53 |
| Guest audout one-second windows | 53 | 53 |
| Audout submit / exact-release attempts | 1,930 / 1,930 | 1,925 / 1,925 |
| Failed attempts | 0 | 0 |
| Queue service probes accepted | 121 | 121 |
| Queue probe errors | 0 | 0 |
| Max blocking \`audoutPlayBuffer\` call | 49,765 μs | 51,692 μs |
| Window eviction / guest clock anomalies | 0 / 0 | 0 / 0 |
| Copy CSV SHA-256 | \`60e9c366bf93970c848f3bd65895cb92a800088530f5f34790ff8d7bdb42e1c6\` | \`cf4a06fa94051b04dc20b7cfc4570c52a4e8fc14948c05a45ba3eba55e5b4748\` |

Original GitHub Actions:
- [39065603152](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39065603152)
- [39065671551](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39065671551)

The attempt count changed by **5 attempts across 53 guest-second windows**,
about **0.26%** of the smaller count. The measured maximum blocking call varied
by 1,927 μs (1.927 ms). Neither difference determines audible quality, real
queue starvation, nor Switch hardware latency. All queue count probes were
**pre-submit** observations, not continuous DAC occupancy.

## Reproducible cross-run gate

Added \`tools/audit_nexium_audout_repeatability.py\`, reading at least two
separately captured **GitHub Actions evidence ZIP** files:

\`\`\`sh
python3 tools/audit_nexium_audout_repeatability.py \
  --artifact run-39065603152.zip \
  --artifact run-39065671551.zip \
  --output audout-repeatability-report.json
\`\`\`

Before producing a report, the comparator:

1. Rejects ZIP traversal, duplicate names, absent/oversized evidence, symlinks
   on evidence members, and duplicated JSON properties.
2. Requires each archive's same-workflow NRO manifest, ten-scene optical/SD
   report, guest audout verification, untouched copied audout CSV, and post-join
   success receipt.
3. Requires the scene audit's **actual NRO SHA-256** to match that workflow's
   NRO manifest. This deliberately excludes earlier reports with an old hardcoded
   \`guest_nro_sha256_pinned\` claim.
4. Independently reparses every CSV and checks reported sums, per-second
   accounting, SHA-256 and size. Checks the exact producer receipt and digest.
5. Requires different workflow run/attempt identities, **identical binary
   SHA-256**, at least 1,000 attempts per run, zero rejected audio attempts and
   zero overwritten/missing windows, clock faults or queue-query errors. A
   10% per-run submit-count spread limit is a **software diagnostic
   repeatability criterion**, not a hardware performance guarantee.

Regression tests include differing binaries, duplicate runs, altered ZIP/CSV,
false writer receipts, forged/duplicated JSON and excessive attempt spread.
The tests run through Host SPU regressions and the NRO smoke build workflow.

### Limits

These archives contain a copy of the original guest SD CSV plus earlier
successful guest-SD verification reports. The independent original guest SD
path from each finished GitHub runner **cannot be reopened now**. The new gate
therefore reports \`independent_original_sd_reopened: false\` rather than
fabricating a second original-source verification.

No test measures or proves actual speaker output, end-to-end latency, underrun
absence, physical Switch functionality, or long-term SD power-loss durability.
A successful cross-run comparison is software observation repeatability only.
