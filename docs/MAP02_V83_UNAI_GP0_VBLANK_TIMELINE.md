# MAP02 v83 — actual Unai renderer GP0 handler observations between emulator VBlank edges

Stacked Draft based on v82's successfully validated pinned emulator
(`notaz/pcsx_rearmed@8b6c163575e6ce9a0537553e0d4ed4225315955e`).

## Why v83 adds a new event kind

v80 recorded GP1 MMIO input and DMA2 invocation, which do not establish that
the software GPU renderer handled a primitive. In the pinned Unai renderer,
`plugins/gpu_unai/gpulib_if.cpp`, v83 inserts an opt-in observer
**after** the original renderer's command switch on the non-legacy path.

Accepted event `gp0_unai_handled` records the 32-bit command header for
commands known to have reached the Unai handler: fill 0x02; polygon, line,
sprite and rectangle families 0x20–0x7f; state E1–E6. An incomplete
packet that terminates before the switch does not qualify; GP0 A0 uploads,
C0 reads and other gpulib-handled commands are deliberately excluded.

Every event shares the native bounded v80 sequence with emulator VBlank and
the submitted GP1/DMA2 records. The Unai callsite has **no authenticated
emulated CPU cycle or frame**; its JSONL `cycle=0,frame=0` placeholders
are explicitly unknown. Only the *shared monotonically increasing sequence*
attributes an event to the interval between two observed VBlank callbacks.
No estimated GP0 CPU timestamp may be invented.

## v83 runtime gate

Opt-in `--vh83-unai-gp0-smoke` executes the signed synthetic v78
four-phase MIPS scene, with the real pinned GPU and real
`psxRcntUpdate()` VBlank callback. It requires:

- Four genuinely observed emulator VBlank-start events.
- v78's exact native GPU VRAM oracle (2,380 samples, 499 guards per phase).
- At least two GP1 MMIO submissions and at least one handled Unai GP0 event.
- Zero dropped events from the bounded 4096-entry recorder.
- Private v82 exclusive disk publication with read-back exact byte comparison.
- Strict v82/v83 event-parser validation of opcodes, sequences, and event counts.
- Failed duplicate output must leave the original report unchanged.

GCC and Clang pinned emulator build+runtime CI is provided; **do not
claim passing results before the actual workflow is green**.
Only aggregate status artifacts may be uploaded, never the private
trace, executable, VRAM dump, or proprietary game assets.

## Known limits

Unai post-switch execution proves the renderer **handled the GP0 command
header**; it does not independently prove a pixel changed, that drawing
wasn't clipped, the precise timing inside the handler, or that this is
hardware-exact PlayStation behavior. The legacy Unai renderer and asynchronous
GPU paths are not covered by this specific observer. GP0 A0/C0 remain
gpulib-owned, and their individual processing is not demonstrated here.

`physical_ps1_vblank_verified=false`.
`retail_video_frame_correspondence_proven=false`.
`original_retail_MAP02_verified=false`.
`native_vram_write_trace_verified=false`.
`HD_replacement_approved=false`.

No retail assets are committed and the Switch HD path remains disabled.
