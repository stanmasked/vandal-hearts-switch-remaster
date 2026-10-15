#ifndef VH_UNIT_ACCUMULATE_H
#define VH_UNIT_ACCUMULATE_H

/* Synthetic safe counterpart of pinned src/units/load.c:216-227.
 * The original code copies an inner size word from each packed sheet into
 * the accumulation cursor at scratch3 + the map-specific unit offset.
 * Here metadata, source, destination and cursor are validated before a
 * single byte is changed. This is NOT yet linked into the game.
 */
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "unit_file_layout.h"
#include "map_unit_boundary.h"

typedef enum VhUnitAppendStatus {
    VH_UNIT_APPEND_OK = 0,
    VH_UNIT_APPEND_INVALID_ARGUMENT,
    VH_UNIT_APPEND_INVALID_SHEET,
    VH_UNIT_APPEND_OUT_OF_RANGE
} VhUnitAppendStatus;

static inline VhUnitAppendStatus vh_unit_append_sheet(
    const VhPs1MemoryView *memory, unsigned map_number,
    const VhUnitFileLayout *layout, size_t file_available,
    size_t sheet_index, size_t accumulator_capacity,
    size_t *accumulator_cursor) {
    size_t src_offset, outer_size, copied_size, start_offset, destination_offset;
    uint8_t *source, *destination;

    if (!memory || !layout || !accumulator_cursor ||
        sheet_index >= layout->sheet_count ||
        sheet_index >= VH_UNIT_SHEETS_MAX)
        return VH_UNIT_APPEND_INVALID_ARGUMENT;
    src_offset = layout->sheet_offsets[sheet_index];
    outer_size = layout->sheet_lengths[sheet_index];
    if (outer_size < 4 || (outer_size & 3u) ||
        src_offset > file_available || outer_size > file_available - src_offset)
        return VH_UNIT_APPEND_INVALID_SHEET;

    /* Source lives in the shared scratch3 staging buffer, not the map input
     * area. No direct pointer arithmetic until PS1 spans are checked. */
    if (src_offset > UINT32_MAX - VH_MAP_OUTPUT_ADDR)
        return VH_UNIT_APPEND_OUT_OF_RANGE;
    source = vh_ps1_memory_span(memory,
                 VH_MAP_OUTPUT_ADDR + (uint32_t)src_offset, outer_size);
    if (!source) return VH_UNIT_APPEND_OUT_OF_RANGE;
    copied_size = vh_unit_layout_read_u32(source);
    if (copied_size < 4 || (copied_size & 3u) || copied_size > outer_size)
        return VH_UNIT_APPEND_INVALID_SHEET;

    if (*accumulator_cursor > accumulator_capacity ||
        copied_size > accumulator_capacity - *accumulator_cursor)
        return VH_UNIT_APPEND_OUT_OF_RANGE;
    start_offset = vh_map_capacity_before_units(map_number);
    if (start_offset > SIZE_MAX - *accumulator_cursor)
        return VH_UNIT_APPEND_OUT_OF_RANGE;
    destination_offset = start_offset + *accumulator_cursor;
    if (destination_offset > UINT32_MAX - VH_MAP_OUTPUT_ADDR)
        return VH_UNIT_APPEND_OUT_OF_RANGE;
    destination = vh_ps1_memory_span(memory,
               VH_MAP_OUTPUT_ADDR + (uint32_t)destination_offset, copied_size);
    if (!destination) return VH_UNIT_APPEND_OUT_OF_RANGE;

    memmove(destination, source, copied_size);
    *accumulator_cursor += copied_size;
    return VH_UNIT_APPEND_OK;
}

#endif
