# Map decompression / unit data address boundary audit

This note applies to the pinned upstream revision
`HalmyLyseas/VandalHearts-PcPort@14552fffa0e0b47e02b57592e274fc6e7a649923`.
No original game files are stored in this repository.

## Confirmed source relationships

* `src/core/main.c` assigns `gMapDataPtr = gScratch3_80180210`.
* `src/units/load.c` places `gUnitDataPtr` at
  `gScratch3_80180210 + 0x2db80`, except map 39 which uses
  `+ 0x3a300` (near lines 139–143).
* `src/maps/unpack.c` reads a four-byte little-endian *compressed*
  length in `ProcessMapFileData`, then passes `&input[4]`,
  `gMapDataPtr` and that length to `UnpackMapFileData`.
  There is **no output-capacity parameter**.
* The symbol addresses `gScratch1_801317c0` and
  `gScratch3_80180210` come from the pinned PS1 symbol map.
  Their declarations are unsized; these addresses do **not** establish
  allocation lengths.
* The experimental host-backed PS1 RAM view models
  `0x80000000..0x801fffff` as 2 MiB, with no KSEG1/KUSEG aliases.

## Address arithmetic (not content-derived sizes)

| Boundary | PS1 address | Relative to map base |
|---|---:|---:|
| Compressed map header (scratch1) | `0x801317c0` | — |
| Decoded map destination (scratch3) | `0x80180210` | `0x0` |
| Normal map unit data start | `0x801add90` | `0x2db80` |
| Map 39 unit data start | `0x801ba510` | `0x3a300` |
| End of 2 MiB PS1 RAM (exclusive) | `0x80200000` | `0x7fdf0` |

The distance between compressed input start and decoded map destination
is `0x4ea50` bytes, *including* the four-byte compressed size header.
For the current isolated test adapter, the compressed payload is rejected
if it would enter the decoded destination region. This is conservative;
the actual engine may reuse these regions at different times.

The provisional map/unit boundary adapter rejects a caller-supplied
decoded capacity larger than `0x2db80` (ordinary maps) or `0x3a300`
(map 39). These limits are **address separation contracts for synthetic
tests**, NOT proven sizes for the original map files and not evidence that
the game's live map and unit data never overlap.

## Unresolved requirements for real integration

1. Determine actual decoded size for each map using original game data
   in a user-controlled local environment. Do not infer it from the
   compressed size header.
2. Confirm allocation lifetime and writes by the map parser, map row
   pointers, terrain graphics, and unit loader. A shared address
   offset does not prove the buffers are simultaneously live.
3. Confirm that the port's scratchpad and PS1 memory aliases match
   source expectations. Fixed-address desktop `mmap`/`VirtualAlloc`
   cannot be assumed to work on libnx.
4. Compare decoded hashes or representative structural invariants
   against a trusted original-format reference before enabling real
   maps.
5. Preserve transactional error behavior: decode into temporary memory
   and publish to shared memory only after successful validation.

## Existing automated coverage

* `tests/test_map_buffer_gate.c`: compressed input span and output
  preflight, including the non-overlap constraint.
* `tests/test_map_decode_checked.c`: bounded command handling,
  longest commands and 1024-byte dictionary wrap.
* `tests/test_map_decode_reference.c`: synthetic differential tests
  against an independently structured reference implementation.
* `tests/test_map_load_checked.c`: transactional output, failure
  rollback and capacity sweeps.
* `tests/test_map_unit_boundary.c`: conservative map-to-unit boundary
  and map 39 special case.

No full original-game Switch runtime verification is claimed.
