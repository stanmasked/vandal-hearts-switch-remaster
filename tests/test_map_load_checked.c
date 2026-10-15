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
    assert(decode == VH_MAP_DECODE_OUTPUT_FULL && written == 0);
    for (size_t i = 0; i < 8; ++i) assert(decoded[i] == 0x7f);

    written = 999;
    status = vh_map_load_checked(&mem, sizeof fixture - 1, 8, &decode, &written);
    assert(status == VH_MAP_LOAD_PREFLIGHT_FAILED && written == 0);
    assert(decode == VH_MAP_DECODE_INVALID_ARGUMENT);
    for (size_t i = 0; i < 8; ++i) assert(decoded[i] == 0x7f);

    compressed[0] = 0xff; compressed[1] = 0xff;
    compressed[2] = 0xff; compressed[3] = 0xff;
    status = vh_map_load_checked(&mem, sizeof fixture, 8, &decode, &written);
    assert(status == VH_MAP_LOAD_PREFLIGHT_FAILED && written == 0);
    for (size_t i = 0; i < 8; ++i) assert(decoded[i] == 0x7f);

    /* A truncated command after an earlier literal must not publish partial data. */
    {
        const uint8_t broken[] = {3,0,0,0,0x02,'X',0x00};
        memcpy(compressed, broken, sizeof broken);
        memset(decoded, 0x6d, 8);
        status = vh_map_load_checked(&mem, sizeof broken, 8, &decode, &written);
        assert(status == VH_MAP_LOAD_DECODE_FAILED);
        assert(decode == VH_MAP_DECODE_TRUNCATED && written == 0);
        for (size_t i = 0; i < 8; ++i) assert(decoded[i] == 0x6d);
    }

    /* Capacity sweep: no partial publish, no writes past decoded length. */
    {
        const uint8_t fixture_again[] = {4, 0, 0, 0, 0, 'R', 'P', 'G'};
        memcpy(compressed, fixture_again, sizeof fixture_again);
        for (size_t capacity = 0; capacity <= 64; ++capacity) {
            memset(decoded, 0x6d, 128);
            written = 999;
            status = vh_map_load_checked(&mem, sizeof fixture_again,
                                         capacity, &decode, &written);
            if (capacity == 0) {
                assert(status == VH_MAP_LOAD_PREFLIGHT_FAILED);
                assert(decode == VH_MAP_DECODE_INVALID_ARGUMENT);
                assert(written == 0);
            } else if (capacity < 3) {
                assert(status == VH_MAP_LOAD_DECODE_FAILED);
                assert(decode == VH_MAP_DECODE_OUTPUT_FULL);
                assert(written == 0);
            } else {
                assert(status == VH_MAP_LOAD_OK);
                assert(decode == VH_MAP_DECODE_OK);
                assert(written == 3);
                assert(memcmp(decoded, "RPG", 3) == 0);
            }
            for (size_t i = capacity >= 3 ? 3 : 0; i < 128; ++i)
                assert(decoded[i] == 0x6d);
        }
    }

    /* Large synthetic output views: the adapter allocates temporary storage
     * but publishes only the actual three decoded bytes. These sizes are
     * tests, NOT verified capacities of any original game map. */
    {
        static const size_t capacities[] = {
            4096u, 65536u, 262144u,
            VH_PS1_RAM_SIZE - (VH_MAP_OUTPUT_ADDR - VH_PS1_RAM_BASE)
        };
        const size_t max_output = capacities[3];
        const uint8_t fixture_again[] = {4, 0, 0, 0, 0, 'R', 'P', 'G'};
        memcpy(compressed, fixture_again, sizeof fixture_again);
        for (size_t test_index = 0; test_index < 4; ++test_index) {
            size_t capacity = capacities[test_index];
            memset(decoded, 0x6d, max_output);
            written = 999;
            status = vh_map_load_checked(&mem, sizeof fixture_again,
                                         capacity, &decode, &written);
            assert(status == VH_MAP_LOAD_OK);
            assert(decode == VH_MAP_DECODE_OK && written == 3);
            assert(memcmp(decoded, "RPG", 3) == 0);
            for (size_t i = 3; i < max_output; ++i)
                assert(decoded[i] == 0x6d);
        }
        /* Exceed the 2 MiB PS1 RAM address window by exactly one byte. */
        memset(decoded, 0x6d, max_output);
        status = vh_map_load_checked(&mem, sizeof fixture_again,
                                     max_output + 1, &decode, &written);
        assert(status == VH_MAP_LOAD_PREFLIGHT_FAILED && written == 0);
        assert(decode == VH_MAP_DECODE_INVALID_ARGUMENT);
        for (size_t i = 0; i < max_output; ++i)
            assert(decoded[i] == 0x6d);

        /* Even a late syntax error cannot publish any decoded bytes. */
        {
            const uint8_t broken[] = {3, 0, 0, 0, 0x02, 'X', 0x00};
            memcpy(compressed, broken, sizeof broken);
            status = vh_map_load_checked(&mem, sizeof broken, max_output,
                                         &decode, &written);
            assert(status == VH_MAP_LOAD_DECODE_FAILED);
            assert(decode == VH_MAP_DECODE_TRUNCATED && written == 0);
            for (size_t i = 0; i < max_output; ++i)
                assert(decoded[i] == 0x6d);
        }
    }

    assert(vh_map_load_checked(&mem, 8, 8, NULL, &written)
           == VH_MAP_LOAD_PREFLIGHT_FAILED);
    assert(vh_map_load_checked(&mem, 8, 8, &decode, NULL)
           == VH_MAP_LOAD_PREFLIGHT_FAILED);
    free(ram);
    puts("Map load integration tests passed.");
    return 0;
}
