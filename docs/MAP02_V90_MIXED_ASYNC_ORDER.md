# MAP02 v90 — mixed asynchronous GPU A0/80/E6 worker-order verification

This v90 Draft stacks on successfully tested v89. The pinned upstream
`notaz/pcsx_rearmed` emulator revision remains
`8b6c163575e6ce9a0537553e0d4ed4225315955e`.

## Actual native worker order — NOT just queue acceptance

After all earlier signed synthetic MIPS phases, the four real *emulator*
VBlank callbacks, 2,380 original VRAM readbacks, and prior v86–v89
host controls pass, the host enables the real `USE_ASYNC_GPU` path and
submits a bounded synthetic interleaving of:

- A0 upload of red to synthetic source row 370, copied to destination A
- E6 mask-set followed by A0 upload of green to the same source, copied
  to destination B with the mask set
- E6 mask reset followed by two same-value A0 uploads of blue, copied
  to destination C

The **real GPU worker** appends only numeric semantic completion
labels to an atomic rolling hash *after* each appropriate original
`do_dma_write` and `do_vram_copy` returns. The expected sequence
is `(1,2,3,4,5,5,6)`. The 32-bit rolling hash (base 17) is
`27249034`, with exactly seven completed, ordered worker steps.
This fingerprint contains **no raw pixel bytes or game data**. It is
checked against independent async GP0(A0) and GP0(80) counters:
four accepted/completed A0 uploads, 32 real 16-bit stores (8 same-value),
three accepted/completed GP0(80) copies, 24 real 16-bit stores (0
same-value), and exactly one forced-mask GP0(80) copy.

Original `GPUfreeze` provides a full renderer sync barrier and pixel
readback. The three copy destinations and final source must match the
expected red, masked-green, and blue values **simultaneously**. This
proves the checked ordering/visibility within the pinned emulator,
not on electrical PlayStation hardware.

## Async-to-sync drain and callback handoff

After complete native GPU sync, the host disables GPU threading via the
original `plugin_call_rearmed_cbs()`, resets v86's original synchronous
gpulib transfer observer, and submits one A0 upload followed by two
identical GP0(80) VRAM copies. GPU readback must retain all three
asynchronously populated destinations and show the new source and
synchronous destination. The expected post-switch counters are
8 A0 stores, 16 copy stores, and 8 same-value copy stores.

Fourteen new aggregate event kinds are appended to the bounded private
native journal **on the main thread after the worker has stopped**.
The v90 verifier refuses reordered/duplicate/missing/forged counters,
worker hash errors, failing predecessor proofs, event drops and fake
cycle/frame ownership. CI still builds and executes the actual pinned
software renderer under both GCC and Clang, tests duplicate-write
refusal and checks that the secret journal bytes match the stored SHA256.
Only non-sensitive aggregate results may be publicly published.

The 384 warm-up primitives and mixed GP0 controls are explicitly
**host-injected synthetic probes after the VBlank oracle**, not game
MAP02 rendering. The worker proves only observed software code paths,
not GPU DMA timing, physical PS1 parity, original retail MAP02, Switch
HD renderer correctness, or all graphics commands.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`

Branch is stacked Draft-only and does not modify `main`.
