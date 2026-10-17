# Stage 260 — independently pinned integrated audout NRO boots in NeXium

**Result: `EMULATOR_GRAPHICS_AND_INPUT_PASSED`. Native audible music and physical Nintendo Switch remain `NOT VERIFIED`.**

## Build identity (checked before the emulator launch)

- Pinned source run: [39034607288](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39034607288)
- Pinned source artifact: `12101269376` / `vandal-hearts-tactical-with-native-music`
- NRO build SHA: `63c718679715adc809a3feb8845a15a37e645488`
- NRO SHA-256: `8068eeef36cc1b3751bb4a9d320de5477c85687af018f1323dbba0b33d26b7ad`, size 266296 bytes.
- Emulator workflow commit: `ec395598c9c408fd24899c7d9b307e6b6a7d0b80`; this is **not** the NRO build SHA.

The GitHub Actions workflow [39035815166](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39035815166) completed **successfully**. Its original `run-in-emulator` job `117405455112` successfully downloaded the pinned *cross-run* artifact, executed `verify_switch_integrated_nro_preflight.py` and recorded `READY_FOR_SD_TRANSFER_REVIEW` and the exact expected hash **before launching the emulator**. The job then installed NeXium nightly and ran the application with Mesa's Lavapipe `lvp_icd.json`, headless Xvfb and screenshots. Build job `117405240565` also completed successfully, but its own freshly built NRO is **not** substituted for the pinned candidate in the emulator job.

## Original emulator evidence

- [NeXium runtime artifact `12102610376`](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39035815166): screenshots, emulator stdout/stderr, `runner.log`, pinned `integrated-nro-preflight.json`.
- Screenshot size: 1280×720.
- Changed pixels from initial to moved state: **4973** (strict colour delta >24).
- Yellow cursor pixels on the three tracked cells: **(371, 0, 0)** before versus **(0, 0, 640)** after two Right presses.
- Selection movement-range highlight: **3660** pixels when selected versus **0** after cancel.
- Hero pixels on initial/destination tracked cells: **1190** before, **0** remaining at source and **1190** at destination after a legal move.
- CI also required and passed captures/positive pixel checks for out-of-range movement refusal, enemy-tile refusal, and post-Plus capture. These prove observed prototype interactions, not original PS1 gameplay.
- The full emulator job returned `success`; screenshot data and metrics were also independently inspected from the downloaded evidence ZIP.

## Limitations and next steps

1. The screenshot shows the minimalist tactical homebrew prototype, **not** a reconstructed retail Vandal Hearts MAP02 scene or finished HD remake.
2. The guest emulator log includes `ALSA ... cannot find card '0'` and `Unknown PCM default` on the headless runner. **Neither audible music nor non-silent PCM capture has been established.** `audout` setup or an on-screen music label must not be interpreted as actual sound output.
3. Emulator FPS counter, screenshot pixels and job `success` do not establish hardware Switch audio, sleep/HOME, removable SD persistence, real latency or audio quality.
4. A future emulator audio stage must provide an explicit working audio sink, record waveform/PCM and validate non-silence with independently specified thresholds; report separately from the passing graphics/input check. A null sink is not proof of audible playback.
5. The hardware acceptance status stays exactly **`HARDWARE NOT TESTED`**.
