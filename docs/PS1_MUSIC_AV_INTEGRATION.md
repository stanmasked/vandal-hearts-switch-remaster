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
