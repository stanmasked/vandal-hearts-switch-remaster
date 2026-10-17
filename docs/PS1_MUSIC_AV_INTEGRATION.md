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

### ADSR Release occupancy versus truly reusable SPU slots

An active music voice whose ADSR phase has moved to
`VH_ADSR_RELEASE` is **not** yet a free voice slot. It remains
occupied until the SPU rendering step advances the envelope to zero
and marks the voice inactive. A new SEQ note-on at that moment may
therefore encounter the 20-slot capacity even when an earlier
`Note Off` was already dispatched.

The read-only resolver audit now distinguishes:

- `notes_while_release_active`: resolved note requests for which
  **at least one** active voice is in ADSR Release before allocation;
- `saturated_with_release_requests`: the subset of those note
  requests for which all 20 slots were still occupied;
- `peak_releasing_voices`: the largest number of active Release
  voices observed immediately before a resolved/unresolved note
  request (not a continuous frame-by-frame maximum);
- `first_release_overlap_block`: the first 1-based 512-frame
  block containing such a resolved request, or zero if none.

A regression starts 20 synthetic notes at tick zero, releases
three at tick 45 (block 5), and then requests three distinct notes.
When the new requests are also at tick 45, all three Release
voices are still active: there are **3** saturated requests and
**3** requests overlapping the Release state. When the three new
notes are instead delayed to tick 90 (block 9), the earlier voices
have finished ADSR Release during intervening SPU renders: the
requests find free slots and both measurements are **0**.

The regression also confirms that stale Note Offs for previously
released notes do not stop the new slot owners, that a transition
to the next VAB bank resets this scene's allocation-pressure
counters, and that the external 44.1→48-kHz output clock remains
continuous.

**Scope:** These metrics sample the resolver/allocator boundary,
not the PlayStation hardware's cycle-accurate envelope scheduler.
A saturated request signals allocator pressure, not proof of a
particular stolen voice or audible dropout. No production voice
allocation or release behavior has been modified.

### Natural release retirement and repeated voice reuse

A note entering `VH_ADSR_RELEASE` is not immediately removed from
the SPU. To separate *natural* completion of that phase from
round-robin replacement of a still-active voice, the private-bank
auditor now samples each slot immediately before and after every
512-frame SPU render. The following additional metrics are reported:

- `adsr_release_slot_retirements` — the count of slots which were
  active in Release immediately before rendering and were inactive
  after rendering the block. This does **not** count Release voices
  overwritten by a new Note On before the render.
- `first_release_retirement_block` and
  `last_release_retirement_block` — the earliest and latest
  1-based 512-frame block in which such retirement was observed.
  They are both zero when no retirement occurred.
- `peak_releasing_voices_before_render` — the highest number of
  simultaneously active Release voices observed just before a
  block's SPU rendering begins.

A synthetic 40-block sequence starts 20 distinct music voices and
executes four successive waves of three Note Offs and three new
Note Ons. In the **immediate** case all 12 new requests arrive
while the corresponding Release voices still occupy slots; these
voices are replaced before rendering, so the test expects 12
saturated requests and zero natural Release retirements. In the
**delayed** case the SPU renders the Release phase before the next
requests: the test expects zero saturated requests and 12 natural
retirements, first in block 5 and last in block 29.

A separate stress test alternates these two banks for 16 scenes,
checking that Release-retirement and saturation counts reset on
every bank switch, that the new bank's notes are resolved from
its own decoded PCM, and that the rolling output resampler still
produces the exact number of 48-kHz frames. Neither test includes
the original copyrighted game audio.

These are **observational, block-granularity software metrics**.
A Release voice that becomes inactive and is reused within the
same render block cannot be individually timestamped here.
A zero retirement count does not mean the voice never entered
Release, and it does not establish waveform or cycle parity
with original PlayStation hardware.

### ADSR Release rate matrix and PCM partition independence

The native SPU host regression exercises the unmodified production
`vh_native_spu_render` envelope logic against **synthetic looping PCM**.
The loop ensures a voice can retire only through ADSR, not because its
source sample reached the end. Every case starts at Q15 level
`0x7FFF`, issues Note Off, and renders 9,000 frames twice:
first one PCM frame per call, then in irregular 127-frame chunks.
The complete PCM16 outputs must be byte-for-byte identical.

| VAB ADSR2 release bits | Release law | Expected rendered frames to retire |
| --- | --- | ---: |
| `0x0000` | Linear, fast | 2 |
| `0x0005` | Linear, moderate | 64 |
| `0x000A` | Linear, slow | 2,048 |
| `0x0020` | Exponential, fast | 16 |
| `0x0025` | Exponential, moderate | 496 |
| `0x002A` | Exponential, slow | 8,842 |
| `0x001F` | All-ones release shift | Does not retire within 9,000 frames |

The special all-ones case is explicitly bounded: the test never
waits indefinitely for the voice to retire. It checks that the
voice remains in Release, keeps its level and stays unavailable
for free-slot allocation. All naturally retired voices must move
to ADSR Off, become allocatable again, and successfully restart
the Attack envelope when a new note is assigned.

The rate/frame numbers here are **regression expectations for the
project's PC-port-style software envelope**. They are not measured
PS1 hardware timings; exact parity requires original-game audio
and hardware comparison. This test runs on the host and under
ASan/UBSan in the PCM diagnostics CI. It neither embeds original
audio nor changes native SPU playback.

### End-to-end SEQ/VAB ADSR2 release verification

A companion regression checks the same seven release-rate encodings
through the entire **synthetic pQES → imported pBAV VH/VB tone → native
SPU → 44.1-to-48-kHz PCM** path, rather than configuring the SPU
envelope directly. Each generated tone stores ADSR2 in its actual
little-endian VH tone-table field. A note-off at SEQ tick 240 is
dispatched before rendering **block 22** (480 PPQN, 500,000
µs/quarter). The resulting voice retirement should occur in:

| ADSR2 release bits | First and last Release retirement block |
| --- | ---: |
| `0x0000`, `0x0005` | 22 |
| `0x000A` | 25 |
| `0x0020`, `0x0025` | 22 |
| `0x002A` | 39 |
| `0x001F` | No retirement within 42 blocks |

The second synthetic bank retains its default fast Release (block
22) in every test. All seven pairs are run twice to check exact,
repeatable JSON output, both input-bank byte-for-byte immutability,
the isolation of each scene's counters, and the exact 48-kHz frame
total. The audit does not export decoded PCM or source file bytes.

The standalone native SPU release-rate test and these seven
end-to-end cases are both exercised under **ASan/UBSan** in the PCM
diagnostics workflow. Passing these software checks does **not**
establish hardware PS1 release timing, pitch/envelope parity, or
audible Switch quality; privately owned original SEQ/VH/VB and
physical playback captures are still required for that assessment.

### Switching away from slow/never-ending ADSR Release

The local offline audit also inspects **both sides** of every successful
A/B bank swap. Before `vh_native_seq_switch_scene` it measures:

- `prior_bank_active_voices`: active voices still using the old bank;
- `prior_bank_release_voices`: active old voices in ADSR Release;
- `prior_bank_pcm_references`: voice records with a non-null PCM
  pointer, **including inactive** voices whose Release already ended.

After switching it verifies that **all** 20 voice records have
`active=0`, a null PCM pointer and an Off ADSR phase; the SPU
allocation index and per-scene render counter have reset; the
sequencer references the new SEQ and resolver; and the caller-owned
resampler has retained its exact clock state. Full STUDIO_C reverb
history is compared byte-for-byte across the switch, together with
the Gaussian interpolation setting and global wet configuration.
The additive report flags
`prior_bank_voices_cleared` and
`reverb_history_preserved_on_switch` for each scene. The initial
scene has no incoming switch and reports both flags as false.

**Important distinction:** in the current production renderer,
a voice that naturally finishes Release becomes inactive, but the
voice record may still contain a borrowed PCM pointer until it is
reassigned or the bank is switched. This is permitted while its
original PCM arena is still owned by the loaded bank. It would be
unsafe to unload that arena while leaving this pointer accessible
to later code. The scene-switch code clears *both* active Release
voices and inactive residual references before any bank unload.

