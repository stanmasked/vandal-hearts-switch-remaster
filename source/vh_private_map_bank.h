#ifndef VH_PRIVATE_MAP_BANK_H
#define VH_PRIVATE_MAP_BANK_H

#include <stdint.h>

/* Exact original LoadMapTextures layout. No retail assets are embedded. */
#define VH_MAP_TEX_BYTES 32768u
#define VH_MAP_LAND_BYTES 123993u
#define VH_MAP_RECORD_BYTES 1797u
#define VH_MAP_RECORDS 69u
#define VH_MAP_SLOTS 257u
#define VH_MAP_PALETTE_BYTES 512u

#define VH_PRIVATE_MAP_TEXTURE_PATH "sdmc:/switch/vandal-hearts-remaster/private-assets/F_TEX01.DAT"
#define VH_PRIVATE_MAP_LAND_PATH "sdmc:/switch/vandal-hearts-remaster/private-assets/LAND_DT.DAT"

/* The texture is ready for the original LoadImage RECT(320,0,64,256);
 * palette is ready for the original LoadImage RECT(672,496,16,16). */
typedef struct VhPrivateMapBank {
    uint16_t texture[VH_MAP_TEX_BYTES / 2];
    uint16_t palette[VH_MAP_PALETTE_BYTES / 2];
    uint8_t uvwh[4];
    uint8_t local_clut_id;
    /* Preserve ALL source LAND_DT slots for geometry face gfx[] lookups.
     * The initial selection above stays available for the single patch.
     * Other local ID selections must be checked before drawing. */
    uint8_t slot_uvwh[VH_MAP_SLOTS][4];
    uint8_t slot_clut_ids[VH_MAP_SLOTS];
} VhPrivateMapBank;

/*  1: validated pair loaded; 0: neither file present (synthetic CI fallback);
 * -1: malformed, one-sided, inaccessible or otherwise invalid pair.
 * Output is left untouched unless the entire pair passes validation.
 * Caller owns files locally; never copy game files into the repo or CI. */
int vh_private_map_bank_load_pair(const char *texture_path,
                                  const char *land_path,
                                  unsigned map_number,
                                  unsigned slot,
                                  VhPrivateMapBank *out);

#endif
