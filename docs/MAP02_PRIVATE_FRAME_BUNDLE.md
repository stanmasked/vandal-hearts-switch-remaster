# MAP02 — private frame evidence bundle (v1)

This is a local verification gate for user-owned MAP02 resources and an
opt-in GPU trace. It **does not** obtain game assets or run the original
game for you. No copyrighted map, VRAM dump or raw camera/event stream
belongs in this GitHub repository.

The verifier implements a concrete next step after
`source/map02_vram4_frame.h`: assemble complete inputs from a single
captured frame, confirm SHA-256 integrity, independently identify each
decoded source face, check real-format 4-bit VRAM addressing, and compare
screen corners, signed NCLIP and raw OTZ against the **compiled portable
PC-GTE reference**. It checks recorded BGR555 samples only when such
observations are supplied.

## Local input directory

Create a private directory containing exactly these required file names
(additional private files are not read):

| File | What it contains |
| --- | --- |
| `map02.decoded.bin` | Exactly 187264 bytes of the caller's decoded 616-record MAP02 buffer |
| `gpu-vram-le.bin` | Exactly 1048576 bytes, the caller's 1024×512 little-endian 16-bit GPU VRAM at the intended capture instant |
| `gpu-events.jsonl` | 1–32 JSON-line submissions with per-face source, GTE and GPU texture state from the *same* frame |
| `bundle.json` | Manifest containing matching frame IDs, pinned source baseline and SHA-256 hashes of all three source files |

The `bundle.json` schema is:

```json
{
  "schema": "vh.map02.frame.v1",
  "frame": 411,
  "vram_snapshot_frame": 411,
  "ot_size": 1024,
  "pc_source_commit": "14552fffa0e0b47e02b57592e274fc6e7a649923",
  "decoded_map_sha256": "<64 lowercase hexadecimal characters>",
  "vram_sha256": "<64 lowercase hexadecimal characters>",
  "events_sha256": "<64 lowercase hexadecimal characters>"
}
```

An optional `pc_game_binary_sha256` may record a fingerprint of the
actual local executable that emitted a trace. The verifier checks its
syntax, **not** its claimed identity. The example frame number is
illustrative, not a captured session.

Each JSON line has the following **shape only**, with synthetic numbers:

```json
{
  "stage": "map02_ft4_submit",
  "frame": 411,
  "register_frame": 411,
  "source": {
    "z": 8, "x": 19, "record_index": 243, "face_index": 0,
    "local_gfx": 241, "shade": 7,
    "indices": [0, 1, 2, 3],
    "vertices": [[0,0,512], [100,0,512], [100,100,512], [0,100,512]]
  },
  "gte": {
    "camera": [4096,0,0, 0,4096,0, 0,0,4096,
               0,0,0, 1310720,1310720, 256,256],
    "perimeter_xy": [[20,20],[70,20],[70,70],[20,70]],
    "nclip_mac0": 2500, "raw_otz": 128
  },
  "texture": {
    "u":240, "v":192, "w":15, "h":15,
    "tpage":5, "clut":31978,
    "mask_x":0, "mask_y":0, "offset_x":0, "offset_y":0,
    "probes": [{"u":241, "v":192, "bgr555":32799}]
  }
}
```

`gte.camera` comprises the **16 actual resident GTE values** taken
immediately before the face's RTPT:
9 row-major Q12 RT coefficients, 3 TR values, OFX/OFY in signed
16.16, H and ZSF4. The `source.vertices` are the four *local*
face vertices in source perimeter order; `gte.perimeter_xy` is the
corresponding four screen corners in that **same** order. The verifier
reorders them into `POLY_FT4` corner order 0,1,3,2, then checks the
source PC-GTE RTPT/NCLIP/RTPS/AVSZ4 calculations.

A `texture.probes` array is optional, with up to 32 original BGR555
color observations at UV positions **inside** the observed inclusive
UVWH crop. If missing, the report says **zero observed GPU texels
checked**; it never manufactures an observed color. The validator
still computes every 4-bit indexed VRAM sample in the crop and counts
zero and STP palette entries. Colors are not included in the report.

You can populate the hashes locally after collecting files:

```sh
python3 - <<'PY'
from pathlib import Path
import hashlib, json
d = Path("/private/map02-frame")
m = json.loads((d/"bundle.json").read_text())
for name, key in [
    ("map02.decoded.bin","decoded_map_sha256"),
    ("gpu-vram-le.bin","vram_sha256"),
    ("gpu-events.jsonl","events_sha256"),
]:
    m[key] = hashlib.sha256((d/name).read_bytes()).hexdigest()
(d/"bundle.json").write_text(json.dumps(m,indent=2)+"\n")
PY
```

Then run from the repository root:

```sh
python3 -m tools.verify_map02_frame_bundle /private/map02-frame \
    > /private/map02-frame-validation.json
```

The only output is a JSON report containing file fingerprints,
submitted face count, compiled PC-GTE agreement count, how many
VRAM texels were examined, and (separately) how many *observed*
texture probes matched. The report deliberately excludes all
source vertex positions, camera registers, raw BGR555 words,
per-frame GPU registers, and original map/VRAM bytes.

## Strong safety and evidence boundaries

- Rejects wrong-sized, missing or symlinked files, wrong SHA-256,
  duplicate JSON keys, extra fields, unexpected stages, mixed frame
  numbers, repeated source face keys, impossible vertex/GFX/shading
  claims, unbounded XY/depth, unsupported 8/15-bit pages, bad palette
  probes, and mismatched compiled PC-GTE projections.
- Hashes demonstrate **local file integrity against the supplied
  manifest**, not the historic provenance of that manifest.
  A fabricated bundle can pass self-consistency checks.
- A `frame` label is not a clock, a signed capture transcript or a
  trusted proof that GPU values and map bytes originated in retail
  gameplay. The executable SHA field is also only user-provided.
- A **single** VRAM snapshot cannot account for intervening VRAM
  writes during a frame. If the original code changes textures/CLUT
  between polygons, a per-submission VRAM-state capture is required.
- This verifies the **portable PC-port-equivalent** projection and
  VRAM addressing, not the physical PS1 GPU's full raster behavior,
  dithering, drawing-area clipping, ABR blending or final display.
  It does not install authentic textures in the live Switch renderer.
- CI validates the *validator* with invented, self-contained inputs;
  **CI does not hold a user game image or a real MAP02 GPU trace**.

The next genuine visual milestone needs private, independently acquired
source map/VRAM/face events from one gameplay session, followed by a
framebuffer/screenshot comparison and an explicit update for any
VRAM changes between primitives.