Synthetic CI covers 16 scenes alternating a wet bank with
`ADSR2=0x002A` (a slow exponential Release that remains active at
block 32) and a zero-dry-gain bank with fast Release. A second
regression switches away from `ADSR2=0x001F`, which cannot retire
within the test window, into a **zero-note** SEQ. The next scene
may still contain nonzero post-resampler PCM solely from prior
STUDIO_C wet history, although all old voices and pointers were
discarded. In all cases the original files are read-only and
never published.

These assertions describe the host software switch and do not
prove that physical Switch audout buffer ownership or original
PlayStation hardware envelope behavior are identical.

### audout single-page ownership during SEQ bank transitions

The native libnx sound probes submit one 4-KiB-aligned
`AudioOutBuffer` page using blocking `audoutPlayBuffer`. A successful
service return **alone** is not sufficient evidence that this
particular page may be overwritten: `released` must point to the
**same descriptor** as the submitted page. Both
`probes/libnx_ps1_music_av.c` and
`probes/audout_audio_smoke.c` now enforce this invariant using
`vh_audio_output_page_returned`, a portable pointer-identity check.
The latter probe also checks PCM size against its actual allocated
4-KiB output page instead of an undefined local descriptor.

A wrong or null returned descriptor is treated as a failed submission
and passed through the existing two-restart
`vh_audio_output_submit_recover` policy. The prepared PCM data and
its pointer remain unchanged across the retries, and no new
SEQ/SPU/resampling operation is performed in that path. Stop/close
must succeed before a retry can reuse the backing page; if all
allowed attempts fail, the caller must stop the audio pipeline rather
than proceed as if the page had been released.

The host test `test_vh_audio_output_recovery.c` now fault-injects
both **foreign** and **null** returned descriptors. It confirms a
recovery with an identical immutable PCM page after reopening the
output service, and a terminal, fail-closed response when every
attempt returns a foreign descriptor.

Its six-scene (48-block) synthetic SEQ/SPU test also alternates two
different source PCM arrays after **each eighth completed output
page**. Each of the five scene switches is allowed only after the
previous mock output page was returned; all outgoing borrowed voice
pointers are cleared, the STUDIO_C delay buffers remain unchanged,
and the rolling 48-kHz resampler keeps its exact clock.
Fault-injected submission errors and wrong/absent returned
descriptors are interleaved throughout the run. Accepted pages must
have the expected cumulative PCM hash and frame count, without
duplicate synthesis or skipped frames.

These are host-level lifecycle and CI compilation checks. They do
**not** establish physical speaker output, real DMA synchronization,
or libnx behavior on an actual Nintendo Switch. The separate SDL2
feasibility workflow may also be blocked by devkitPro package-network
availability, independently of these audio invariants.

### Measuring real audout submission waits on Nintendo Switch

Both libnx probes now measure the **blocking time of each individual
`audoutPlayBuffer` invocation**, using `armGetSystemTick` before and
after the actual service call. This is deliberately separate from the
existing SEQ/SPU/resampler compute-time measurement. The new portable
`VhAudioSubmitTiming` accumulator provides:

- `calls`: all attempted audout submissions, **including** failed
  calls and additional recovery attempts; not the number of distinct
  musical PCM pages;
- `total_ticks` and `max_ticks`: cumulative and maximum measured
  blocking ticks in the audio service;
- `waits_longer_than_page`: submissions whose blocking time exceeded
  the expected duration of **their own 48-kHz PCM frame count**;
- `failed_submissions`: failed service calls or nonmatching/NULL
  returned page descriptors that cannot safely authorize reuse.

The standalone audout console probe prints average and peak wait
times in microseconds and the long-wait/failure counts every 128
accepted blocks and again at exit. The combined graphics/audio
probe keeps statistics on its **audio-owner thread**, atomically
publishes three small counters, and displays a **neutral blue**
peak-wait bar capped visually at four nominal 512-frame durations.
This gauge is not a green/red audible-quality verdict.

**Interpretation:** `audoutPlayBuffer` is blocking, and waiting for
a page to complete may be normal. A wait longer than one nominal page
duration is only a *diagnostic observation*: it neither proves
a dropped buffer nor establishes that a speaker glitch was audible.
The service-call timer also excludes the time spent in stop/reopen
between recovery attempts; all separate attempts are still counted.
Values are collected on hardware, not predicted from host CI.

The shared helper rejects zero frame counts, oversized pages, zero
tick frequency, arithmetic and counter overflow without altering its
accumulated state. The host test uses a deterministic **19.2-MHz
synthetic tick source** to verify expected page-duration thresholds,
saturating microsecond conversion, and correct accounting during
foreign/NULL page returns, bounded restarts, and an entire 48-page,
six-scene bank-switch sequence. This host test does not measure
real console scheduling latency.

The measurement does not change music timing, STUDIO_C reverb, source
bank ownership, audio format, or the rule that a previous page must
be returned before the audio thread can overwrite it.

### Comparing audout waits on SEQ scene boundaries

The combined native graphics/music Switch probe now records **two
separate classes of logical PCM pages**:

- `ordinary`: each PCM page that does not immediately follow an
  explicit switch of the generated SEQ fixture;
- `first_after_switch`: **only** the very first rendered and
  submitted PCM page after a successful synthetic SEQ switch.

For each class, `VhAudioSceneWaits` tracks logical pages, the sum
and peak of blocking `audoutPlayBuffer` service ticks, pages with
at least one raw service call longer than the page's nominal 48-kHz
duration, pages with one or more retry submissions, and terminally
failed pages. A page with recovery attempts contributes to the
logical-page count **once**; the sum of raw submission waits includes
all service attempts for that page, not stop/reopen overhead. Terminal
failures are included as observed failed pages, never accepted pages.
No source music, filenames, samples, or note events are serialized.

The fixture switches SEQ every 64 completed PCM pages, only after
the prior blocking audout call returns its exact descriptor. The
audio-owner thread snapshots `VhAudioSubmitTiming` just before the
page submission and after bounded recovery, tags the first new-scene
page, and atomically publishes **two comparable peak-wait gauges**
to the graphics thread. The upper blue bar is the ordinary-page
peak; the lower pale-blue bar is the scene-boundary peak and remains
empty until the first generated switch. Both cap their display at
four nominal 512-frame durations. User-supplied SD music is **never
automatically switched**; the scene-boundary bar is fixture-only,
not evidence about switching the user's original resources.

The portable helper validates that exactly one call per accepted
logical page returned successfully, no more than two restart attempts
were observed, and all timing snapshots and counter additions are
monotonic and overflow-safe. Invalid observations do not change its
counters and cause the caller's diagnostic pipeline to stop rather
than publish misleading statistics.

The synthetic host regression compares **43 ordinary pages with five
first-after-switch pages** across six musical scenes (48 pages
total). It explicitly injects a failed submission at the first
page of one new scene and a foreign returned descriptor at another,
verifies correct recovery on both boundaries, and checks that
per-category blocking totals reconcile exactly to the raw audout
timer while the stream's accepted PCM hash, reverb history and
44.1→48-kHz frame clock remain unchanged.

**Not a dropout detector:** comparison of blocking waits may reveal
scheduling changes near a switch, but cannot by itself establish
underflows, glitches, latency to actual sound output, or audio
fidelity on hardware. The NeXium runner does not capture speaker
audio. Measurement of these timings on a physical Switch remains
a separate acceptance step.

### Standalone Switch audout console: captureable A/B latency results

The independent `build/audout-audio-switch-probe.nro` now offers a
text-based counterpart to the combined graphics probe. It loads
locally owned SEQ/VH/VB from SD when available; otherwise, it plays
two different **generated** SEQ cues (same generated VAB), switching
between them **only after each 64 successfully returned PCM pages**.
Original SD-loaded music is never automatically replaced or switched.

The output prints `fixture_switches` and the two per-page categories
every 128 completed blocks, as well as a final comparison:

- `steady pages`: average and peak audout service wait in
  microseconds, pages with slow backend calls, and retry counts;
- `boundary pages`: the same quantities for the **first** PCM
  page after each synthetic cue switch;
- `Audout scene summary`: accepted normal/boundary page totals,
  completed fixture switches and per-class wait peaks.

