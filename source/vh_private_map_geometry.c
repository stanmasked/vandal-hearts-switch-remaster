#include "vh_private_map_geometry.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned read16(const uint8_t *p) {
    return (unsigned)p[0] | ((unsigned)p[1] << 8);
}

static int16_t signed16(const uint8_t *p) {
    unsigned word = read16(p);
    return (int16_t)(word > 32767u ? (int)word - 65536 : (int)word);
}

int vh_private_map_geometry_load(const char *path, unsigned tile_x,
                                 unsigned tile_z, VhPreviewGeometry *out) {
    FILE *file = NULL;
    uint8_t *slab = NULL;
    VhPreviewGeometry candidate;
    size_t i, face, corner, tile_offset;
    long length;
    int err, result = -1;
    if (!path || !out || tile_x >= VH_MAP_MODEL_COLS ||
        tile_z >= VH_MAP_MODEL_ROWS)
        return -1;
    file = fopen(path, "rb");
    if (!file) {
        err = errno;
        return err == ENOENT ? 0 : -1;
    }
    if (fseek(file, 0, SEEK_END) != 0 ||
        (length = ftell(file)) != (long)VH_MAP_MODEL_TOTAL ||
        fseek(file, 0, SEEK_SET) != 0)
        goto cleanup;
    slab = (uint8_t *)malloc(VH_MAP_MODEL_TOTAL);
    if (!slab || fread(slab, 1, VH_MAP_MODEL_TOTAL, file) != VH_MAP_MODEL_TOTAL)
        goto cleanup;
    /* Validate all 336 models, not only the two faces displayed.
     * Invalid topology anywhere implies the private owner file is
     * corrupted and must not be treated as trusted geometry. */
    for (i = 0; i < VH_MAP_MODEL_COLS * VH_MAP_MODEL_ROWS; ++i) {
        const uint8_t *tile = slab + i * VH_MAP_MODEL_BYTES;
        unsigned count = tile[VH_MAP_MODEL_BYTES - 2];
        if (count > VH_MAP_MODEL_MAX_FACES) goto cleanup;
        for (face = 0; face < count; ++face) {
            for (corner = 0; corner < 4; ++corner) {
                if (tile[176u + 36u + face * 4u + corner] >= VH_MAP_MODEL_VERTICES)
                    goto cleanup;
            }
        }
    }
    tile_offset = ((size_t)tile_z * VH_MAP_MODEL_COLS + tile_x)
                  * VH_MAP_MODEL_BYTES;
    {
        const uint8_t *tile = slab + tile_offset;
        memset(&candidate, 0, sizeof(candidate));
        candidate.face_count = tile[302];
        candidate.tile_height = tile[303];
        for (face = 0; face < candidate.face_count; ++face) {
            VhPreviewFace *dst = &candidate.faces[face];
            dst->local_gfx = signed16(tile + 176u + face * 2u);
            dst->shade_index = tile[284u + face];
            for (corner = 0; corner < 4; ++corner) {
                unsigned index = tile[212u + face * 4u + corner];
                const uint8_t *pos = tile + index * 8u;
                dst->vertex_index[corner] = (uint8_t)index;
                dst->vertex[corner][0] = signed16(pos);
                dst->vertex[corner][1] = signed16(pos + 2u);
                dst->vertex[corner][2] = signed16(pos + 4u);
            }
        }
    }
    memcpy(out, &candidate, sizeof(candidate));
    result = 1;
cleanup:
    free(slab);
    fclose(file);
    return result;
}
