# Vandal Hearts Remake — Stage310: preserve actual guest exit CSV bytes

Stage309 compared two separate, source-verified NeXium software exit
records and their actual original CRC-verified guest optical PNGs.
Both runs had distinct guest CSV SHA-256 hashes and orderly guest
software exit milestones; guest Plus observation → worker join was
27.979 ms versus 31.657 ms. These are guest software durations, NOT
audible audio-stop times.

Stage309 exposed a specific provenance limitation: older NeXium
artifacts contained the *capture-time-audited guest CSV JSON receipt*
but did not preserve the source **guest-created CSV file bytes** in
the runtime artifact. Stage309 therefore correctly reported
`all_original_guest_csv_bytes_reaudited: false`.

## Stage310 implementation

`tools/preserve_nexium_guest_exit_original.py` runs on the same NeXium
runner after the Stage307 original guest SD parser and Stage308
CRC-verified optical guest scene/exit audit.

It uses the **original isolated guest SD mount root**, not a newly
reconstructed CSV. For the single original file
`sdmc/switch/vandal-hearts-remake/audio-exit-timeline-000.csv`, it
performs the following independently and in order:

1. Re-read the original guest SD root and require the newly parsed
   complete Stage307 receipt to match the existing audited report.
2. Re-decode the same real guest framebuffer screenshot with CRC32;
   require the Stage308 report to reproduce exactly.
3. Read the original guest exit CSV bytes, validate canonical ordered
   guest software timestamps, check the source SHA-256 against the
   Stage307 and Stage308 witnesses.
4. Copy **unchanged original bytes** exclusively into
   `runtime-evidence/audio-exit-timeline-000.csv`, refusing to replace
   any existing file, and read the copy back byte-for-byte.
5. Write a separate machine-readable provenance receipt
   `runtime-evidence/guest-original-exit-source-stage310.json`.

If NeXium does not expose the guest SD original, the tool records
`ORIGINAL_GUEST_EXIT_SD_NOT_OBSERVED` without producing a CSV. The
current NeXium workflow requires a real source capture to pass Stage310,
rather than pretending a report is the original file.

The existing workflow uploads the `runtime-evidence/` directory.
This now includes the actual source guest-exit CSV containing five
diagnostic monotonic timestamps; it includes **no commercial game
audio or retail PS1 resources**.

## Tests

`tests/test_preserve_nexium_guest_exit_original.py`: ten synthetic
source integrity cases, including exact byte round trip, refusal to
overwrite, altered original CSV, changed Stage307/308 receipts,
swapped optical PNG, symlink, extra numbered CSV, and explicit absence.

Host SPU CI uses the same isolated Pillow environment as Stage308.
The NeXium workflow validates the preserved original file SHA-256,
size, and no claims of guest/host clock mapping or audible sound.

## Limits

Raw exit timestamps are **guest software measurements**. Even a
byte-exact, SHA-verified guest CSV is not aligned with buffered host
PulseAudio PCM frames or a physical DAC clock. It does not prove
soundtrack fidelity, speaker playback, or an audible audio fault.
No sound generation, audio queue, or gameplay shutdown semantics
are changed.