The console labels measured waits, **not** actual audible glitches.
The raw audout timer includes each retry attempt, and the associated
page is counted exactly once. The SEQ/SPU/resampler calculation and
the blocking audout call are timed separately. The first new-cue page
is tagged only when a synthetic switch succeeds and an output
submission begins; a terminal submission error is reported rather
than quietly advancing to the next scene.

For a physical Switch check, launch the NRO from the CI artifact
`native-audout-music-nro` (or `make audout-audio-probe` with
devkitA64), choose the generated-fixture path by **not** placing a
user-owned complete audio bank at
`sdmc:/switch/vandal-hearts-remake/audio`, and observe the
text counters while listening. The test stops music and closes
audout before displaying its final report; **press Plus (+) to exit**
after recording the results or taking a screenshot. The final
results remain on-screen until then. No proprietary audio is
included in the NRO, and this diagnostic does not write logs or
original bytes to the SD card.

The `Switch libnx audout music NRO` CI is now enabled on
`feat/native-av-ps1-seq-integration`, so the standalone console
variant is built for this branch instead of remaining untested until
merging into the older CD-XA pipeline base. It still does not
establish successful playback on the user's hardware; the device
must be run and listened to separately.

### Final audout results: complete, interrupted, or inconsistent

The standalone console NRO now produces an additional
`Run evidence` result after stopping audio and closing the service.
This deliberately avoids interpreting a return from
`audoutPlayBuffer` or a clean applet close as evidence that the
**entire** 1,200-block hardware observation ran to completion.

The portable verifier `vh_audio_output_verify_run` reconciles:

- successfully returned output pages against the recovered service's
  accepted-page counter and the sum of *accepted* ordinary and
  first-after-switch logical pages (which excludes failed pages);
- completed generated-SEQuencer scene switches against the number
  of accepted boundary pages and the configured fixture cadence
  (one switch after every **64** accepted PCM blocks);
- zero scene switches and zero boundary pages for a user-owned
  SD-loaded music set, which must not be switched automatically;
- cumulative blocking ticks from both page categories against the
  raw `audoutPlayBuffer` timing accumulator, including failed
  calls and restarts, as well as failure and recovery counts;
- monotonicity and safe bounds for counts and intermediate sums.

Exactly three outcomes are possible. **FULL PCM PAGE ACCOUNTING**
means the complete 1,200-page run finished without application
errors *and* every accounting invariant passed.
**INCOMPLETE - NO FULL-RUN CLAIM** means available counters reconcile,
but the applet exited before the planned number of pages or a
submission/stop error interrupted execution. **COUNTER MISMATCH -
INVALID** means independent counts contradict each other; no
successful run should be claimed. The applet sets a nonzero
diagnostic result code if an otherwise error-free run produces a
counter mismatch.

Even FULL is **not** proof of audible output or glitch-free playback:
there is still no physical Switch sound capture or hardware timing
validation in CI. The result screen is held open after all audio
services and bank resources have been closed; press **Plus (+)** to
exit after recording the evidence.

Host regression uses an independently constructed 48-page,
six-scene synthetic playback trace. It verifies that the same trace
is FULL when 48 pages are expected, INCOMPLETE when 64 are expected,
and INVALID when page counts, switches, timing totals or recovery
counters are falsified. It separately exercises an aborted failed
page and a two-page user-owned-bank accounting scenario. The
standalone NRO is compiled via the `Switch libnx audout music NRO`
workflow on the active feature branch and its binary artifact
contains no original game music.

### Four normalized audout wait bands for on-device screenshots

A single peak wait is not enough to distinguish an isolated backend
stall from repeated delays during a Switch music scene change.
`VhAudioPageWaitBucket` therefore keeps a fixed-size four-bin
histogram, independently for steady-state and first-after-switch
PCM pages. The bands compare **the sum of blocking audout service
waits for each logical page** with the duration of that page's
*actual* 48-kHz frame count:

| Wait band | Meaning |
| --- | --- |
| `<=1x` | Blocking backend wait did not exceed this PCM page duration |
| `<=2x` | More than 1x, at most 2x page duration |
| `<=4x` | More than 2x, at most 4x page duration |
| `>4x` | More than four page durations |

The four bins are mutually exclusive. Their sum must equal the
corresponding logical page count, **including a terminally failed
page** if one was observed. Recovery retries still contribute only
one page, with the service waits of all attempts added; stop/reopen
time is excluded. The PCM page duration is calculated from the
resampler's actual output count rather than assuming a fixed 557
frames per block. Fixed-size counters use no heap allocation,
retain no per-page timestamps, and do not reveal music resources.

The standalone audout NRO now prints both histogram rows directly
above the result code and **Plus-to-exit** prompt. The final
`FULL PCM PAGE ACCOUNTING` verdict is also contingent on histogram
sums matching their page counts. A synthetic host test generates
exactly one observation in each of the four latency bands and
rejects artificially incremented or decremented histogram bins,
while the existing 48-page A/B bank-switch regression checks the
same invariants under injected retries.

The bands are **not glitch flags**: `audoutPlayBuffer` may normally
block while playback completes, and a long page wait does not imply
a sample underrun, an audible gap, or PS1 parity. The purpose is
to make the distribution and its relation to cue switching readable
on a photo of the physical Switch results screen, without exporting
copyrighted music or any audio recordings.


### Paired PCM seam and audout latency observations

The standalone NRO now pairs each returned 48-kHz PCM page with its
corresponding four-band audout service-wait observation. After the
service returns the exact submitted PCM buffer descriptor, the probe
computes the **maximum absolute adjacent stereo PCM16 sample step**
between the preceding returned page and this page. Results are
separated into ordinary pages and first pages after synthetic cue
switches. The first page has no predecessor and contributes no seam;
a retry of the same PCM page contributes only one seam. User-owned
SEQ banks are never automatically switched.

The final Switch console screen prints one maximum PCM seam magnitude
per wait band and category, alongside the existing wait histogram.
Zero may mean an empty band or a zero step. A portable verifier checks
that seam counts equal returned pages minus the first, that they match
the category totals and do not exceed their wait-bin page counts.
The experiment retains only the previous stereo frame in memory and
aggregates: no copyrighted samples, recordings or identifiers are
exported. A five-page generated host test includes a failed submission,
a successful retry, corruption detection and invalid-input isolation.

