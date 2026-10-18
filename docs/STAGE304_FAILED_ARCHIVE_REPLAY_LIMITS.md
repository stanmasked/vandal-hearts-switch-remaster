# Stage304 failure — original run vs downloaded archive

The original Stage322 NeXium workflow
[39157976877](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39157976877)
**failed** at the pre-existing Stage304 host Plus-control PCM evidence
step. The guest audout service behavior must **not** be diagnosed
from that failure alone.

The first read-only archived replay
[39160065284](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39160065284)
refused the source because a required pinned report was not an
existing regular file **in the downloaded artifact**. That message
does not establish that the same report was missing when the original
NeXium job executed: failed-workflow artifacts can be incomplete or
laid out differently from the live workspace. Treat the original
in-run cause as **not established**, not as proven audio failure,
host recording failure, game defect or user-input timing issue.

The revised read-only postmortem in
`.github/workflows/diagnose-stage304-original-archive.yml`:

- Enumerates the **exact 12 original Stage304 pinned input paths**
  inside the downloaded failed-run archive, recording existence
  and byte sizes, **not audio contents**.
- If any input is absent, reports `ARCHIVE_INCOMPLETE_NO_FULL_REPLAY`
  and does not pretend to reproduce the original in-run audit.
- If all sources exist, reruns the **unchanged strict Stage304 source
  checker**, records whether the archived replay passes or refuses,
  and explicitly distinguishes that outcome from the cause of the
  original workflow's failure.
- Publishes only a compact JSON availability/replay classification,
  never raw PCM, retail soundtrack, game data or keys.

This diagnostic does **not** change `audout`, SPU, game logic or the
Stage304 validation/acceptance rules.

A later original Stage322 NeXium run
[39159226320](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39159226320)
completed **successfully**, including Stage304 and the bounded normal
PlayBuffer history. Independent Stage323
[39159251998](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39159251998)
replayed the later **real original guest CSV bytes** and optical CRC
successfully. That later success does not retroactively change the
failed status of 39157976877.
