# MAP02 Stage290 — first real guest 22ms CPAL lifecycle/error observation

**Research-only Draft / DO NOT MERGE.** Child of verified [Stage289 Draft #353](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/353), frozen at `ce8e2863d6b0e51217e21a8de49d0c202c194c5b`. No production Nintendo Switch game source, licensed PS1 ROM, music or original audio data are uploaded or modified.

## Real prerequisite: newly compiled ELF boots

[Stage287 Release build #39492859181](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39492859181) compiled an actual source-pinned NeXium Linux x86-64 ELF with new Stage286 opt-in CPAL lifecycle/error counters, **292,009,536 bytes**, SHA-256:

`c3803abd7a06fd4081d7d49367cfbd2cedc4bb1650996f1e09fca5788c881b65`

[Stage289 no-ROM GUI boot #39494803753](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39494803753) independently verified that exact ELF, its manifest/source hashes, and obtained a real visible GUI screenshot using software Vulkan/Xvfb and a 48-kHz virtual PulseAudio sink. This does not exercise the game's CPAL stream.

[Stage288 generated-only parser #39493822174](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39493822174) separately passed 18/18 synthetic tests for the new lifecycle `L` CSV schema, without runtime evidence.

## One real guest positive-control first

Stage290 downloads the **exact Stage287 ELF artifact** and the earlier **same original generated-only research NRO**, checking byte-level ELF SHA-256, compiled source/research/source overlay SHA and guest NRO0 checksum/provenance. It does not compile new game or emulator code.

The runner then reuses the previously successful Stage280 Rustarmic 22-ms guest test procedure unchanged except for stage-specific output paths: identical virtual X11/software Vulkan, 48-kHz stereo Pulse null sink, same NRO, controller input sequence, screenshot timing and `NEXIUM_CPU_BACKEND=rustarmic`. The requested `PULSE_LATENCY_MSEC=22` is a *hint*, not a measured CPAL callback period.

It independently preserves three complementary observations:

- **Guest optical**: real pre-input/prejoin/final/late screenshots; strict eight-page guest descriptor/PCM CRC-8 final receipt, which cannot be faked by a valid host trace.
- **Host audio**: real raw 48-kHz stereo PCM16 capture, SHA-256, byte/sample count and nonzero sample count. Virtual PulseAudio does not imply physical Switch speaker sound.
- **New CPAL lifecycle**: actual Rust `L,monotonic_ns,state,error_count,cpal_entries,cpal_returns,output_frames,consumed_frames,audioout_appends,accepted_frames,releases` samples via an absolute opt-in `VH_MAP02_CPAL_TRACE_PATH`. The independent Stage288 L parser checks bounded time series against real first-controller-input and final guest screenshot monotonic clocks, distinguishing prior `stream.play` success from observed new callbacks, a build/play failure or an increasing CPAL error count.

All available raw evidence is uploaded even if a guest CRC or lifecycle audit fails. The workflow does **not** classify a failed guest as successful solely because the host callback ran.

## Scientific interpretation

A successful 22ms positive control would establish that this **new and changed binary** can boot the guest and emit its lifecycle/CPAL/AudioOut/virtual PCM evidence. It would not yet explain what happens with 21ms, prove a permanent deadlock or demonstrate a production fix.

Next: hold this Stage287 ELF and guest NRO exactly constant, run a bounded 21ms control and then repeat paired tests as needed. Preserve the original Stage284 six-run baseline from the **old different ELF** rather than treating the new probe as transparent to scheduling.

**No original game ROM or soundtrack in public GitHub. Do not merge.**
