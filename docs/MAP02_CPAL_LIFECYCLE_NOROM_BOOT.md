# MAP02 Stage289 — boot the **new** CPAL lifecycle NeXium ELF with no game ROM

**Research-only Draft / DO NOT MERGE.** Child of [Stage288 Draft PR #351](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/351), parent source `161236be2528b8621738ff23adfcb9d16a8b48a7`.

[Stage287 GitHub Actions #39492859181](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39492859181) **SUCCESS** created a distinct Linux x86-64 NeXium ELF with Stage274 original atomic CPAL/AudioOut counters and Stage286 opt-in lifecycle/error counters. Source-pinned upstream `nexium-emu/nexium@089562567a0a8760dfdd8420e1f57c35159a9219` (Rustarmic backend), tested lifecycle source SHA-256 `27014ef42f80300f62034d46219c5ac82b9fdc647d23a5c5417b6018548ad78b`, fixed Cargo.lock SHA-256 `e6e8fcb90624650afddd1f25327dd4e6b042b094e8336cb5f43d2dc370e28739`.

## Immutable new experimental ELF

**SHA-256:** `c3803abd7a06fd4081d7d49367cfbd2cedc4bb1650996f1e09fca5788c881b65`.

**Size:** 292,009,536 bytes.

The Stage289 workflow downloads the exact compiled ELF from successful Stage287 run #39492859181. Before execution, it independently rehashes all executable bytes; validates Linux x86-64 ELF format, size, opt-in reporter markers, and Stage287 source/build manifest (upstream Git SHA, lifecycle source SHA, research source SHA, Cargo lock hash, Rustarmic CPU backend and L-prefixed lifecycle trace declaration).

Next it uses only a Linux virtual X11 display, software Vulkan and a 48kHz PulseAudio null sink to **launch this exact binary without a game ROM or guest NRO**, requiring a visible NeXium window and a real screenshot. A failure remains **UNVERIFIED**, with logs retained; a green result can prove only the guest-free GUI starts.

## Important limits

The lifecycle reporter may not start without a game stream. No 21/22ms guest calls or CPAL L records are expected from this test. The first meaningful runtime experiment will need the **same exact new ELF** and previously SHA-pinned generated-only research NRO with `NEXIUM_CPU_BACKEND=rustarmic`, plus real guest optical CRC, raw 48kHz virtual PCM, and the already validated Stage288 **L-row** parser.

This code changes neither Vandal Hearts Remake gameplay/audio nor original game assets. It does not prove callback runtime activity, permanent audout deadlock, the cause of the 21ms behavior, original PS1 soundtrack fidelity or physical Nintendo Switch sound.

**Do not merge to main.**
