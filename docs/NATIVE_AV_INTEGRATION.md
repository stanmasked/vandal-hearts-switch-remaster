# Combined native libnx video and audout experiment

This is an experimental asset-free Nintendo Switch NRO. It is NOT the original
Vandal Hearts game or a playable native port.

## Integrated subsystems

- 1280x720 libnx software framebuffer and shared tactical grid/input helpers.
- Dedicated libnx worker submits deterministic stereo PCM16 via audout at 48 kHz.
- 800 stereo frames per audio block, 3200 active PCM bytes.
- AudioOutBuffer advertises a fully allocated and 4096-byte-aligned page.
- Animated heartbeat shows visual updates while the audio worker operates.
- Green sound status means audout initialized and no synchronous worker error;
  red means unavailable or error. Green does NOT prove audible playback.
- Plus exits; cleanup stops and joins the audio thread before closing audout.

## Build and test

Run with the official devkitPro devkitA64 plus libnx toolchain:

```sh
make test-native-tone
make native-av-probe
```

The native-av-probe workflow performs host tests, UBSan checks,
cross-compilation, NRO validation, and artifact upload. It does not depend
on SDL2, OpenAL or network package installation from pacman.

The host tests cover stereo sample agreement, 48000 generated frames per
second, phase continuity, numeric wrapping and rejection of undersized
output buffers without altering generator state.

This is a software integration test, not original music. Actual audible
sound, hardware audio timing, synchronized gameplay and whole-game
portability remain unverified. The existing SDL2 package CI blocker
is separate: the devkitPro pacman database synchronization returned HTTP 403.
devkitPro recommends preconfigured Docker images over installing
packages with pacman in CI. No attempt is made to hide that blocker.

## Emulator smoke test

The Native AV workflow includes a separate NeXium stage that launches the
compiled NRO and captures two video frames. The image validator requires
the expected synthetic hero tile, a green/red audout status rectangle,
and a changing heartbeat bar while the emulator is running.

A green status means the audio service and worker started without a recorded
synchronous error; it **does not** verify audible samples, correct timings
or uninterrupted PCM transport. Red is an explicitly visible audio failure
or unavailable-device state and does not prevent video diagnostics.

Only a verified hardware run with actual output recording could establish
audible playback. A passing framebuffer smoke test is not a playable port.
