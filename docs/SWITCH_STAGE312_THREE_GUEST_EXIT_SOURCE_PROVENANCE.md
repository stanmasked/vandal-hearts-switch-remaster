# Vandal Hearts Remake — Stage312: three original guest software exits with explicit source provenance

## Verified starting point

- **Stage307**: guest software recorded Plus observed, audio mailbox stop,
  audio-worker cleanup, `audout` close, and thread join.
- **Stage308**: a CRC-validated guest framebuffer optical source showed the
  musical-scene guest events preceded guest-observed Plus.
- **Stage309**: separately replayed two original optical NeXium captures;
  guest-observed Plus → worker join was approximately 27.979 ms and
  31.657 ms. Those older captures stored *capture-time validated JSON*
  guest-exit receipts but did not archive the raw guest-created CSV.
- **Stage310**: the original third NeXium capture
  [39141325435](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39141325435)
  succeeded, preserving exact original `audio-exit-timeline-000.csv` guest
  SD bytes and checking their SHA-256 against guest and optical receipts.
- **Stage311**: a completely separate GitHub Actions workflow
  [39142041977](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39142041977)
  successfully re-read that archived CSV byte-for-byte. It also regenerated
  and exactly matched the Stage307, Stage308 and Stage310 reports,
  including original guest software events and CRC-protected optical
  musical-scene image. All 13 adversarial Stage311 tests passed.

## Stage312 design

`tools/audit_nexium_guest_exit_three_run_cohort.py` compares three
independently captured original NeXium artifacts:

1. 39137949186 — old original optical PNG and source-audited guest exit JSON;
   raw exit CSV **not retained**.
2. 39138826525 — separate original optical PNG and source-audited guest exit
   JSON; raw exit CSV **not retained**.
3. 39141325435 — original optical PNG **and raw guest-created exit CSV bytes**,
   already independently re-audited with Stage311.

It rejects duplicate original optical PNGs, reused guest-exit source
SHA-256s, tampered host vs guest-clock scope claims, wrong guest milestone
intervals, false raw-original claims for earlier captures, a mismatched
Stage311 independent receipt, and attempts to substitute only a JSON
summary for the third original guest-created file.

The result explicitly distinguishes the two legacy
`capture_time_source_audited_JSON_only_runs` from
`original_csv_byte_verified_runs`. No fake uniform confidence tier is
assigned.

For each guest software shutdown interval, the report includes each
run's duration, minimum, median and maximum across all three. These
are guest software monotonic **time intervals only**, not a combined
host-to-guest clock fit, DAC service latency or audible speaker output.

## Workflow and output

`.github/workflows/stage312-three-guest-exit-provenance.yml`
fetches all three original NeXium artifacts and the **separate**
Stage311 original-byte independent receipt. It replays every original
optical framebuffer with its payload CRC, the Stage307 observed guest
exit source receipts, and the exact third-run original guest CSV bytes
and Stage310/311 provenance chain.

Output: `independent-stage312-evidence/three-guest-exit-provenance-stage312.json`.

12 synthetic adversarial tests:
`python3 -m unittest discover -s tests -p 'test_audit_nexium_guest_exit_three_run_cohort.py' -v`.
The Host SPU workflow also runs them with its isolated Pillow environment.

No original PS1 retail soundtrack, music data, voice bank, SPU synthesis,
audout page scheduling, NRO runtime logic or original customer game assets
are changed by this stage.

## Evidence limits

An authentic guest exit CSV timestamps **software code sites**. It does
not locate the actual last audible sample on the Switch speakers, prove
that Plus is the cause of zero-valued PCM, or establish a synchronized
host PulseAudio and guest monotonic clock conversion. It is correct
to preserve those limits even when all three source timelines agree.
