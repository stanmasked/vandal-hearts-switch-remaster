# PS1 SEQ/VAB + native Switch graphics integration

This feature branch combines two previously separate, tested prototypes:
the libnx 1280x720 tactical-grid framebuffer and the native PS1-format
SEQ/VAB/SPU music pipeline. It is not yet the original playable game.

## Startup and content policy

The NRO attempts to load exactly three **user-owned** files from
`sdmc:/switch/vandal-hearts-remake/audio/`: `music.seq`, `music.vh`,
and `music.vb`. The complete file set is validated and decoded before
the sound worker starts. No copyrighted music is embedded in the binary
or GitHub. The files are neither uploaded nor modified.

The NRO checks whether libnx has already mounted `sdmc` and mounts it
itself only if necessary, without unmounting another subsystem's existing
mount. It unmounts its own mount after stopping the audio worker and releasing
all borrowed sample pointers. If the SD device cannot be mounted, it
**does not** treat inaccessible files as absent: audio is disabled and
the separate source indicator turns amber.

Only if SD access succeeds **and all three files are absent** does the NRO
use a generated SEQ/VAB/VAG fixture for asset-free CI. A partial or
malformed set fails closed, with red source and audio indicators;
it cannot silently substitute the fixture in place of owned data.

The main thread handles the gamepad, simple tactical demonstration and
framebuffer. A separate libnx thread generates 512 frames of 44.1kHz
SPU stereo PCM per music block, applies Gaussian interpolation and
the existing STUDIO_C reverb path, then resamples to 48kHz for `audout`.
Every call supplies at most 640 stereo output frames in a fully allocated
4KiB-aligned audio page. Music banks are released **after** the sound
thread is joined and the audio service is stopped.

## Display indicators and limitations

The upper-right green status means audout startup returned successfully
and no synchronous worker error has been recorded; red indicates failure
or device unavailability. Its separate source marker below it has
**four meanings**: green = user-owned SEQ/VH/VB accepted, gray =
mounted SD with no files (generated fixture), red = incomplete/invalid
file set, amber = SD could not be mounted. The screenshot validator
reports the actual observed marker and CI specifically requires the
gray synthetic source: inability to mount SD is not a passing audio
fixture test. No status indicator establishes that music is audible
or proves the original source files are authentic.

The animated blue heartbeat and tactical-grid marker support an
independent emulator screenshot check of ongoing framebuffer updates.
Audio timing, fidelity of VAB mappings, audible playback on physical
Switch hardware and integration with original Vandal Hearts gameplay
are not established by a successful synthetic CI run.

## Building and regression tests

From this feature branch, with devkitPro/libnx installed:

```sh
make test-audio-stream
make ps1-music-av-probe
```

The `native-ps1-music-av.yml` GitHub Actions workflow also runs a
UBSan-checked long-duration synthetic SEQ/SPU/reverb/resampler soak,
builds the NRO without SDL2/pacman downloads, and exercises the
framebuffer in NeXium. All CI tests use synthetic audio assets.
Full Switch functionality still requires local hardware validation.

## First NeXium run of the combined SEQ/VAB/SPU + framebuffer NRO

