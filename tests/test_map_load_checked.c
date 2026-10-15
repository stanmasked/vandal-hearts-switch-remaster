#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../source/map_load_checked.h"

int main(void) {
    uint8_t *ram = calloc(VH_PS1_RAM_SIZE, 1);
    uint8_t scratch[VH_PS1_SCRATCH_SIZE] = {0};
    VhPs1MemoryView mem = {ram, VH_PS1_RAM_SIZE, scratch, sizeof scratch};
    uint8_t *compressed, *decoded;
    VhMapDecodeStatus decode;
    VhMapLoadStatus status;
    size_t written = 999;
    assert(ram != NULL);
    compressed = vh_ps1_memory_span(&mem, VH_MAP_INPUT_ADDR, 8);
    decoded = vh_ps1_memory_span(&mem, VH_MAP_OUTPUT_ADDR, 8);
    assert(compressed && decoded);
    /* Little-endian compressed size (4), one control and three literals. */
    const uint8_t fixture[] = {4,0,0,0,0,'R','P','G'};
    memcpy(compressed, fixture, sizeof fixture);
    memset(decoded, 0x7f, 8);

    status = vh_map_load_checked(&mem, sizeof fixture, 3, &decode, &written);
    assert(status == VH_MAP_LOAD_OK && decode == VH_MAP_DECODE_OK);
    assert(written == 3 && memcmp(decoded, "RPG", 3) == 0);
    assert(decoded[3] == 0x7f);

    memset(decoded, 0x7f, 8);
    status = vh_map_load_checked(&mem, sizeof fixture, 2, &decode, &written);
    assert(status == VH_MAP_LOAD_DECODE_FAILED);
    assert(decode == VH_MAP_DECODE_OUTPUT_FULL && written == 2);
    assert(decoded[2] == 0x7f);

    written = 999;
    status = vh_map_load_checked(&mem, sizeof fixture - 1, 8, &decode, &written);
    assert(status == VH_MAP_LOAD_PREFLIGHT_FAILED && written == 0);
    assert(decode == VH_MAP_DECODE_INVALID_ARGUMENT);

    compressed[0] = 0xff; compressed[1] = 0xff;
    compressed[2] = 0xff; compressed[3] = 0xff;
    status = vh_map_load_checked(&mem, sizeof fixture, 8, &decode, &written);
    assert(status == VH_MAP_LOAD_PREFLIGHT_FAILED && written == 0);

    assert(vh_map_load_checked(&mem, 8, 8, NULL, &written)
           == VH_MAP_LOAD_PREFLIGHT_FAILED);
    assert(vh_map_load_checked(&mem, 8, 8, &decode, NULL)
           == VH_MAP_LOAD_PREFLIGHT_FAILED);
    free(ram);
    puts("Map load integration tests passed.");
    return 0;
}
