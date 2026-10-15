#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "../source/vh_private_map_bank.h"

static void put_bytes(const char *path, const void *data, size_t count) {
    FILE *file = fopen(path, "wb");
    assert(file != NULL);
    assert(fwrite(data, 1, count, file) == count);
    assert(fclose(file) == 0);
}

int main(void) {
    char tempdir[] = "/tmp/vh-private-map-XXXXXX";
    char texture_path[256], land_path[256];
    uint8_t texture[VH_MAP_TEX_BYTES] = {0};
    uint8_t *land = (uint8_t *)calloc(1, VH_MAP_LAND_BYTES);
    VhPrivateMapBank *bank = (VhPrivateMapBank *)malloc(sizeof(*bank));
    size_t offset, uv, clut, colors;
    int status;
    assert(land && bank && mkdtemp(tempdir));
    assert(snprintf(texture_path, sizeof(texture_path), "%s/F_TEX01.DAT",
                    tempdir) < (int)sizeof(texture_path));
    assert(snprintf(land_path, sizeof(land_path), "%s/LAND_DT.DAT",
                    tempdir) < (int)sizeof(land_path));

    /* Neither file exists: the native probe must retain synthetic fallback. */
    memset(bank, 0xa5, sizeof(*bank));
    status = vh_private_map_bank_load_pair(texture_path, land_path,
                                           11, 241, bank);
    assert(status == 0 && bank->uvwh[0] == 0xa5);

    texture[0] = 0x21;
    texture[VH_MAP_TEX_BYTES - 1] = 0x42;
    offset = 11u * VH_MAP_RECORD_BYTES;
    uv = offset + 241u * 4u;
    clut = offset + VH_MAP_SLOTS * 4u + 241u;
    colors = offset + VH_MAP_SLOTS * 5u + 3u * 32u;
    land[uv + 0] = 240;
    land[uv + 1] = 192;
    land[uv + 2] = 15;
    land[uv + 3] = 15;
    land[clut] = 35;
    land[colors + 2] = 0x1f;
    land[colors + 4] = 0xe0;
    land[colors + 5] = 0x03;
    put_bytes(texture_path, texture, sizeof(texture));
    put_bytes(land_path, land, VH_MAP_LAND_BYTES);

    assert(vh_private_map_bank_load_pair(texture_path, land_path, 11, 241,
                                         bank) == 1);
    assert(bank->uvwh[0] == 240 && bank->uvwh[1] == 192);
    assert(bank->uvwh[2] == 15 && bank->uvwh[3] == 15);
    assert(bank->local_clut_id == 35);
    assert((bank->texture[0] & 0xffu) == 0x21);
    assert(((const uint8_t *)bank->texture)[VH_MAP_TEX_BYTES - 1] == 0x42);
    assert(bank->palette[3 * 16 + 1] == 0x001f);
    assert(bank->palette[3 * 16 + 2] == 0x03e0);

    /* Invalid parameters and mismatched local file pair fail CLOSED. */
    assert(vh_private_map_bank_load_pair(texture_path, land_path, 69, 241,
                                         bank) == -1);
    assert(vh_private_map_bank_load_pair(texture_path, land_path, 11, 257,
                                         bank) == -1);
    assert(vh_private_map_bank_load_pair(NULL, land_path, 11, 241,
                                         bank) == -1);
    assert(vh_private_map_bank_load_pair(texture_path, land_path, 11, 241,
                                         NULL) == -1);
    assert(unlink(land_path) == 0);
    memset(bank, 0xa5, sizeof(*bank));
    assert(vh_private_map_bank_load_pair(texture_path, land_path, 11, 241,
                                         bank) == -1);
    assert(bank->uvwh[0] == 0xa5);
    put_bytes(land_path, land, VH_MAP_LAND_BYTES);

    put_bytes(texture_path, texture, sizeof(texture) - 1);
    assert(vh_private_map_bank_load_pair(texture_path, land_path, 11, 241,
                                         bank) == -1);
    put_bytes(texture_path, texture, sizeof(texture));

    put_bytes(land_path, land, VH_MAP_LAND_BYTES - 1);
    assert(vh_private_map_bank_load_pair(texture_path, land_path, 11, 241,
                                         bank) == -1);
    put_bytes(land_path, land, VH_MAP_LAND_BYTES);

    land[clut] = 31; /* not one of the 16 local LAND_DT palettes */
    put_bytes(land_path, land, VH_MAP_LAND_BYTES);
    assert(vh_private_map_bank_load_pair(texture_path, land_path, 11, 241,
                                         bank) == -1);
    land[clut] = 35;
    land[uv + 0] = 255; /* x=255 cannot show a 2-pixel sprite */
    put_bytes(land_path, land, VH_MAP_LAND_BYTES);
    assert(vh_private_map_bank_load_pair(texture_path, land_path, 11, 241,
                                         bank) == -1);

    assert(unlink(texture_path) == 0);
    assert(unlink(land_path) == 0);
    assert(rmdir(tempdir) == 0);
    free(bank);
    free(land);
    puts("PASS: private map-bank loader rejects missing/partial/truncated/invalid files");
    return 0;
}
