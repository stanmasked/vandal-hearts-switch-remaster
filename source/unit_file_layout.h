#ifndef VH_UNIT_FILE_LAYOUT_H
#define VH_UNIT_FILE_LAYOUT_H

/* Bounded metadata walk for the pinned src/units/load.c:176-186 layout.
 * It is NOT a decoder and does not claim to determine the logical end
 * of the complete UNIT_*.DAT file. The source also contains sprite strips
 * after the packed sheet region, whose count/usage is context dependent.
 *
 * The original loader uses pSheets[6], counts [2]+[3], a size table of
 * 32-bit little-endian lengths at offset 4, then concatenated sheets.
 * For each sheet, the first word is the size copied to unit accumulation.
 * It may be smaller than the outer table span. This parser verifies
 * table bounds, inner-copy bounds, sheet bounds and alignment before
 * providing offsets to future loader integration.
 */
#include <stddef.h>
#include <stdint.h>

#define VH_UNIT_SHEETS_MAX ((size_t)6)

typedef struct VhUnitFileLayout {
    size_t sheet_count;
    size_t strips_offset;
    size_t sheet_offsets[6];
    size_t sheet_lengths[6];
} VhUnitFileLayout;

static inline uint32_t vh_unit_layout_read_u32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static inline int vh_unit_file_layout(
    const uint8_t *bytes, size_t available,
    VhUnitFileLayout *result) {
    size_t count, offset;
    VhUnitFileLayout parsed = {0};
    if (bytes == NULL || result == NULL || available < 4) return 0;
    count = (size_t)bytes[2] + (size_t)bytes[3];
    if (count == 0 || count > VH_UNIT_SHEETS_MAX) return 0;
    if (count > (available - 4) / 4) return 0;
    offset = 4 + count * 4;
    for (size_t i = 0; i < count; ++i) {
        size_t length = vh_unit_layout_read_u32(bytes + 4 + i * 4);
        if (length < 4 || (length & 3u) != 0 ||
            length > available - offset)
            return 0;
        /* Original loader copies the word count specified at sheet start;
         * require a bounded, aligned inner copy size before exposing a span. */
        {
            size_t inner_length = vh_unit_layout_read_u32(bytes + offset);
            if (inner_length < 4 || (inner_length & 3u) != 0 ||
                inner_length > length) return 0;
        }
        parsed.sheet_offsets[i] = offset;
        parsed.sheet_lengths[i] = length;
        offset += length;
    }
    parsed.sheet_count = count;
    parsed.strips_offset = offset;
    *result = parsed; /* only publish after complete validation */
    return 1;
}

#endif
