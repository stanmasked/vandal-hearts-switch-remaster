#ifndef VH_MAP_DECODE_CHECKED_H
#define VH_MAP_DECODE_CHECKED_H

/* Bounded standalone interpretation of pinned upstream src/maps/unpack.c.
 * Synthetic data tests only; NOT linked into the original game yet.
 * Unlike upstream, incomplete commands fail rather than producing partial
 * successful output. The dictionary is fully zero-initialized for safety,
 * whereas upstream explicitly clears only the first 990 bytes.
 */
#include <stddef.h>
#include <stdint.h>
#include <string.h>

typedef enum VhMapDecodeStatus {
    VH_MAP_DECODE_OK = 0,
    VH_MAP_DECODE_INVALID_ARGUMENT,
    VH_MAP_DECODE_TRUNCATED,
    VH_MAP_DECODE_OUTPUT_FULL
} VhMapDecodeStatus;

static inline VhMapDecodeStatus vh_map_decode_checked(
    const uint8_t *input, size_t input_size, uint8_t *output,
    size_t output_capacity, size_t *written) {
    uint8_t dictionary[1024];
    size_t pos = 0, out = 0, cache_ofs = 990;
    unsigned bit;
    if (written == NULL) return VH_MAP_DECODE_INVALID_ARGUMENT;
    *written = 0;
    if (input == NULL || output == NULL || input_size == 0 || output_capacity == 0)
        return VH_MAP_DECODE_INVALID_ARGUMENT;
    memset(dictionary, 0, sizeof(dictionary));
    while (pos < input_size) {
        uint8_t control = input[pos++];
        for (bit = 0; bit < 8 && pos < input_size; ++bit) {
            size_t count = 1, index = 0, k;
            uint8_t b1 = 0;
            unsigned kind = 0; /* literal, absolute, relative, raw run */
            if (((control >> bit) & 1u) != 0) {
                b1 = input[pos++];
                if (b1 < 0x80) {
                    if (pos == input_size) {
                        *written = out; return VH_MAP_DECODE_TRUNCATED;
                    }
                    index = (size_t)input[pos++] | ((size_t)(b1 & 3u) << 8);
                    count = (size_t)(b1 >> 2) + 3;
                    kind = 1;
                } else if (b1 < 0xc0) {
                    index = b1 & 0x0fu;
                    count = ((b1 & 0x30u) >> 4) + 2;
                    kind = 2;
                } else {
                    count = (b1 & 0x3fu) + 8;
                    kind = 3;
                    if (count > input_size - pos) {
                        *written = out; return VH_MAP_DECODE_TRUNCATED;
                    }
                }
            }
            if (count > output_capacity - out) {
                *written = out; return VH_MAP_DECODE_OUTPUT_FULL;
            }
            for (k = 0; k < count; ++k) {
                uint8_t v;
                if (kind == 0 || kind == 3) v = input[pos++];
                else if (kind == 1) v = dictionary[(index + k) & 1023u];
                else v = dictionary[(cache_ofs - index) & 1023u];
                output[out++] = v;
                dictionary[cache_ofs] = v;
                cache_ofs = (cache_ofs + 1) & 1023u;
            }
        }
    }
    *written = out;
    return VH_MAP_DECODE_OK;
}
#endif
