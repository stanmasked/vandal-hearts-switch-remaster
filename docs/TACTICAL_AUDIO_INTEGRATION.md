# Tactical prototype: nonblocking native music integration (stage 176)

The original tactical homebrew `source/main.c` now links the native
musical SEQ/SPU/STUDIO_C/resampling engine **in the same NRO** as
its framebuffer/input prototype. It is still a generated 8×6 grid and
does not implement the original game's missions, menus or soundtrack.

## Real game-state triggers, not fabricated gameplay events

The currently implemented game state has only these UI modes:

| Existing game event | Requested music cue |
| --- | --- |
| Hero not selected, cursor navigation | `VH_GAME_MUSIC_FIELD` (1) |
| A selects the hero | `VH_GAME_MUSIC_HERO_SELECTED` (2) |
| B cancels selection | `VH_GAME_MUSIC_FIELD` (1) |
| Valid move is confirmed | `VH_GAME_MUSIC_FIELD` (1) |

Walking the cursor, failed movement and repeated input events do not
change the scene request. The actual `VhGameState.hero_selected`
after `vh_process_input` is the only input to this mapping.
**Victory, defeat, a new mission or an intro scene are not yet
gameplay states**, and are deliberately not simulated as if they were.

## Audio architecture

```text
libnx main thread                         dedicated libnx worker thread
-----------------                         ----------------------------
padUpdate + vh_process_input
       |
compare old/new hero_selected
       |
atomic store: desired scene -----------> atomic load: latest desired scene
                                         scene cue validation
framebufferBegin / draw_frame            8-block fade / note state reset
framebufferEnd                            pQES -> 20 SPU voices -> Gaussian
                                         -> ADSR -> STUDIO_C -> 44.1k PCM
                                         -> 48k PCM resample
                                         -> audoutPlayBuffer [blocking]
       |
  repeated gameplay frames               [blocks without stalling gameplay]
       |
  Plus / exit
atomic running=0 ----------------------> finish current audio block, stop audout
threadWaitForExit [shutdown only]
```

`source/vh_game_music_mailbox.c/.h` implement a C11 atomic
**latest-request-wins mailbox**. Gameplay only publishes changes;
it never waits, locks the audout service, touches PCM, or runs
VAB/SEQ parsing. Audio alone invokes `vh_music_scene_request()`
and `vh_music_scene_render()` to preserve voice ownership,
fade continuity and STUDIO_C state. Requests received during
fade are retried at the next audio block; they do not interrupt
the middle of an existing fade.

`source/vh_switch_game_audio.c/.h` owns the libnx worker thread and
audout session. The 4096-byte output buffer is page-aligned,
static, and large enough for the published AudioOutBuffer length.
SPU, FIR work area, source PCM and the 44.1k→48k rate-converter
also use static storage to avoid Switch thread stack pressure.
When audout cannot initialize, the game remains usable without
audio; the on-screen status shows `AUDIO ERROR`.
`vh_switch_game_audio_stop()` joins the worker **only on game exit**.

The two pitches and short synthetic pQES streams were authored
for this technical prototype. They are not Vandal Hearts
compositions. The separate diagnostic audio NRO still supports
user-owned local `music.seq/music.vh/music.vb`, but the integrated
game prototype does **not yet** select original VH/VB banks by
gameplay event. All samples/SEQ embedded in this prototype are
synthetic and distributable as a test fixture.

## Regressions and build

`tests/test_vh_game_music_mailbox.c` feeds real portable
`vh_process_input` actions through the scene mapping,
tests no-change cursor frames, A-select, valid move, B-cancel,
invalid ID rejection, 100,000 latest-wins atomic stores,
and concurrent C11 producer/consumer stress. The host
`Host SPU audio regressions` workflow compiles strict C11
and UBSan variants.

The dedicated `Switch tactical prototype with integrated audio`
workflow builds and validates the **main** framebuffer NRO using
devkitA64. Its downloadable artifact is
`vandal-hearts-tactical-with-native-music`, whose internal file is
`vandal-hearts-prototype.nro`. This differs from the standalone
`native-audout-music-nro` used for audio-only diagnostics.

```sh
make build/test_vh_game_music_mailbox
./build/test_vh_game_music_mailbox
make verify-nro
```

All previous synthetic audio regressions and long-duration
SEQ/SPU/rate-conversion tests remain available through
`make test-audio-stream`.

**Hardware acceptance outstanding:** confirm audible output,
graceful shutdown, controller responsiveness during active
STUDIO_C effects, output-device behavior after suspend/resume,
and observed CPU/underrun statistics on a physical Switch.
CI cross-builds and NRO header verification do not prove
these behaviors.


## Applet focus, HOME/sleep and resume recovery (stage 177)

The main tactical NRO now has a cooperative **audio pause/resume gate**
rather than continuing to advance native music while the applet loses
focus. This uses libnx `appletHook()`, with
`AppletHookType_OnFocusState` and `AppletHookType_OnResume` callbacks
executing on the main applet message-processing thread.

The callback **only publishes C11 atomics** through the extended
`VhGameMusicMailbox`. In particular, a focus change is never allowed
to call an audout service, decode a VAG, lock a PCM buffer or wait for
the worker from the input/framebuffer loop. A direct
`appletGetFocusState()` refresh after `appletMainLoop()` also
covers the first interactive frame after libnx resumes normal
execution in applet modes where no separate focus notification
was processed beforehand.

The dedicated audio thread now handles the lifecycle:

- **Out of focus:** after any already submitted blocking buffer
  finishes, stop `audout` once and enter a bounded 16-ms idle sleep;
  do not render any new 512-frame SEQ blocks or advance SPU reverb,
  decoded sample playback or 44.1→48-kHz resampling.
