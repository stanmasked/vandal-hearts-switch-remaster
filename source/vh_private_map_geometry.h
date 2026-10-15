#ifndef VH_PRIVATE_MAP_GEOMETRY_H
#define VH_PRIVATE_MAP_GEOMETRY_H

#include <stdint.h>

/* Map #11 is 28x12 stored tiles, each source MapTileModel is 304 bytes.
 * Input is a safely decompressed FIRST 102144 bytes, NOT a compressed PRS.
 * All data originates from an owner-only SD file, never the NRO/CI. */
#define VH_MAP_GEOMETRY_PATH "sdmc:/switch/vandal-hearts-remaster/private-assets/MAP11_MODELS_28X12.BIN"
#define VH_MAP_MODEL_COLS 28u
#define VH_MAP_MODEL_ROWS 12u
#define VH_MAP_MODEL_BYTES 304u
#define VH_MAP_MODEL_TOTAL (VH_MAP_MODEL_COLS * VH_MAP_MODEL_ROWS * VH_MAP_MODEL_BYTES)
#define VH_MAP_MODEL_MAX_FACES 18u
#define VH_MAP_MODEL_VERTICES 22u

typedef struct VhPreviewFace {
    int16_t vertex[4][3];
    int16_t local_gfx;
    uint8_t shade_index;
} VhPreviewFace;

typedef struct VhPreviewGeometry {
    uint8_t face_count;
    uint8_t tile_height;
    VhPreviewFace faces[VH_MAP_MODEL_MAX_FACES];
} VhPreviewGeometry;

/* 1: present, correctly-sized and validated model slab; 0: absent;
 * -1: corrupt/partial/inaccessible. Output unchanged except on success.
 * Selected tile only; this is not the original GTE/map-camera renderer. */
int vh_private_map_geometry_load(const char *path, unsigned tile_x,
                                 unsigned tile_z, VhPreviewGeometry *out);
#endif
