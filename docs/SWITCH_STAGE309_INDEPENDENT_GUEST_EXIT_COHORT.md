# Vandal Hearts Remake — Stage309: independent guest exit-software cohort

Stage307 introduced guest-monotonic timestamps for the software event
sites `plus_observed`, `stop_requested`, `worker_cleanup_entered`,
`audout_closed`, and `worker_joined`, without changing audio output.
The actual NeXium run [39137949186] succeeded and observed the
real guest exit CSV through the emulator's isolated SD mirror.

Stage308 [39138826525] independently confirmed CRC-verified guest
optical musical-scene events preceded the in-game observed Plus event,
in a **shared guest software** monotonic domain. No physical audio
playback, host/guest clock alignment or causality is inferred.

## Stage309 design

The standalone workflow
`.github/workflows/stage309-guest-exit-cohort.yml` downloads the
`nexium-runtime-evidence` archives from those two successful, distinct
GitHub Actions workflow runs. It independently re-decodes each **actual
archived original** NeXium optical framebuffer PNG, checks its CRC32,
all four musical-scene transitions and the observed guest software
exit events. Each pair of guest timestamps is checked in the same
guest clock only. It refuses duplicate run IDs, duplicated original
optical PNG hashes, re-used guest exit CSV source hashes, reversed
guest event sequence, forged duration fields or impossible source
claim flags.

Stage309 then independently computes the durations of:

- Guest Plus observation → audio stop request
- Audio stop request → worker cleanup entrance
- Worker cleanup → audout close
- Audout close → worker join
- Total observed Plus → completed join

It reports the minimum and maximum *guest software durations* across
the two captures, without forcing unrelated runs to agree or asserting
any physical audio performance threshold.

The archives may contain the Stage307 **capture-time validated JSON
receipt**, but not the original guest SD CSV bytes (which are in the
runner's isolated SD mirror). The tool explicitly records
`original_guest_csv_bytes_reverified: false` in that case, and
`all_original_guest_csv_bytes_reaudited: false` for the cohort.
It never falsely claims that a receipt hash is a fresh reread of the
original file. If future artifacts preserve the exact source CSV,
the tool validates its bytes, hash, event schema and timestamp
values against the original Stage307 receipt.

For Stage308 archives that include its original correlation JSON,
Stage309 also checks exact reproducibility of that report against
the preserved optical PNG.

## Outputs

- `independent-guest-exit-evidence/stage309-software-exit-cohort.json`
- CI workflow artifact `stage309-guest-software-exit-cohort`
- 11 adversarial synthetic tests, run using Pillow in an isolated venv

## Interpretation

These are guest **software teardown** timing measurements. Their
endpoints are not synchronized to the host buffered PCM file-size
snapshots, the virtual PulseAudio null sink, the audout hardware
queue or physical Switch DAC. Neither the original soundtrack nor a
human-audible dropout has been verified. No changes to synthesized
music or audout output behavior were made.
