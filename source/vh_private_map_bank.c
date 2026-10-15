#include "vh_private_map_bank.h"

#include <errno.h>
#include <stdio.h>
#include <string.h>

static int exact_file_length(FILE *stream, long expected) {
    long length;
    if (fseek(stream, 0, SEEK_END) != 0) return 0;
    length = ftell(stream);
    if (length != expected || fseek(stream, 0, SEEK_SET) != 0) return 0;
    return 1;
}

int vh_private_map_bank_load_pair(const char *texture_path,
                                  const char *land_path,
                                  unsigned map_number,
                                  unsigned slot,
                                  VhPrivateMapBank *out) {
    FILE *texture_file = NULL, *land_file = NULL;
    int texture_error = 0, land_error = 0, result = -1;
    unsigned char record[VH_MAP_RECORD_BYTES];
    VhPrivateMapBank candidate;
    size_t offset;
    if (!texture_path || !land_path || !out ||
        map_number >= VH_MAP_RECORDS || slot >= VH_MAP_SLOTS)
        return -1;

    texture_file = fopen(texture_path, "rb");
    if (!texture_file) texture_error = errno;
    land_file = fopen(land_path, "rb");
    if (!land_file) land_error = errno;

    if (!texture_file && !land_file &&
        texture_error == ENOENT && land_error == ENOENT) {
        result = 0;
        goto cleanup;
    }
    if (!texture_file || !land_file) goto cleanup;
    if (!exact_file_length(texture_file, VH_MAP_TEX_BYTES) ||
        !exact_file_length(land_file, VH_MAP_LAND_BYTES))
        goto cleanup;
    if (fread(candidate.texture, 1, VH_MAP_TEX_BYTES, texture_file)
            != VH_MAP_TEX_BYTES)
        goto cleanup;

    offset = (size_t)map_number * VH_MAP_RECORD_BYTES;
    if (fseek(land_file, (long)offset, SEEK_SET) != 0 ||
        fread(record, 1, VH_MAP_RECORD_BYTES, land_file)
            != VH_MAP_RECORD_BYTES)
        goto cleanup;
    memcpy(candidate.uvwh, record + slot * 4u, 4);
    /* The CLUT selector block begins after 257 four-byte UVWH entries. */
    candidate.local_clut_id = record[VH_MAP_SLOTS * 4u + slot];
    if (candidate.local_clut_id < 32 || candidate.local_clut_id > 47 ||
        candidate.uvwh[0] > 254 || candidate.uvwh[1] > 254 ||
        candidate.uvwh[2] < 1 || candidate.uvwh[3] < 1 ||
        (unsigned)candidate.uvwh[0] + candidate.uvwh[2] >= 256 ||
        (unsigned)candidate.uvwh[1] + candidate.uvwh[3] >= 256)
        goto cleanup;
    memcpy(candidate.palette, record + VH_MAP_SLOTS * 5u,
           VH_MAP_PALETTE_BYTES);
    memcpy(out, &candidate, sizeof(candidate));
    result = 1;
cleanup:
    if (texture_file) fclose(texture_file);
    if (land_file) fclose(land_file);
    return result;
}
