#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stddef.h>
#include <stdlib.h>
#include "../source/map_decode_checked.h"

/* Independent command-by-command reference derived from pinned upstream.
 * Only complete eight-command groups are generated: truncated streams are
 * intentionally tested separately in test_map_decode_checked.c.
 */
static size_t reference_decode(const uint8_t *src, size_t input_size, uint8_t *out) {
    uint8_t ring[1024] = {0};
    size_t ip = 0, op = 0, tail = 990;
    while (ip < input_size) {
        unsigned flags = src[ip++];
        for (unsigned command = 0; command < 8; ++command) {
            if ((flags & 1u) == 0) {
                uint8_t value = src[ip++];
                out[op++] = value;
                ring[tail] = value;
                tail = (tail + 1) % 1024;
            } else {
                unsigned token = src[ip++];
                unsigned length, start;
                if (token < 128) {
                    start = (src[ip++] | ((token & 3u) << 8));
                    length = (token >> 2) + 3u;
                    for (unsigned j = 0; j < length; ++j) {
                        uint8_t value = ring[(start + j) % 1024];
                        out[op++] = value;
                        ring[tail] = value;
                        tail = (tail + 1) % 1024;
                    }
                } else if (token < 192) {
                    start = token & 15u;
                    length = ((token & 48u) >> 4) + 2u;
                    for (unsigned j = 0; j < length; ++j) {
                        uint8_t value = ring[(tail + 1024 - start) % 1024];
                        out[op++] = value;
                        ring[tail] = value;
                        tail = (tail + 1) % 1024;
                    }
                } else {
                    length = (token & 63u) + 8u;
                    for (unsigned j = 0; j < length; ++j) {
                        uint8_t value = src[ip++];
                        out[op++] = value;
                        ring[tail] = value;
                        tail = (tail + 1) % 1024;
                    }
                }
            }
            flags >>= 1;
        }
    }
    assert(ip == input_size);
    return op;
}

static uint32_t seed = UINT32_C(0x78bd51e9);
static uint32_t random_word(void) {
    seed = seed * UINT32_C(1664525) + UINT32_C(1013904223);
    return seed;
}

int main(void) {
    uint8_t input[8192], expected[32768], actual[32768];
    for (unsigned trial = 0; trial < 128; ++trial) {
        size_t ip = 0;
        for (unsigned group = 0; group < 12; ++group) {
            unsigned flag = 0;
            size_t flag_pos = ip++;
            for (unsigned bit = 0; bit < 8; ++bit) {
                uint32_t mode = random_word() % 4;
                if (mode == 0) {
                    input[ip++] = (uint8_t)random_word();
                } else {
                    flag |= 1u << bit;
                    if (mode == 1) {
                        uint32_t index = random_word() % 1024;
                        unsigned length_bits = random_word() % 32;
                        input[ip++] = (uint8_t)((length_bits << 2) | (index >> 8));
                        input[ip++] = (uint8_t)index;
                    } else if (mode == 2) {
                        unsigned token = random_word() % 64;
                        input[ip++] = (uint8_t)(0x80u | token);
                    } else {
                        unsigned run_extra = random_word() % 64;
                        input[ip++] = (uint8_t)(0xc0u | run_extra);
                        for (unsigned j = 0; j < run_extra + 8; ++j)
                            input[ip++] = (uint8_t)random_word();
                    }
                }
            }
            input[flag_pos] = (uint8_t)flag;
        }
        assert(ip <= sizeof(input));
        size_t expected_size = reference_decode(input, ip, expected);
        assert(expected_size < sizeof(expected));
        memset(actual, 0xcd, sizeof(actual));
        size_t actual_size = 0;
        assert(vh_map_decode_checked(input, ip, actual, sizeof(actual), &actual_size)
               == VH_MAP_DECODE_OK);
        assert(expected_size == actual_size);
        assert(memcmp(expected, actual, actual_size) == 0);
        assert(actual[actual_size] == 0xcd);
    }
    puts("Map decoder reference differential tests passed (128 synthetic streams).");
    return 0;
}
