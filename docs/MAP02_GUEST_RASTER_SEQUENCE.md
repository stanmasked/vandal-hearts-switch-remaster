# MAP02 guest raster sequence: observation, not proof of audout deadlock

Draft-only child based on [PR #239](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/239) exact head `21745a71f57ac3b174b68874fae7ff9157b4006c`. No C source edits, no NRO playback changes, no original game audio assets. This is an **independent GUI-evidence observer** of already-captured NeXium screenshots.

## Why a missing optical packet is not an automatic cause

The app's experimental `source/main.c` starts audio on its own owner thread and continues gameplay input/framebuffer work on the main thread. On exit the main thread calls `vh_switch_game_audio_stop()`. That function first calls `vh_game_music_mailbox_stop()` and then uses a **blocking `threadWaitForExit(&audio_thread)`**. Only **after the audio thread joins** does main render the opt-in `VHPRE001` eight-page receipt.

The guest PCM worker creates its resampled 557/558-frame stereo pages, hashes them, enters `audoutPlayBuffer`, then records descriptor return. At 21ms in earlier [run #39386868354](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39386868354) two experiments had only-zero virtual monitors and no final `VHPRE001` while two 22ms controls were CRC-valid with eight exact pages. **There are multiple possible failure points**: audio start/initialization, failure to advance to submit, blocked submit, join waiting on some other operation, or an unexpectedly incomplete user-input/exit sequence. A static screenshot alone cannot identify the culprit. In particular, an instantaneous PulseAudio `Buffer Latency` is *not* the available service queue capacity.

## Independent actual screenshot inspection

Downloaded authentic, unexpired previous evidence artifacts from #39386868354:
- 21ms repeat 1, artifact 12249005637
- 21ms repeat 2, artifact 12248232607
- 22ms repeat 1, artifact 12247764669

For each, cropped the fixed `(x0,y0,x1,y1)=(250,160,1180,690)` from three 1280×720 RGB screenshot frames: **before input**, **final**, and **five seconds after final**. This ROI excludes the top-left NeXium status overlay and does **not** inspect arbitrary copyrighted media. Observations:

| Trial | Changed gameplay-region RGB pixels, before→final | Final→late | Guest CRC | PulseAudio nonzero PCM16 |
|---|---:|---:|---|---:|
| 21ms r1 | 27,722 | 0 | UNVERIFIED | 0 |
| 21ms r2 | 27,485 | 0 | UNVERIFIED | 0 |
| 22ms r1 | 492,900 | 0 | eight pages matched | 521,783 |

The before→final image change in both 21ms failures demonstrates **a change in rendered pixels across the screenshot interval**, but **does not establish which game commands were accepted or whether the audio thread was progressing**. The final→late unchanged ROI shows an unchanged scene during the five-second observation window, but **does not prove an audout deadlock**: the app may have legitimately stopped updating or may be displaying a stable framebuffer.

## New read-only evidence reporter

`tools/report_map02_guest_raster_sequence.py` validates three true 1280×720 PNGs, crops that fixed ROI, computes canonical RGB SHA-256 and precise changed-pixel counts/bounding boxes for before→final and final→late. The CI writes `presubmit-guest-raster-sequence.json` with `if: always()` after the guest capture, **even when** the independent eight-page optical decoder correctly fails. It cannot turn a failed receipt green. The output explicitly states `actual_guest_audio_thread_progress_proven=false`, `audout_call_deadlock_proven=false`, and `neXium_guest_optical_receipt_verified=false` (the last is assessed **separately** by the strict `VHPRE001` parser).

Generated-only regression tests cover one intentional ROI change, excluded emulator UI chrome, late-frame movement and invalid 1280×720 dimensions. No changes to guest PCM generation, PulseAudio latency matrix, 48k monitor recording, NRO source SHA provenance or bitmap style.

## Further causal test (not performed here)

A separate **opt-in-only** guest trace would need to record state *before* `audoutPlayBuffer`, after it, and around thread shutdown, via atomic progress counters visible before join. Without such evidence the current diagnostics cannot blame a particular service call, the NeXium host audio backend, or libnx buffer ownership.

Keep this and every parent Draft, no merge; main and physical Switch speaker path untouched.