A sharp PCM step is **not** automatically a click, nor is a long
\`audoutPlayBuffer\` wait necessarily a dropout. Pairing the two
observations narrows down where to listen on a physical Nintendo
Switch; it cannot establish audible effects without hardware
listening or external sound capture. No resampling, scene switching
or output scheduling behavior is changed.


### Manual listening marks on physical Nintendo Switch (A button)

The console-only audout probe now accepts a **rising A-button press during
the 1,200-page playback run** as a *user-reported perceived issue*. Each
press reviews up to the **previous 32 returned PCM pages** (~0.37 seconds
at 512 source frames / 44.1 kHz), accounting for approximate human
reaction latency; it is NOT a precise timestamp of the acoustic event.

The in-memory ring holds only the four-level audout wait bin, whether
a page was the first after a synthetic cue change, whether its output
submission needed recovery, and the inter-page maximum PCM16 adjacent
sample step. The final results screen summarizes the number of A
presses and how many had, *anywhere in the look-back window*, a cue
transition, >2x or >4x wait, or retry. It also displays the largest
PCM16 seam step seen near any button mark.

Manual marks are not sample-level audio recordings, proof of actual
clicks, or evidence that a delayed audout call caused an audible fault:
a human button press is delayed and the window may overlap unrelated
events. The check does not write any files or music to SD. Pressing A
does not trigger cue changes, silence, playback pause, DSP reset or
recovery. At the end the probe separately verifies that ring input
contains exactly the returned-page count and summary counters remain
valid. Use **Plus** on the final report to exit, as before.

A new portable, copyright-free host regression checks marker
aggregation, window expiry/wraparound, invalid observations, and
corrupted counts. Until physical Switch listening happens, A-marker
counts must be treated as **unobserved**, not zero-perceived-issues
hardware evidence.


### All-page control windows for manual A-button marks

A 32-page look-back can contain a synthetic cue switch or long backend
wait even when nobody hears a defect: one event appears in up to 32
overlapping windows. The probe now compares the operator's A-button
observations with **every returned page**, treated as an eligible
look-back window with the same exact classification logic.

The final console report pairs counts for marked windows (A) and
all-page windows (all), for synthetic cue switches, service waits over
two or four PCM-page durations and backend retries. The respective
denominators are the number of manual marks and the number of returned
PCM pages. A zero-mark run has no defined manual-mark proportion and
does not imply glitch-free playback.

The portable accumulator computes each all-page window from the newest
page and at most 31 earlier returned pages; a manual mark uses the most
recent 32 returned pages. The first 31 observations use proportionally
shorter windows for both groups. All windows can overlap, so ratios
are descriptive only, NOT statistically independent trials or
evidence of causation. No timing/scheduling, sound recording, file
access or gameplay is changed.

The host regression explicitly verifies that one isolated synthetic
cue/wait/retry is present in exactly 32 adjacent all-page windows,
disappears immediately after ring wrap, distinguishes >2x from >4x
waits and rejects corrupted baseline counters.


### A-button input sampling coverage

Input is sampled once, after each synchronous audout buffer return.
Short button presses entirely between polls can be lost. A long
backend call, retry, or diagnostic console update may extend that
interval even when every PCM page eventually returns.

The physical Switch results page therefore also prints the longest
actual system-tick interval between consecutive padUpdate calls,
the number of intervals exceeding one or four times the nominal
duration of their PCM output page, and the total number of polls.
The first sample has no measured interval. These indicators describe
input sampling, NOT backend underruns, missed-press counts, or
audible defects. The final report validates exactly one recorded
controller poll per successfully returned logical PCM page.

For human testing, hold A through at least one music block after
noticing an anomaly, then release before another annotation. The
32-returned-page look-back corresponds to nominal audio duration,
not guaranteed elapsed wall time if audout stalls. Neither these
numbers nor an absence of A marks establishes glitch-free output.
No playback path, copyrighted bytes, controller history, or SD
storage is changed. The portable regression checks boundary cases,
overflow, invalid counters and non-monotone tick samples.


### Exact per-band audit including terminal audio failures

The inter-page PCM seam audit now rejects *compensating bin corruption*:
the total seam count may be correct and each seam count can still stay
below the raw audout wait-bin count while a seam is assigned to the
wrong duration range. The verifier now requires exact agreement in
each ordinary/first-after-switch wait band, not just aggregate totals.

The per-page audout recorder also keeps a separate four-bin
histogram of **terminally failed logical pages**. Such attempts are
already present in the service-wait histogram but must never produce
a returned-PCM seam. The verifier subtracts the failed pages from
their respective bins and, if any successful page exists, subtracts
the single first returned page from its **recorded actual wait band**
(it has no preceding sample). This also supports a first-page
wait longer than 4x the nominal PCM page duration. Invalid failed-bin
distributions, mismatched category/bin counts, tampered first-page
classification, and nonzero peaks in empty seam bins all fail closed.

A portable generated host regression covers both a five-page
steady/scene-switch trace with a recovered submission and a distinct
two-delivered/one-failed trace starting in the >4x band. No music
content, audio samples or timing traces are written to SD. This
is evidence-accounting hardening, not evidence of audible glitches.


### Three photograph-friendly diagnostic report pages (standalone audout NRO)

After the probe stops the audio service and releases the music banks,
the old accumulating console log is replaced by a **cleared, paginated
three-screen report**. Press **LEFT/RIGHT** to move between screens
(wrapping at either end); press **PLUS** to exit. Each screen redraws
only when its page changes, and navigation starts after playback
finishes, so it cannot alter SEQ/SPU scheduling or actual audout waits.

- **1/3 Device/service:** exact returned-page accounting result,
  source identity (generated fixture vs user-owned SD), service call
  counts, retry totals and separate normal/switch wait distributions.
- **2/3 PCM:** exact seam counter audit, per-band seam counts and
  peak steps for ordinary/boundary pages, failed-page totals and first
  page's wait classification.
- **3/3 Listening:** human A-mark overlap against the all-page
  baseline, the observed peak PCM step, and input-poll coverage
  / integrity (including long polling gaps and missed-short-tap
  warning).

The former single long report could scroll the first verdict and
histogram off the Switch console, particularly after many periodic
progress messages. The three short cleared screens keep each group
together for separate photographs. A portable regression verifies
both page-direction wrap and no-false-FULL status when any audit fails.

The display labels the run as **FULL PCM accounting**, not as
"glitch free": only listening or independently recorded hardware
audio can establish whether clicks/dropouts were audible. No PCM,
button history, copyrighted asset or screenshot is automatically
saved or uploaded.


### Operator-selected normal-sounding B-button control

The standalone on-console audout NRO now supports two **different
subjective annotations** during music playback:

- Press **A** when you believe you hear a click, gap, or other defect.
- Press **B** when the audio currently sounds normal. B is an
  explicit operator-selected *negative control*, not a randomized
  baseline. Press them separately; if A and B rising edges occur
  together in a single controller poll, both are ignored.

Both record the identical past 32 **returned PCM pages**, using the
same shared classifier for a synthetic scene switch, >2x/>4x
backend waiting, output retry, and largest inter-page PCM16 step.
Two independent count sets are retained. The existing all-returned-page
baseline remains unchanged. The third on-console report shows event
overlaps as **A / B / all**, with denominators A marks, B marks,
and returned pages, respectively. No derived significance score is
printed: overlapping windows, selection effects, delayed manual
reaction and controller polling gaps prevent causal or statistical
inference. Zero B marks also means no usable subjective-control
comparison.

For practical listening, choose a few normal-sounding moments with
B in addition to any perceived faults with A. Do not label the
control data as a verified absence of clicks: it only describes
what the operator thought at the time. Press buttons long enough
to cross at least one audout return, then release them before
marking another event. No PCM capture, copyrighted sample material,
button-event history or files are stored. The portable test checks
shared A/B window classification, counter separation, ring expiry,
corruption, and no-mutation on overflow.


### A/B hold-release annotation gate

The old rising-edge-only logic could register B as a normal-sounding
control while A remained held from a previous perceived defect.
The new console input gate checks current A/B held states instead.
A mark or an A+B chord disarms the gate. The next mark is accepted
only after a later controller poll where both A and B are released.
A chord is rejected as ambiguous, and the final listening page
displays its rejection count. On startup, the gate also waits for
an initially neutral A/B poll before accepting the first mark.

Gate counters are checked against actual manual A/B mark totals and
the number of successfully returned PCM pages; any mismatch prevents
a FULL integrity verdict. Rapid tap/release cycles between audout
controller polls can still be missed. These are subjective human
annotations, not proof of audio defects or causation.

A portable regression reproduces A held while B is newly pressed,
simultaneous A+B chords, later release/re-arm, damaged counters,
invalid input bits and saturated counters. The change affects only
diagnostic controller handling, with no effect on sound rendering,
audout submission, music asset loading or SD storage.


### Atomic A/B annotations on failed or interrupted audout reports

Previously the single-threaded probe first committed the A/B held-state
gate (including a count of accepted button annotations), and only then
tried to update the 32-page listening ring. A damaged ring or saturated
listening counter could reject the second operation after the first was
already committed. Final audit correctly detected the disagreement,
but the two in-memory diagnostic objects were already inconsistent.

The new portable input helper stages only the small button-gate struct
and checks that its poll index is exactly the previous delivered page.
It then commits the associated A/B listening observation first, and
only after success commits the staged button gate. On error, neither
object is modified. This enforces exactly one gate update per recorded
PCM page, prevents duplicate samples and rejects skipped page counts.
The output recovery, SEQ/SPU resampler and audout scheduling paths
are untouched. No sample data or button history is recorded.

A host regression tests an A/B held/chord timeline, repeated polling
on one page, corrupted ring data, saturated listening count, a page
without a matching input sample (as in an aborted probe), illegal
button flags and a gate counter ahead of the delivered-page count.
The regression runs through both host Make targets and independently
under CI UndefinedBehaviorSanitizer. Neither these tests nor a clean
FULL PCM-accounting verdict prove there are no audible glitches on a
physical Nintendo Switch.


### Independent 4096-page A/B lookback oracle (portable CI)

To make the 32-returned-page lookback more resistant to silent ring
off-by-one regressions, a new host-only oracle compares the production
accumulator against an independent chronological array of **4096**
synthetic page observations. The oracle never reads the production
ring to calculate expected events: it scans up to the previous 31
pages plus the current page directly from the historical fixture.

For every returned page, the test compares all four event classes
(synthetic scene change, audout wait greater than 2x/4x nominal page
duration and retry) across three groups: manual perceived-defect A,
manual normal-sounding B, and every-returned-page background.
It also verifies both A/B maximum inter-page PCM16 jumps, and checks
the production 31-page and 32-page lookback results separately on
**every** one of the 4096 pages.

The deterministic fixture includes deliberately adjacent events on
pages 31, 32 and 33, many further full-ring wraps, isolated cue
boundaries, varied long waits, backend retries and distinct A/B marks.
The same test is built under both Make test targets and in CI with
-O0 and -O2+UndefinedBehaviorSanitizer, with output comparison.
No copyrighted audio, PCM sample buffers or input timing logs are
used. This test only validates counting and window boundaries;
it is not a physical hardware listening test or evidence that
audible glitches are absent.


### Restored DSP processing-budget evidence in the native audout results

The three-screen diagnostic layout originally retained backend wait
histograms and audio seam counters but accidentally dropped the DSP
processing cost from its final on-device results. That cost was still
measured and printed only in periodic scrolling progress lines, which
can disappear from the Switch console before the operator photographs
the final report.

Report **1/3** now includes average and peak compute time in
microseconds, the number of rendered pages exceeding their nominal
44.1-kHz SEQ/SPU/resampling budget, the number of synthesized pages
and an independent compute-page integrity verdict. The measurement
excludes blocking audout service waits and result-screen rendering.
It includes any synthetic fixture scene-switch work before that
page's render.

The portable compute accumulator rejects a zero budget and integer
overflow without modifying previous measurements. A final consistency
check allows exactly the delivered-page count or one additional
rendered-but-undelivered page (if an output submission terminated
the probe); two or more missing deliveries, negative accounting,
inconsistent peak or impossible over-budget totals fail closed.
The final FULL PCM-accounting label now also requires this check.

Both \`make test\` and \`make test-audio-stream\` include a host
regression for threshold boundaries, an interrupted final audout
submission, arithmetic saturation and tampered statistics. The PCM
workflow additionally runs it with UBSan. This change adds only
bounded in-memory diagnostic metadata. It does not speed up the
audio engine or demonstrate glitch-free playback on physical Switch.


### DSP compute cost separated by scene-boundary versus ordinary pages

The portable audout compute telemetry now distinguishes ordinary
SEQ/SPU/resampling blocks from the **first rendered block after a
synthetic music-scene switch**. Previously, the global over-budget
count and peak processing time could not show whether a spike
belonged to the actual change-of-cue work or to routine rendering.

The same sample clock remains in use: the elapsed wall-clock ticks
include the scene-switch operation (if one occurs), SEQ advance, SPU
render and rate conversion, and exclude blocking audout service waits.
Both per-category buckets retain **rendered block count, total ticks,
max compute ticks and count exceeding one nominal block budget**.
The first results screen displays independent normal/switch overrun
counts and peaks as well as the total DSP average/peak. In the
user-owned SD-music mode the probe never triggers synthetic scene
switches; the switch compute bucket therefore remains empty.

Before claiming FULL PCM accounting, verification now enforces exact
equality between the two compute buckets and their global totals,
peaks and over-budget counters. It also correlates delivered scene
boundary pages with the associated rendered category and accepts at
most one final undelivered page across both categories, not one
per category. Tampered category assignment, missing/extra pages
and arithmetic saturation fail closed.

Portable regression cases check strict budget threshold behavior,
a final failed scene-boundary submission, a final failed ordinary
submission, mismatched scene counts, contradictory bucket sums
and no-mutation counter overflow. The existing CI UBSan exercise
compiles and executes those checks. This improves diagnostic
interpretability and integrity; it is not evidence of audible quality
or proof that Switch audio compute meets its budget in practice.


#### Final-render ordering check

The first scene-category host regression exposed a real auditing
ambiguity: group totals alone could treat an earlier ordinary page
as not yet returned even when the more recently rendered cue-boundary
page had supposedly already returned. The native probe renders and
submits a single synchronous PCM page at a time, so that sequence
cannot occur.

The accumulator now stores the one-bit class of the **last rendered
page**. If the delivered-page count is short by one, the missing
page must belong to that class, not merely to either plausible group.
The verifier rejects a missing ordinary page followed by a delivered
switch page (and vice versa). Invalid last-class values and a nonzero
class in empty runs fail closed. These checks are tested by the
host regression and PCM UBSan, without changing real audio service
timing or any PCM data.


### Same-page DSP budget vs audout wait correlation (native Switch probe)

After the last-rendered-page auditing was verified, the hardware
results now also distinguish two types of **joint events on one
successfully returned logical PCM page**: a SEQ/SPU/resample DSP
duration exceeding its nominal block budget *and* a blocking audout
wait exceeding either 2x or 4x the duration of its own output page.
The first results screen shows the joint-event counts separately
for ordinary pages (N) and the first rendered page after a synthetic
scene switch (S). These are inclusive thresholds: >4x is a subset
of >2x. Neither a long backend wait nor a coinciding compute
overrun demonstrates an audible drop or establishes causality.

Each returned logical page contributes exactly one joint sample;
audout retry attempts are not treated as separate PCM pages. A
terminally failed rendered page contributes nothing to the joint
counts. The portable joint verifier cross-checks returned-page
totals against scene groups, DSP-budget overruns against the DSP
accumulator (subtracting the known final undelivered page, if any),
and >2x/>4x counts against the exact audout wait bins minus their
terminally failed logical pages. Contradictory joint-event counts,
category shifts, mismatched totals and counter overflows fail closed.
The NRO's FULL PCM-accounting status now also depends on this
cross-audit. No PCM contents, proprietary music, controller history
or audio timestamps are retained.

A generated regression creates overlapping and nonoverlapping DSP
and backend events in both categories, including a final
undelivered >4x scene-boundary page and an independent normal-page
failure. It also tests compensated counter corruption and atomic
overflow handling. Both Make host test targets and PCM CI with
UndefinedBehaviorSanitizer run the new regression. Physical Switch
listening is still required to establish any audible outcome.


#### Exact limits of joint-count validation

The first joint-counter test accidentally expected an observed
intersection shift from one to two DSP-overbudget/>4x audout pages
to be rejected. That shift can still be consistent with the
independent total DSP-overbudget count and audout wait histograms.
Those aggregates cannot uniquely reconstruct per-page overlap.

The verifier now checks the exact independent marginal totals,
category/returned-page identity, subset constraints, and necessary
lower bounds for set intersections. It rejects impossible overlaps
without claiming that a plausible altered overlap is detectable.
The regression asserts both properties explicitly. Joint counts
are recorded once as pages are returned, but cannot be independently
reconstructed from marginal totals alone. Neither coincidence nor
its absence proves an acoustic defect or causal mechanism.


### Four-bin returned-page DSP/wait histogram

The earlier same-page counters showed DSP budget overruns coinciding
with an audout wait exceeding **2x** or **4x** PCM-page duration.
This hid the important converse: how many DSP overruns happened
while audout returned within 1x or between 1x and 2x, where there
was no severe service wait on that same page?

The joint telemetry now stores a **four-band, exclusive histogram**
for every successfully delivered PCM page: <=1x, 1..2x, 2..4x and
>4x normal audout wait. For both ordinary and first-after-synthetic-
scene-switch groups, it counts (a) all returned pages in each band
and (b) just the pages whose *own* preceding SEQ/SPU/resample
compute time exceeded its nominal block budget. The first console
report displays the DSP-overbudget four-bin distribution separately
for ordinary and scene-switch pages. The pre-existing >2x and >4x
joint counters remain available.

The verifier now directly matches each returned-page wait histogram
bin with the original backend measurement **minus** terminally
failed logical pages in precisely that bin. It also checks that the
four DSP joint bins sum to the independent compute-over-budget total
after subtracting the one permitted undelivered terminal page.
Derived >2x and >4x threshold joint counts must equal the exact
appropriate bin sums. Corrupting just one new counter, changing a
band without updating its dependent totals or overflowing a counter
causes the audit to fail rather than present FULL evidence.

A coordinated *plausible* change of multiple joint bins cannot
be disproved from aggregate backend and DSP marginals alone; the
regression explicitly acknowledges this limitation. Synthetic
tests cover all four wait bands, scene classification, 256 returned
pages, a terminal failed scene page and nonmutating overflow
guards. No raw PCM, human input history or copyrighted audio is
recorded. Counts do not themselves prove a click, delay cause
or glitch-free sound on physical Switch hardware.


### Manual A/B windows now include DSP and same-page audout co-occurrence

The fixed 32-returned-page listening lookback now carries one
bounded DSP overbudget bit per returned logical PCM page. The
window independently reports (i) any overbudget computation,
(ii) any page whose computation exceeded budget **and** its own
audout wait exceeded 2x nominal PCM duration, and (iii) any
such page with audout wait exceeding 4x. These are same-page
co-occurrences; separate events on separate pages inside the
same window do not count as a joint-page observation.

Screen 3/3 now shows **A / B / all** lookback-window counts for
each event. A is a user-selected possible anomaly, B is a
user-selected normal-sounding control. These windows may overlap,
and B is not an unbiased randomized control. Neither matching
counters nor an A marker proves a physical glitch.

The recorder validates the new DSP bit, subset relationships and
64-bit counter overflows atomically before mutating its ring.
It counts only returned logical audio pages; the exact per-page
DSP / DSP+wait>2x / DSP+wait>4x totals must reconcile with the
independent same-page joint audit before a FULL result is allowed.

The independent 4096-page chronological oracle exercises the
new window events at every 31/32-page lookback boundary and across
repeated ring wraps, including DSP and wait events straddling
pages 31–33. No PCM, input trace or copyrighted assets are
recorded or exported.


### Atomic returned-page joint telemetry and 32-page A/B ring

The native audout probe previously wrote two separate diagnostic
accumulators in order: the returned-page DSP/audout joint histogram
and the 32-page A/B listening ring. A corrupt ring entry or counter
overflow could cause the listening recorder to reject its update
AFTER the joint histogram had already incremented. Although the
final audit detected the difference, the in-memory diagnostics
were unnecessarily left inconsistent.

The new portable \`vh_audio_page_telemetry_record\` requires the
pre-update returned-page clocks and exact DSP/long-wait totals to
agree. It stages the small joint histogram, then attempts the
already-atomic listening ring observation, and publishes the staged
histogram only after the ring succeeds. On any error both objects
remain unchanged. No large ring copy, PCM data, time-series export
or extra audout callback is introduced.

A dedicated synthetic host regression exercises more than three
ring turns (100 returned pages), missing/duplicate counters,
illegal wait bands, categories, retry and DSP flags, a malformed
ring slot, joint histogram overflow, saturated listening-window
totals and success after restoring the original metadata. The
test is included in \`make test\` and \`make test-audio-stream\`,
and run separately under UndefinedBehaviorSanitizer by PCM CI.

The fix does not change the music/render/audio service order or
demonstrate sound quality. Physical Nintendo Switch observation
is still required. It only prevents a failed recorder from
creating a phantom DSP/audout event or inconsistent A/B ring.


### Exact raw audout call conservation in the final PCM run audit

The final native audio run auditor previously accepted a raw backend
service call count as long as it was **at least** the number of
logical submitted PCM pages. That lower bound did not reject a
stray unaccounted call. Each raw audout submission is either
rejected (counted as one failed submission) or accepts exactly
one logical returned PCM page; recoverable retry attempts do not
advance SEQ/SPU clocks or create another returned page.

The final validator now requires the exact equality

    raw audout calls - failed submissions == returned PCM pages

after an explicit underflow guard. This avoids 64-bit overflow,
rejects phantom or missing raw calls, and still allows up to
the configured bounded retries for a failed or recovered page.
It independently verifies that long-wait raw call counts do not
exceed raw calls, max raw call ticks do not exceed their total,
and a raw call's maximum wait fits in the maximum wait of at least
one logical PCM page.

The existing host recovery regression adds cases for one extra
raw call, one missing raw call, a saturated call counter,
impossible long-call/peak metadata, a terminal failed page
with unmatched raw calls, and recoverable/fully failed page
examples. This tightens integrity checks **only**: no audout
service behavior, sample generation, PCM or listening controls
change. Passing the audit does not certify acoustic quality.


### Recovered vs terminal retry-page conservation

The exact backend-call audit also reconciles page-level retry labels
with independent recovery callbacks. Every logical page with more
than one raw service attempt either succeeds via a recorded
recovery, or is an unrecovered terminal failed page. Therefore:

    retried logical pages - recovered pages <= terminal failed pages

and the successful recoveries can never exceed retried pages.
Each service restart attempt also follows a failed submission, so
restart attempts cannot exceed failed submissions.

The new regression intentionally lowers the recovery counter in
an otherwise complete 48-page run; this must fail instead of
silently claiming FULL accounting. The terminal three-failure
test now accurately marks its ONE failed page as retried and
records the TWO restarts, rather than assigning a retry field to
the wrong aggregate type. A transient test-compilation error in
the initial patch was corrected before this stage was accepted.
Neither refinement changes retry behavior or makes audible
quality assertions.


### Full returned PCM-page diagnostic transaction

A successfully released PCM page used to update its service-delay
scene bucket, then the PCM16 seam histogram, then the DSP/audout
same-page counters and the 32-page listener ring separately.
The latter two were already atomic, but a seam failure could
still leave an otherwise successful scene histogram update.
These diagnostic counters would be rejected at final report
validation, but unnecessary partial state remained.

The native audout probe now commits ALL FOUR logical returned-page
views through \`vh_audio_returned_page_telemetry_record\`.
It first stages the small wait-category and seam accumulators,
and then stages the DSP/wait histogram. Only after those records
succeed does it call the listener recorder, whose own checks
reject malformed ring data without mutating any state. It then
commits the previously staged structures without further
fallible operations. No music clocks, buffers or SD data are
copied, and the order and number of audout callbacks are unchanged.

A terminally failed page is a different case: only its failed
logical page wait bucket is updated, with no PCM seam or
returned-page DSP and A/B annotation. The portable transaction
regression now injects a failure in each of the four recorders,
asserts bytewise nonmutation of all four objects, and then
successfully retries the same diagnostic page after restoring
the original metadata. It runs in both Make host suites and
under PCM CI UndefinedBehaviorSanitizer. These are internal
metadata consistency guarantees; no physical-console acoustic
quality is implied.


### Last returned PCM page vs A/B ring tail integrity on early exit

After merging four returned-page diagnostic views into one atomic
transaction, the final audit still only compared their aggregate page
counts and latency histograms. The **most recent returned PCM page**
could be mislabeled in the 32-slot listening ring without changing
any totals: the ring's last wait band or PCM16 boundary step could
disagree with the corresponding final PCM seam. Such a contradictory
report must not be eligible for FULL integrity.

The new read-only portable
\`vh_audio_last_returned_page_verify\` compares the two page clocks,
the exact ring tail slot at \`(returned_pages-1)%32\`, the last
delivered page's normalized audout wait band and PCM16 inter-page
step, and the zero-seam special case of the first successful page.
An empty run must have no previous PCM metadata. It is checked
both before accepting a subsequent returned page and during final
validation. Report screen 2/3 now explicitly shows the tail audit.
Contradictory tail metadata fails closed as part of the PCM seam
audit, with no extra audio service operation or copied PCM data.

Critically, terminally **failed audout submissions do not update the
last-returned PCM seam or listener ring**: they only add a failed
logical page to the audout wait histogram. The new 96-page synthetic
regression crosses the 32-page ring wrap three times and tests a
failed final submission, valid retained tail, targeted single-field
corruption that leaves independent aggregate counts unchanged,
and bytewise nonmutation when a subsequent page is attempted from
an already inconsistent tail. It runs in the existing host and
UBSan telemetry tests. These checks are software bookkeeping,
not physical Switch audible-glitch measurements.


### HOME/sleep audout resume accounting and bounded fault matrix

The portable \`vh_audio_output_resume_recover\` helper (separate
from raw audio page submit retry) now rejects invalid preexisting
\`resume_recoveries > resume_restarts\` and guards each session
restart/recovery/failure counter BEFORE invoking a backend callback
that might require incrementing that unsigned field. An otherwise
saturated counter cannot wrap and falsely make a restarted session
appear unobserved. These checks do not touch music state, submitted
PCM pages, sound data or service callback policy.

The final audout evidence auditor now also rejects \`resume_recoveries
> resume_restarts\` independently of successful PCM-page counts.
A HOME/sleep resume never qualifies as a new returned PCM page.

Host fault injection now exercises: existing-session quick
focus-resume (one start with no reopened service); transient failed
start followed by successful bounded close/open/start; forced
HOME/sleep reinitialization with an initial open failure and
successful second attempt; failing stop/open/start; saturated
restart/failure/recovery counters; contradictory prior counters;
and a poisoned resume-recovery count in an otherwise successful
48-PCM-page run. The tests verify submitted PCM pages and frames
never change in ANY resume scenario. These are synthetic backend
callbacks; no actual Nintendo Switch sleep/resume measurements
have been performed.


### No-duplicate PCM handoff across simulated HOME/focus pauses

The portable audout recovery regression now submits eight distinct
synthetic PCM16 stereo pages to a mock backend, checking every
accepted logical page's cumulative FNV fingerprint and the exact
scene-wait/raw-call accounting. It interleaves (a) fast focus resume,
(b) forced HOME/sleep reinitialization after a transient failed
open, and (c) a failed stop followed by successful force-reopen.
During each pause/resume interval it compares the before/after
raw submission count, accepted count, PCM fingerprint, native
SEQ/SPU/resampler clocks, wait histograms and submitted page/frame
statistics. They MUST all remain unchanged. One post-resume
PCM page suffers a simulated first submission failure and is
retried with its identical backing data: it still contributes only
one delivered page. Final \`vh_audio_output_verify_run\` accepts
the exact eight-page trace.

The same code also now fail-closes saturated or already impossible
raw submission/restart/recovery counters **before** contacting the
audout backend. When the failure counter reaches UINT_MAX after
a failed call, it refuses another retry callback instead of
allowing an uncountable new attempt. Tests cover saturation,
impossible relationships, unchanged input PCM and zero side
effects on preflight rejection. These checks may conservatively
reject near-saturated synthetic counters; they cannot establish
actual battery, focus, HOME or sleep behavior on physical Switch.

No original assets, audio captures, or user data are exported.


### Repeated HOME/focus resumes followed by terminal PCM-page failure

A new independent, portable host regression
\`tests/test_vh_audio_resume_abort_telemetry.c\` exercises the
combined production \`vh_audio_output_submit_recover\`,
\`vh_audio_output_resume_recover\`, returned-page
\`vh_audio_returned_page_telemetry_record\` and terminal
\`vh_audio_output_record_scene_page\` paths through a simulated
audout backend. It sends **70 distinct copyright-free PCM16 pages**
to the mock service and verifies every returned page's checksum,
one-to-one delivered-page accounting, audout raw-call counts,
PCM seam histogram, last-32-page A/B ring and last-returned PCM
tail. Seventy pages cross the 32-page ring boundary twice.

At six returned-page boundaries the test pauses and resumes the
service, including fast focus-start, a forced reopen with one
temporary open failure, a stop failure followed by a successful
reopen and **two immediate repeated pause/resume cycles** before
any new PCM submission. It snapshots per-page audio telemetry
across each pause, proving that it cannot be mutated by session
recovery or generate a duplicate delivered page. Two pages also
require a raw submission retry using their exact original
PCM buffer; neither is counted as two delivered pages.

Next, an additional rendered page fails all three permitted audout
submission attempts. Its backend wait histogram records exactly
one terminally failed logical page, while the accepted-page checksum,
last PCM seam, DSP/wait counters and A/B ring tail must remain
identical to the preceding 70-page state. A subsequent forced
session reopen likewise cannot deliver that abandoned PCM page
implicitly. An independent zero-delivery + terminal-failure
scenario remains INCOMPLETE instead of falsely reporting FULL.
The new test runs in both Make host suites and in PCM CI under
UBSan. This is synthetic state-machine evidence only: physical
Switch sleep/resume and audible quality are still unverified.


### Retained descriptor ownership across immediate pause after retry recovery

The host audout callback simulator now models a descriptor with a
foreign pointer or NULL returned from an otherwise successful
backend call as **still in flight**, not released. A subsequent
submission is illegal until a *successful* \`stop\` drains or
discards that descriptor. Failed stops preserve this in-flight
state, and the test aborts if an unsafe submit/close is attempted.

A two-page synthetic trace injects a foreign return and then a
NULL return for the SAME immutable PCM buffer, each followed by a
successful stop/close/reopen and re-submission. Once the correct
descriptor returns, it counts as exactly ONE delivered page.
The service is paused IMMEDIATELY, forcibly reopened despite a
temporary open failure, then paused and quickly resumed again
without any new PCM. Backend calls, accepted-page fingerprint,
timing, page-wait bins and SEQ/SPU/resampler clocks remain
unchanged across both pause/resume operations. A second, distinct
page is then submitted and delivered once, and exact whole-run
accounting is checked.

A separate negative trace returns a foreign descriptor and then
fails to stop the device. The descriptor remains outstanding;
neither the retry path nor a failed forced resume may close,
requeue or mark it as returned. Only an explicit successful stop
releases the simulated ownership before reopening. No abandoned
page is implicitly delivered and the incomplete-run audit is
consistent with one failed raw submission.

This is a STRICT host mock of a possible outstanding backend
descriptor, NOT proof of libnx hardware queue ownership, stop
drain semantics, HOME/sleep behavior or audible Switch quality.
It adds no retained PCM dumps, new backend API calls or changes
to physical music playback.


### Three consecutive failed stop calls: in-flight PCM ownership remains locked

The portable audout mock now permits a configurable count of
consecutive \`stop()\` failures while an unreturned PCM descriptor
remains in flight. The new regression delivers a first PCM page,
submits a distinct second page whose backend returns the *wrong*
descriptor, and injects THREE failed stop attempts: one inside
the submit-retry helper, then two separate forced session-resume
calls. Neither of those failures may close/open the device,
release or retransmit the original PCM buffer, change its input
checksum, add an accepted page or alter backend wait counters.

The fourth stop succeeds and is the ONLY modeled event that
releases the outstanding descriptor. A successful force reopen,
followed by another immediate pause/focus resume, delivers no
previously accepted or aborted PCM page. An entirely NEW page
then advances the accepted checksum and delivered-page count
once. The final audit reports **INCOMPLETE** with 2 accepted
pages and one terminally failed logical page: this preserves the
original failed event rather than incorrectly converting it into
a successful delivery after reopening.

A companion scenario injects SIX successive stop failures
(one service retry, five forced resume calls). In-flight ownership
must remain blocked throughout; no restart, descriptor flush or
new PCM delivery may be claimed. The added checks are host-only
synthetic fault injection; they do NOT establish the real libnx
hardware stop/queue semantics.


### Fail-closed final audout stop and service close on forced shutdown

The native audout proof previously called \`audoutExit()\` even if
\`audoutStopAudioOut()\` failed during final cleanup. Because
\`audoutPlayBuffer\` can fail to return the identical descriptor,
such unconditional closure was not justified by the existing
conservative PCM backing-buffer ownership rule.

The new portable \`vh_audio_output_stop_close\` calls \`stop\`
and invokes \`close\` **only after confirmed success**. An
invalid callback table or failed stop returns an error without
calling close or altering music/page accounting. The Switch
audout proof now uses this helper for both failed initialization
cleanup and end-of-run cleanup, prints a concise warning if stop
cannot be confirmed, and cannot report a clean FULL run after
that failure. Its static 0x1000-byte PCM audio output buffer
remains allocated for the lifetime of the NRO even if the
service is left initialized until application termination.

The 70-page integrated mock regression additionally attempts
three *failed* final stops after a terminally undelivered page:
all three must skip close and leave the last returned A/B tail,
PCM seam, DSP/wait histograms, raw backend call count, accepted
checksum and recovered page accounting unchanged. The fourth
stop then succeeds, closes exactly once and likewise does not
convert the failed page into a returned one. Separate mock
tests cover invalid callbacks and repeated failed shutdowns.
These are fail-closed software ownership invariants, not
measurements of actual physical Switch buffer drain semantics.


### Zero-delivery shutdown, safe reopen and report verdict isolation

The integrated host regression now explicitly tests the edge case
of **no returned PCM page at all**. An all-failed audout logical
page makes three raw attempts; its single failed logical wait-page
count is retained, while every returned-page seam, DSP joint
bucket and the 32-slot A/B ring remains empty. Two consecutive
final-stop failures must not call close or create a page. The
third stop succeeds and closes the service once; only an
explicitly separate open/start can create a new backend session.

Even after that reopen the raw audio call count and returned-page
statistics must stay unchanged. A NEW, distinguishable PCM page
may then be returned exactly once: it has a **zero first-page
PCM seam** despite the earlier fully rendered, unreturned page.
The final run auditor and on-device report evidence function
must still say **INCOMPLETE** because the failed logical page
has not disappeared. The same procedure in an independently
reset, valid one-page session is allowed to report FULL. Thus
the test distinguishes a clean new run from an accidental
reset of failure evidence within an interrupted run.

The test is already part of both Make host suites and the PCM
CI UBSan stage; it requires no new external dependencies,
game data, PCM recordings or calls to the real Switch audio
service. This remains software accounting evidence only.


### Three-scene synthetic PCM continuation with retained audout failures

After a first entirely undelivered PCM page, failed shutdown
attempts, successful service close/open and one newly accepted
page, the integrated host test now delivers nine more distinct
generated PCM pages in the **same run**. Two labeled synthetic
scene switches occur at returned-page indices 4 and 8; a
transient service submission failure on page index 6 retries
the *identical* already-rendered buffer. Final totals: ten
successfully returned pages, fourteen raw calls, four failed
raw submissions and two completed synthetic scene switches,
while the initial failed logical page remains in the ordinary
wait histogram and the final status stays **INCOMPLETE**.

For each page, the test verifies source-labeled scene categories,
two independent returned-page DSP/wait accumulators, exact PCM16
seam bands, the A/B ring last returned page and raw submission
counts. Directly after each scene-switch page, an audout stop/
reopen verifies all PCM histories, clocks, raw call timing,
accepted checksum and preexisting failure statistics remain
unchanged. Injected loss of a previously failed logical page,
a failed raw service submission or a completed scene-switch
count must instead produce INVALID integrity. This exercises
synthetic cue boundary bookkeeping, not original copyrighted
SEQ/VAB music or real physical Switch audio.


### Decoded PS1-format VH/VB and SEQ through native audout telemetry

A new independent, portable integration regression
\`tests/test_vh_decoded_vab_audout.c\` produces two small **synthetic
but format-valid PS1 VH/VB banks**, decodes their VAG ADPCM via
\`vh_native_vab_load\`, uses the production VAB resolver and
\`vh_native_seq_advance_block\` to drive SPU/STUDIO_C, then
resamples 44.1 to 48 kHz and calls the same
\`vh_audio_output_submit_recover\` and atomic
\`vh_audio_returned_page_telemetry_record\` functions as the
Switch audout proof.

Four eight-page scenes alternate decoded sample banks. Before
each actual \`vh_native_seq_switch_scene\`, the preceding audout
page must already have been returned. Focus/sleep service
reopen cannot submit a page or alter the 48-kHz resampler clock,
PCM seam accumulators, joint DSP/wait counts or the A/B ring.
Scene switching must detach all borrowed PCM voice pointers
from the previous bank and preserve the reverb history. The
next note must resolve to the new bank, not the old arena.

Each bank-change first page and one ordinary page gets an
intentional failed raw call, followed by a retry of the SAME
rendered PCM; neither SEQ/SPU nor the resampler may advance
during retry. Every returned page reconciles wait category,
ring scene/retry metadata, DSP overlap and PCM16 seam. An
additional terminally undelivered page after the 32 fully
returned pages increments only the failed logical-page wait
bucket. The audit must report INCOMPLETE without modifying
the final previously returned PCM seam, 32-slot ring or DSP
joint accumulator.

This connects actual format decoders to the audout path with
copyright-free synthetic fixtures; it does NOT load, distribute
or claim to have tested original Vandal Hearts game music,
and it does not validate libnx hardware acoustics.


### Independent callback-free PCM replay for decoded VH/VB scene transitions

The decoded synthetic VH/VB/SEQ→SPU→44.1-to-48-kHz→audout
integration test now also runs a SECOND, independent sequencer,
SPU/reverb memory and resampler state. The reference uses the
same immutable decoded bank input but never enters an audout
callback or recovery path. At each of 32 pages and the 33rd
terminally unreturned page, the two pipelines must produce
exactly the same SPU stereo samples, output frame count and
bit-identical 48-kHz PCM16. It also keeps independent per-bank
page checksums, a full returned-page checksum, decoded-bank
pointer checks and each first-after-switch PCM boundary step.

The callback path intentionally inserts failed raw audout calls
and reopens the device; the reference does NOT. Recovered
submissions must use their original rendered PCM with zero
resampling or SEQ/SPU advancement. A one-sample mutation is
explicitly injected into the reference output after 32 pages:
the bytewise comparison must detect it and then pass after the
original sample is restored. This ensures the verification
actually detects PCM changes rather than checking only counters.

This is a **service-independent replay differential**, NOT an
algorithmically independent PlayStation decoding oracle: both
pipelines share the same native decoder code and format-valid,
copyright-free synthetic VH/VB/SEQ fixtures. Existing separate
Python differential unit tests cover narrower VAB resolution
and STUDIO_C math; neither these host fixtures nor CI can
prove audio accuracy against the original game or physical Switch.


### Independent Python SPU-ADPCM oracle for decoded, reverb-enabled VH/VB bank switching

The decoded synthetic VH/VB→SEQ→SPU→audout fixture previously
checked wet-tail preservation while the chosen tone's VAB reverb
send bit was not active. Its synthetic tone now explicitly sets
VagAtr.mode bit 2, and the integrated C test asserts that the
native VAB resolver returns \`reverb_send=1\` for both banks.
The separate callback-free C PCM replay remains a service
isolation comparison, not an independent codec reference.

The already-installed \`tests/test_native_vab_python_reference.py\`
now constructs **the exact two synthetic banks** used in the
C scene-switch integration, independently in Python. Its
\`tools.decode_spu_adpcm.decode_spu_blocks\` implementation
decodes both 16-byte ADPCM blocks in each bank (56 signed 16-bit
mono samples) separately from the native
\`vh_native_vab_load\` / C ADPCM decoder. The full 56 decoded
samples are compared individually, including both ends of the
two-block predictor history, the loop-start and repeat-end
metadata, and the resolver's decoded PCM pointer. A single
changed ADPCM nibble is independently decoded both ways and
must produce a detectably different result. The bank selection
is then exercised for 16 alternating scenes without mutation
of either bank's borrowed PCM arena.

Python reference checks are already invoked by \`make test\`
and \`make test-audio-stream\`, both part of core CI and the
native audio NRO build. The reference is independent at the
ADPCM *decode* stage, not a complete independently implemented
SEQ/SPU/ADSR/resampler PS1 emulator, and the synthetic fixture
does not prove original soundtrack matching.


### Algorithmically independent Python wet-tail check at VH/VB scene boundaries

The standalone Python STUDIO_C reference is now also driven by
**independently decoded ADPCM PCM16** from the two exact synthetic
VH/VB scene-switch banks. Four 3072-frame scenes alternate their
decoded samples without resetting the wet-tail history on either
the independent Python STUDIO_C model or the C implementation.
Every stereo reverb output sample is compared exactly, and at
each boundary the reference checks the prior scene's stored
buffer, delay cursor and FIR phase against the native module.
Nonzero accumulated history is required, ruling out trivial
all-zero-state equivalence.

Unlike the earlier C two-player PCM differential replay, the
Python ADPCM and reverb algorithms do not call the native C
codec/reverb routines to compute their expected outputs. These
separate verifications still do NOT constitute an independent
end-to-end implementation of SEQ scheduling, pitch, ADSR,
voice mixing or 48-kHz resampling and do not certify original
PlayStation hardware audio parity. No game assets or user music
are accessed. The affected Python test files are now explicitly
listed in PCM, native-audio and audout-NRO workflow path
filters, so subsequent reference changes invoke CI.
