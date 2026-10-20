# MAP02 — source-pinned second native GPU window LoadImage path

The existing optional native GPU recorder can store **two sequential
64-event windows** from one original PC-port process. Each window has its
**own** local event steps `0..63`; their canonical private filenames are
`gpu-NNNN-vram.bin` and `gpu-NNNN-upload.bin` **within** their respective
private `window-000`, `window-001` directories.

## Discovered issue

The original instrumental C helper correctly reset the **snapshot** name
to `local_seq`, but used the **global** event `seq` for `LoadImage`
upload basenames. For an actual second-window post-LoadImage record at
global event 65 and local event 1, this meant:

- expected by `verify_map02_native_gpu_windows` and
  `verify_map02_native_gpu_capture`: `window-001/gpu-0001-upload.bin`;
- actually emitted previously: `window-001/gpu-0065-upload.bin`.

As a result a valid source-generated LoadImage transfer appearing in the
second window **could not pass the independent auditor**, even with correct
complete 1-MiB BGR555 snapshots and a valid upload payload. That would
block progress toward real MAP02 source/native GPU capture.

## Narrow correction

The pinned-source instrumenter now formats the upload basename using
`local_seq`, matching the names already used for VRAM snapshots and
the auditor's strict per-window upload checks. For a single-window
capture, `local_seq == seq`, so the legacy on-disk structure and capture
format do not change. No event limits, recording size budgets, private
directory policies, source/PC GPU drawing behavior or production game
code are changed.

## Regression coverage

The new synthetic two-window test constructs **66 ordered events**
(64 events / 32 DRAW pairs in window 000, and 2 events / one LoadImage pair
in window 001), with full 1-MiB invented VRAM snapshots and one 16-bit
upload. The test requires:

- local upload `gpu-0001-upload.bin` for second-window global event 65;
- intact 32 cross-operation VRAM endpoints including the window boundary;
- correct source event frame (the transfer is in frame 6 before target
  DrawOTag frame 7), event counts, draw-pair/transfer-pair partition;
- explicit lack of any retail PS1/MAP02 authenticity claim;
- rejection when the log/upload is changed to the **incorrect legacy
  global** filename `gpu-0065-upload.bin`.

The dedicated GitHub Actions job additionally generates the exact
source-pinned optional `libgpu.c` recorder from the immutable public PC
port (`14552fffa0e0b47e02b57592e274fc6e7a649923`), compiles it as an
actual C object in two-window mode with the upstream headers, and proves
the recorder symbol is absent from the non-opt-in baseline object.

All tests use invented VRAM only; the original user's disc is never read,
uploaded or included in CI. The 128-event upper limit and any overflow
remain strict rejection conditions. This does not prove the complete
original MAP02 scene, source-indexed full game render, PS1 GPU pixel
equivalence, macOS Catalina runtime or Nintendo Switch gameplay. Further
real owner-local capture and independent source GPU window linking are
still required. Keep Draft; no merge.
