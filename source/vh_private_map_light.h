#ifndef VH_PRIVATE_MAP_LIGHT_H
#define VH_PRIVATE_MAP_LIGHT_H

#include <stdint.h>
#include "PsyQ/libgte.h"

/* These are the original 26 primitive normals, NOT saved commercial art.
 * Upstream: src/core/graphics.c::SetupLightNormals (pinned at
 * 14552fffa0e0b47e02b57592e274fc6e7a649923).
 * UpdateLight is reproduced by calling pinned libgte.c's GTE NCCS.
 * The PRIVATE test selects a deterministic demo light rotation and
 * intensity; this is NOT the game runtime's gLightRotation/gLightColor. */
#define VH_MAP_SIDE_NORMALS 26u
#define VH_MAP_LIGHT_DEMO_PATH "sdmc:/switch/vandal-hearts-remaster/private-assets/LIGHT_TEST_INTENSITY.BIN"

void vh_map_init_side_normals(SVECTOR output[VH_MAP_SIDE_NORMALS]);
void vh_map_update_light(CVECTOR output[VH_MAP_SIDE_NORMALS],
                         const SVECTOR normals[VH_MAP_SIDE_NORMALS],
                         const SVECTOR *rotation, const CVECTOR *light_color,
                         int intensity, unsigned map_number);
/* 1 valid intensity byte 0..128, 0 missing, -1 invalid; preserves
 * *intensity unless exactly one valid byte exists. */
int vh_map_read_demo_intensity(const char *path, unsigned char *intensity);

#endif