GitHub Actions [run #38865008839](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38865008839)
successfully compiled the new NRO and ran the SEQ/SPU/reverb/resampler
host regression and UBSan test. The separate NeXium runtime stage also
passed: the synthetic tactical grid and hero marker were observed;
**8,138 pixels changed** between the two frame samples, and
`audout_status` was `initialized`. The build artifact and raw NeXium
screenshots/log are retained in that CI run.

These results **do not** confirm audible music playback, correct
hardware sample timing, fidelity to the original game, or successful
loading of an actual user-owned `music.seq/music.vh/music.vb` set.
CI includes no proprietary audio files and exercises the synthetic
fixture only. A separate on-device recording is required for those claims.

## Synthetic guest-SD end-to-end cases

The integration workflow now uses a dedicated `NEXIUM_DATA_ROOT` for each
emulator run, matching NeXium's upstream `sdmc/` filesystem mapping.
The generator `tools/generate_ps1_music_sd_fixture.py` creates a tiny
**original-free** `pQES` sequence and `pBAV` bank in that isolated root.
Neither this generated sample nor any proprietary SEQ/VH/VB is committed
or included with the finished NRO artifact.

The three independent runtime cases are:

- `empty`: mounted SD with all three music files absent -> local
  built-in fixture chosen; green audout, gray source marker
- `full`: all three generated format-valid files -> SD file loader
  selected; green audout and green source marker (not original music)
- `partial`: only generated `music.seq` -> fail closed; red audout
  and red source marker, never silently substituted with fixture playback

Each case records two NeXium images, reports independently detected source
and audout status, and requires an animated framebuffer heartbeat.
The test asserts no observed content proves the identity of original
music or actual audible sound on a Nintendo Switch.
Host tests also ensure this CI fixture generator does not overwrite
existing audio files and rejects symlinked output directories.

## Additional guest audio processing progress gate

The runtime now shows a third independent rectangular status marker:

- Green: guest SEQ/SPU/resampler generated at least **16 stereo PCM blocks**
  and at least **16 calls to `audoutPlayBuffer` have returned**.
- Amber: audout started but there is not yet evidence of 16 completed
  PCM and audout-return iterations; a stalled audio output may remain here.
- Red: audio pipeline was not started or recorded an error.

Counts are atomic and updated by the audio worker, separate from the
main-thread framebuffer. The NeXium CI checks this third status for
all three synthetic SD variants, preventing an initialized-but-stalled
audio service from being counted as healthy playback. A green marker
proves **software audio buffer processing**, not audible audio through
speakers or parity with original PS1 timing.

## Transactional scene switching (host-tested, not wired into gameplay)

The native SEQ/SPU layer exposes
`vh_native_seq_switch_scene(&seq, next_seq, next_seq_size, &spu,
vh_native_vab_resolve, &next_bank, 0)`.

This routine validates the incoming SEQ before touching the current
sequencer or SPU. Invalid SEQ input leaves the current scene running,
with its existing PCM voice references and reverb intact. Successful
switching releases the old bank's voices, removes every old PCM pointer,
and retains the STUDIO_C delay/FIR history and configuration. The caller
owns the resampler, so its 44.1-to-48-kHz clock is not reset. A mismatched
SPU instance is rejected.

**Lifetime and thread requirements:** Load and validate the *next* VH/VB
bank and its decoded PCM storage before switching; retain its storage
until its voices have finished or been cleared. Perform the SEQ switch
only when the native audout worker is paused/joined or otherwise
synchronized, never concurrently with the DSP render callback. Any
already-submitted audout page must be handled separately; the SEQ
function does not resend, drain, or replay those pages.

The A/B/A/B synthetic bank regression exercises the successful and
invalid-SEQ paths, old-bank pointer removal, different-SPU rejection,
wet-tail preservation and uninterrupted resampling. All of these
are host-side tests. The combined NRO currently loads one bank and does
**not yet** invoke this transition API from the game's scene controller.

## Recovering failed native audout submissions

The standalone `audout-audio-probe` uses the portable
`vh_audio_output_submit_recover` transport helper. It renders and
resamples one stereo page **before** submitting it; a failed
`audoutPlayBuffer` cannot cause the helper to run SEQ/SPU or the
44.1-to-48-kHz resampler again. Recovery stops and recreates the
native audio service, then attempts to send exactly the same PCM page,
with a limit of two service restarts. A permanent error stops the probe
with a nonzero result rather than advancing music blindly.

The host `tests/test_vh_audio_output_recovery.c` fault-injects rejected
pages, exhausted retries, stop/open/start failures and HOME-resume
handling. It asserts stable SEQ note counts, SPU frame counts and
resampler phase during retries, and verifies the retried PCM pointer
and sample bytes are unchanged. The test is included in
`make test-audio-stream` and the PCM diagnostics workflow.

**Scope and limitations:** The recovery helper is now wired into both
the standalone native audout probe and the combined graphics/audio
NeXium/NRO audio worker. The combined worker starts its service before
launching the music thread; its retries occur exclusively in that
thread; and the main thread waits for it to exit before final teardown
and unloading user-owned PCM banks. A recovered submit increments the
completed-buffer counter once, not once per failed attempt.

A failed device call may have produced an *ambiguous* amount of audible
output before the failure; restarting audout may therefore truncate
sound or produce a discontinuity. The host tests guarantee software
clock preservation, **not** glitch-free or exactly-once sound on
Nintendo Switch hardware. Real Switch audio capture remains necessary.

## Synthetic music-scene transitions in the combined NRO

With a complete SD music bank, the combined NRO leaves the user-owned
`music.seq/.vh/.vb` playing and does **not** cycle cues. With **no** music
files present on a mounted SD, the fixture-only audio worker alternates
two generated pQES songs every **64 successfully submitted 512-frame**
SPU blocks. The transition uses `vh_native_seq_switch_scene` on the
audio-owning thread; it validates the next SEQ, clears old voice PCM
references and preserves STUDIO_C reverb. The independent 44.1→48-kHz
resampler is not reset. Both fixture songs resolve into the same
generated VAB; neither contains original game music.

A fourth framebuffer indicator at x=1000, y=325 changes from amber to
green once **two** fixture scene transitions have each produced and
successfully returned their first PCM page from audout. It is neutral
gray for user-owned music and invalid/partial sources. The synthetic
guest-SD NeXium run checks this indicator in addition to previously
verified music-source identity, audio-buffer processing and animated
framebuffer. This establishes **software switching progress only**,
not correct audibility or the original game's music cue rules.

## EON wet/dry differential and resampling-phase investigation

The synthetic 16-scene A/B bank test `tests/test_vh_native_bank_switch.c`
uses a VAB tone with `VagAtr.mode` bit 2 **unset**. Thus, although
STUDIO_C remains enabled, it receives no voice send and cannot explain
the late increasing PCM seam in that specific test. Its baseline dry
max across 15 transitions is **1367 PCM16**.

A separate host regression, `tests/test_vh_native_bank_switch_reverb.c`,
sets `VagAtr.mode` bit 2 and runs matched **wet STUDIO_C** and
**fully dry** SEQ/SPU/resampler paths through the same 16 synthetic
scenes. On the recorded CI run, **280,621 stereo sample values**
differed between these outputs; the peak 48-kHz adjacent-sample
changes were **1269 PCM16 wet** versus **1367 dry**. Reverb can alter
individual seams in either direction, but a wet tail is **not needed**
to reproduce the rising dry 48-kHz seam values.

Tracing the source *before resampling* isolates the pattern:

| Source and output | A→B seams | B→A seams |
| --- | --- | --- |
| Dry SPU at 44,100 Hz | 194 (repeats) | 2429 (repeats) |
| Dry output at 48,000 Hz | 112, 125, 139, 152, 165, 179, 14, 27 | 365, 532, 699, 866, 1033, 1200, 1367 |
| EON wet output at 48,000 Hz | 109, 210, 187, 191, 205, 227, 104, 110 | 523, 585, 649, 792, 950, 1109, 1269 |

The identical alternating 44.1-kHz source discontinuities and
changing 48-kHz seam values correspond to a **changing fractional
resampler boundary position** (the test logs this position for each
scene). This explains the measured synthetic pattern without
requiring a random DSP discontinuity or lost PCM clock. It does
**not** prove that an audible click is absent, nor that the actual
PlayStation original makes the same transitions.

The differential regression asserts that the source-level A→B and
B→A magnitude bands remain separate, that wet seams stay within the
measured synthetic safety envelope, that the dry/wet outputs differ,
and that continuous resampler clocks are identical. ASan/UBSan and
repeated-execution comparisons run in PCM WAV diagnostics.

**Decision:** Do not add automatic crossfades or modify reverb merely
to suppress these diagnostic numbers. Future work needs a genuine
user-supplied SEQ/VH/VB comparison and capture on a physical Switch
before selecting a perceptual artifact fix.

## Local-only two-bank transition audit for user-owned music

Build and exercise the host utility with generated, copyright-free
fixtures:

```sh
make test-local-music-transition
```

For locally owned SEQ/VH/VB resources, place each complete three-file
set in a separate **private directory**, using exactly these names:
`music.seq`, `music.vh`, and `music.vb`. Then run, locally:

```sh
make build/vh_local_music_transition_probe
./build/vh_local_music_transition_probe \
  /private/music/bank_A /private/music/bank_B 16 16 \
  > /private/music/transition-audit.json
```

The optional final arguments are the **number of scenes** (2–32;
default 4) and **512-frame blocks per scene** (1–4096; default 16).
The engine reads both banks with the same strict all-or-nothing
`vh_audio_assets_load` logic used by the Switch probe, validates each
SEQ, alternates A/B on the audio owner, clears borrowed voices at each
transition, and preserves the STUDIO_C work buffer and resampler clock.

The stdout JSON is **metrics only**: per-scene dispatched events,
successfully started notes, note-resolution requests, missing or
unresolvable requests, fallback notes, directly matched notes,
per-note reverb sends, whether any active voice sent to reverb,
raw 44.1-kHz and output 48-kHz boundary deltas, resampler fraction,
and frame counts. The counters are collected by a wrapper around the
unchanged production VAB resolver. Here **fallback** means the resolver
used a tone outside the requested program/key range: either a different
program or the nearest available key range. This is not necessarily an
audio defect, but can indicate a mismatch between SEQ and VH/VB. The
original resolver tries a global or nearest-tone fallback, so a bank
with missing intended notes can have `unresolved_notes = 0` while
`fallback_notes` is elevated. With a validated VAB containing playable
tones, the resolver's global/nearest-tone fallback will generally
resolve every valid request: `unresolved_notes = 0` does **not** mean
the intended instrument was selected.

The local report also distinguishes notes that resolved with zero
left/right gain (`zero_gain_notes`) from scenes that actually rendered
silent output (`silent_pcm`, `nonzero_samples`, `peak_pcm16`,
`clipped_samples`). In addition, per-channel `mean_pcm16_left/right`
measures the sample-average (DC offset) and
`rms_pcm16_left/right` measures the root-mean-square level. These are
**post-resampler 48-kHz** measurements in PCM16 sample units, not dBFS.
The measurements use all samples in each scene's specified 512-frame
audit blocks. RMS and means do not identify the original musical
instrument or guarantee that the physical Switch output is audible.
A zero-gain scene may still have nonzero PCM because the prior scene's
STUDIO_C reverb tail survives the transition. This identifies silence
within the limited audit window, **not** across an entire song.

The synthetic CI checks that malformed SEQ/VH/VB files are rejected
before playback. It covers 13 malformed resource variants in either
A or B (26 rejection scenarios), including damaged headers, missing
end-of-track, invalid tone/key ranges and invalid ADPCM headers.
Every rejection must produce no partial JSON, must not include the
private input path in stderr, and must leave the other bank unchanged.
Those tests do **not** imply all possible corrupt input is covered.

No PCM frames, original bytes, track names, file paths, or bank
contents are serialized. The program opens files
read-only and does not create or overwrite audio files. The output
report is created **only** if the operator explicitly redirects
stdout (as illustrated above), and should stay private if its
measurements might identify the music set.

The command is intentionally offline: **do not upload or commit**
the music directories or any original game audio. CI only invokes it
against our independently generated synthetic test banks and checks
malformed/missing resources, determinism, clock continuity, and
ASan/UBSan. The report does **not** certify physical Switch audibility,
original PS1 waveform matching, or perfect support for every track.

### Extended synthetic transition soak (host regression)

The offline analyzer now asserts the exact expected cumulative
48-kHz frame count for every valid 44.1-kHz source sequence:
`floor((input_frames - 1) * 48000 / 44100) + 1`. This is checked
in addition to the rolling resampler tick and SPU-frame counters,
so output duplication or omission cannot be hidden by simply
summing the reported per-scene counts.

`test_maximum_scene_count_long_pcm_soak` switches between A and B
for **32 scenes × 32 blocks** (524,288 input frames), verifies
continuous output clocks, deterministic per-scene measurements,
note-resolution accounting and absence of local asset mutation.
This uses generated banks only; it is not a PlayStation audio
waveform-parity test.

`test_wet_tail_survives_transition_into_zero_gain_bank` first
renders an EON-enabled sounding bank and then switches to a
zero-gain bank. It proves that the muted scene can still output
the previously accumulated STUDIO_C wet tail, while its own note
requests have zero dry gain and make no new reverb sends. This is
important when diagnosing a silent cue: zero-gain notes and
nonzero output are not contradictory.

Both tests are included in the normal host audit and the ASan/UBSan
PCM diagnostics workflow. The original music is never copied to CI.

### SEQ program changes, repeated notes and fallback classification

The offline auditor now separates the existing `fallback_notes` into
`cross_program_fallback_notes` and
`out_of_range_fallback_notes`, whose sum must equal the total.
The first counter covers a resolver selection from a different program
than the one currently requested by SEQ. The second covers a selection
in the requested program but outside the note's key range. The latter
may be an intentional nearest-key fallback; neither is automatically
a playback defect. `direct_match_notes` remains the complement of
the fallback count among successful resolutions.

The additional `note_offs` counter comes from the native sequencer.
It counts voices actually released by note-off handling, **including**
same-pitch retriggers and other sequencer stop actions. It does not
equal the number of raw MIDI Note Off events in the SEQ file.

A generated regression supplies same-block program changes
(7 → 9 → 7), twice triggers key 60 without an intervening explicit
Note Off, then requests key 61 under the missing program and key 110
outside the existing tone's range. In a 16-block audit window this
checks four resolved notes, two direct matches, one cross-program
fallback, one nearest-range fallback, and one voice release caused by
the repeated note. Switching to a second complete generated bank
must preserve 48-kHz frame accounting without carrying stale voices
from the previous scene.

All classifications are measurements of the runtime resolver's
actual decisions. They are not a claim that these program mappings
match the original game's intended orchestration; that still requires
comparison using privately supplied original assets.

### Delayed pQES events and tempo snapshots

The private-bank audit now records five per-scene **1-based** 512-frame
block indices: `first_note_block`, `last_note_block`,
`first_note_off_block`, `first_cross_program_block`, and
`first_out_of_range_block`. **Zero** means no corresponding event
during the chosen window. These are coarse audio-block timestamps,
not individual MIDI ticks or exact sample offsets, and contain
neither original event bytes nor note names.

A generated delayed SEQ schedules a note at tick 0, retriggers the
same pitch with a cross-program fallback at tick 45, and selects a
nearest-range note with an explicit voice release at tick 135.
With the default 480 PPQN and 500,000 µs/quarter, these occur in
**blocks 1, 5 and 13** respectively. The regression samples windows
of 4, 8, 12 and 16 blocks to catch prematurely or belatedly
dispatched notes as well as resets of the 44.1-to-48-kHz clock.
A companion fixture injects a native `FF 51` tempo change at
tick 0 to 250,000 µs/quarter. Because the SEQ worker snapshots
tempo when advancing each 512-frame block, the increased rate
takes effect **on the next block**; the delayed events are then
expected in **blocks 3 and 7**, not blocks 5 and 13.

These tests verify the sequencing implementation against independently
constructed synthetic timing expectations, not against timing
captured from the original PlayStation executable. `note_offs`
counts voices released by the sequencer, including a same-pitch
retrigger, rather than every encoded Note Off command.

### Multiple FF51 changes and SEQ end-of-track loops

The local audit reports additional per-scene metrics:

- `cycles_completed`, `first_cycle_block` and `last_cycle_block`
  are based on the sequencer's processed FF2F end-of-track boundaries.
- `observed_tempo_changes`, `first_tempo_change_block` and
  `last_tempo_change_block` compare the tempo **before and after**
  each 512-frame block. Multiple FF51 events inside one block may be
  counted as a single observable change (or no change when they cancel).
  These are not raw MIDI event counts.
- `final_tempo_us_per_quarter` is the tempo stored by the sequencer
  at the end of the measured scene, before the next bank switch.

A synthetic loop sequence starts at 500,000 µs/quarter, switches to
250,000 at tick 0, then to 750,000 at tick 30, and completes its
cycle at tick 90. In the 512-frame pre-render dispatch model,
end-of-track boundaries occur at **blocks 10, 19 and 28**. Tempo
changes are observed at **blocks 1, 2, 10, 12, 19, 21, 28 and 30**.
These are independent, test-constructed timing expectations; they
are not timing measurements from the original PlayStation game.

The 32-scene stress regression alternates this multi-tempo, repeating
bank with a separate bank that starts at its own 500,000-µs tempo.
Every A scene completes three cycles in 32 blocks; every B scene
starts a fresh sequencer with no inherited tempo or program state,
while the SPU's STUDIO_C wet history and the external resampler clock
remain continuous. It also checks all 524,288 input frames and the
exact count of 48-kHz output frames.

All fixtures are synthesized in CI and do not contain original
Vandal Hearts music. Hardware audibility and PS1 waveform fidelity
are not established by these tests.

### Detecting music-voice allocation pressure

The local SEQ/VAB transition audit also reports three numerical,
synthetic-testable measurements for the 20-slot PC-port-style music
SPU: `peak_active_voices`, `saturated_note_requests`, and
`first_saturated_note_block`. The last field is a **1-based**
512-frame audio-block position, or zero when no pressure occurred.

The resolver wrapper inspects the current SPU *before* each resolved
note is allocated, which catches multiple note-on events dispatched
inside the same block. A **saturated note request** is a successfully
resolved note arriving while all 20 music voices are still active.
This is a sign that the round-robin allocation path may displace
an existing voice; it is **not** by itself proof of an audible dropout
or an exact count of hardware PS1 voice steals. ADSR release voices
may still occupy active slots, and the metric excludes unresolvable
notes. No music sample bytes or individual note identities are logged.

The synthetic regression exercises (a) exactly 20 simultaneous
distinct notes, expected to fill all slots with **zero** saturated
requests; and (b) 23 simultaneous distinct notes, expected to produce
**three** saturated requests in the first block. Delayed Note Off
messages for two already displaced voices must not release the newer
slot owners. A/B/A/B bank switching then checks that pressure counters
reset per scene, the next bank has only its own note, and the 48-kHz
resampler clock remains exact.

This host-only diagnostic does not change voice allocation policy.
Direct comparison with the game's original SEQ/VH/VB and hardware
sound capture remains outstanding.