- **Return to focus:** start the audout output session on the audio
  thread, then continue using the **same** SEQ/SPU/ADSR/reverb state
  and resampler clock; do not start the track over.
- **Explicit OnResume:** increment an atomic resume serial. This
  forces an `audoutStopAudioOut()` / `audoutStartAudioOut()`
  cycle even if default system-wide applet suspension prevented
  the worker from observing the preceding loss of focus.
  `appletSetRestartMessageEnabled(true)` is requested **only** for
  `AppletType_Application`, then disabled on normal exit. Unsupported
  applet/launch modes keep their native focus handling policy.
- **No OnResume delivered:** a rising background→foreground focus
  edge in `vh_switch_game_audio_set_focus()` also publishes a resume
  serial. Ordinary per-frame in-focus polling never increments it,
  preventing continuous restart of the audio service.
- **Output-service state reconciliation:** if a start/stop operation
  returns an error but `audoutGetAudioOutState()` confirms the
  target state is already reached, audio continues safely. Other
  audout failures terminate the audio worker with a negative status
  rather than looping on a potentially invalid service.
- **Latest-wins scene selection:** scene changes requested while
  suspended remain pending in the mailbox and are applied after
  playback resumes. Transition requests still respect the
  pre-existing eight-block fade ownership protocol.
- **Shutdown:** `appletUnhook()` occurs before the audio thread is
  asked to stop; the only thread join is after leaving the
  framebuffer loop.

The diagnostic on-screen text can now show `AUDIO PAUSED`,
`AUDIO ERROR`, or the active tactical music mode. An
unrecoverable `audout` service error leaves the visual prototype
usable while the audio worker reports a negative status.

Host regressions include: focus toggles concurrent with scene
requests; an explicit `OnResume` generation that is **not**
incremented by normal frame-by-frame focus sampling; a
3000-iteration focus-loss period; and assertions that no
SEQ/SPU/STUDIO_C/48-kHz counters advance until the game becomes
focused again. The follow-up test verifies the last pending scene,
fade completion and repeated resume without track restart.
See `tests/test_vh_game_music_mailbox.c` and
`tests/test_vh_music_focus_resume.c` under strict C11 and UBSan.

**Important limits:** host tests simulate focus policy and clocks,
not actual HOME-menu/standby behavior of the Switch audio service.
Applet focus notifications vary by launch mode, and a single
already-submitted 48-kHz audio buffer can finish when focus is lost.
No physical device test has yet confirmed recovery from suspend,
correct audible transitions, or absence of crackling on resume.
The main tactical prototype still plays two **synthetic** cues.
Loading separate user-owned music banks for gameplay scenes is
not part of this change.

## Two preloaded user-provided music banks (stage 178)

The tactical NRO can now optionally preload **two independent**
user-owned pQES/VH/VB music sets before starting libnx `audout`.
The required SD folder structure is:

```text
sdmc:/switch/vandal-hearts-remake/audio/
  field/
    music.seq
    music.vh
    music.vb
  selected/
    music.seq
    music.vh
    music.vb
```

The portable `source/vh_game_music_banks.h/.c` manager loads the
`field` and `selected` triplets using the already validated
read-only `vh_audio_assets_load()`. **Both** must validate before
a music pack can become active. The two sets have independent,
persistent decoded PCM arenas and separate `VhNativeVab`
metadata; the SEQ resolver associated with each `VhMusicCue`
uses that cue's own bank. During an eight-block fade from one
scene to another, both banks remain valid and the old SPU sample
pointers are not freed until the entire audio worker exits.
All disk I/O, ADPCM decoding and bank validation happen on the
**audio worker before the audout service starts**, never in the
main game frame loop or inside the stream render loop.

**Failure policy:**

- Both complete sets absent → use two existing synthetic diagnostic
  cues (this is the only automatic fallback).
- Either set incomplete, corrupt, oversized or unreadable → report
  an audio error; no automatic synthetic substitution and no partially
  loaded user pack. The tactical framebuffer remains operational.
- Individual compressed VB files are bounded by the existing 8 MiB
  file limit, with an additional **12 MiB combined** compressed-VB
  budget for the pair. Its conservative worst-case decoded PCM
  staging can approach 42 MiB (plus the original VB/SEQ/VH
  bytes and runtime structures). Insufficient memory fails cleanly.

The scene mapping is unchanged: ordinary tactical cursor navigation
requests `field`, while choosing the hero requests `selected`.
Exiting selection or completing a move returns to `field`.
The main/game thread publishes only a small atomic scene ID. It
never holds a bank pointer, decodes a VAG or calls an audio service.

The synthetic regression `tests/test_vh_game_music_banks.c`
creates an isolated temporary directory with two distinct
manufactured banks. It checks the all-or-nothing loading policy,
independent decoded PCM addresses and sample contents, preservation
of old memory during a fade, resolution of the new bank's voice,
zero overwrite of a live pack, missing and corrupt second bank,
and proper cleanup. It runs in host CI under strict C11/UBSan
and as part of `make test-audio-stream`.
The dedicated devkitA64 GitHub workflow links the updated **main
tactical** NRO with this scene-bank manager.

**Not yet established:** on-console SD mount and file I/O, available
RAM for a full-size pair, audible scene transitions with original
game banks, or handling of all real-game program mappings. The
file payloads and music are user-supplied; they are never embedded
in the NRO or committed to GitHub. The standalone libnx audio-only
diagnostic still has its older *single* `music.seq/.vh/.vb` path
and is independent of this two-bank tactical interface.

