#ifndef VH_PRIVATE_MAP_NORMALS_H
#define VH_PRIVATE_MAP_NORMALS_H

#include "vh_private_map_geometry.h"
#include "vh_private_map_light.h"

/* Re-run original src/core/graphics.c::UpdateMapTileLighting on ONE
 * fully validated, extracted MapTileModel (up to 18 quads).
 *
 * Identical 26-way signed dot search and tie-break, original GTE OP0
 * (cross product), pinned VectorNormalS, and the degenerate source
 * vertex-ID fallback choices. Changes only each face's shade_index.
 *
 * Returns 1 for valid geometry, -1 for bad indices, counts or pointers.
 * On error the supplied model remains byte-for-byte unchanged. */
int vh_map_recompute_shade_indices(
    VhPreviewGeometry *geometry,
    const SVECTOR side_normals[VH_MAP_SIDE_NORMALS]);

/* Optional synthetic demonstration only. Exactly one byte == 1
 * enables re-derivation from the input mesh; absent means legacy
 * stored source shade indices. Malformed flags reject the NRO. */
#define VH_MAP_RECOMPUTE_SHADES_PATH \
    "sdmc:/switch/vandal-hearts-remaster/private-assets/LIGHT_RECOMPUTE_SHADES.BIN"

#endif
