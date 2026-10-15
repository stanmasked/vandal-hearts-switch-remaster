/* Asset-free bridge: verify Python-staged map bytes with the EXACT loader
 * linked into the Switch NRO. This is a HOST-ONLY verification program. */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include "../source/vh_private_map_bank.h"

static VhPrivateMapBank bank;

static unsigned sample_texel(unsigned u, unsigned v) {
    unsigned word = bank.texture[v * 64u + (u >> 2)];
    return (word >> ((u & 3u) * 4u)) & 15u;
}

int main(int argc, char **argv) {
    int status;
    unsigned u, v, local_row, index_left, index_right;
    unsigned color_left, color_right;
    if (argc != 3) {
        fprintf(stderr, "Usage: %s F_TEX01.DAT LAND_DT.DAT\n", argv[0]);
        return 2;
    }
    status = vh_private_map_bank_load_pair(argv[1], argv[2], 11, 241, &bank);
    if (status != 1) {
        printf("status=%d\n", status);
        return 0;
    }
    u = bank.uvwh[0];
    v = bank.uvwh[1];
    local_row = bank.local_clut_id - 32u;
    index_left = sample_texel(u, v);
    index_right = sample_texel(u + 1u, v);
    color_left = bank.palette[local_row * 16u + index_left];
    color_right = bank.palette[local_row * 16u + index_right];
    printf("status=1\n");
    printf("uvwh=%u,%u,%u,%u\n", u, v,
           (unsigned)bank.uvwh[2], (unsigned)bank.uvwh[3]);
    printf("clut=%u\n", (unsigned)bank.local_clut_id);
    printf("indexes=%u,%u\n", index_left, index_right);
    printf("colors=%04x,%04x\n", color_left, color_right);
    return 0;
}
