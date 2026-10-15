#ifndef VH_MAP_UNIT_BOUNDARY_H
#define VH_MAP_UNIT_BOUNDARY_H

/* Experimental conservative map/unit lifetime gate.
 * Pinned upstream src/units/load.c chooses unit storage at map base +
 * 0x2db80 normally, or +0x3a300 on map 39. The offsets indicate where
 * unit data STARTS, not proven maximum decoded map sizes. Never claim an
 * original map fits in the interval without validating real map assets.
 */
#include <stddef.h>
#include <stdint.h>
#include "map_load_checked.h"

#define VH_MAP_NORMAL_UNIT_OFFSET ((size_t)0x2db80)
#define VH_MAP_39_UNIT_OFFSET ((size_t)0x3a300)

static inline size_t vh_map_capacity_before_units(unsigned map_number) {
    return map_number == 39 ? VH_MAP_39_UNIT_OFFSET
                            : VH_MAP_NORMAL_UNIT_OFFSET;
}

/* Require the caller-supplied maximum map size to end before live unit data.
 * This deliberately rejects requests crossing the unit start address. */
static inline VhMapLoadStatus vh_map_load_before_units(
    const VhPs1MemoryView *memory, unsigned map_number,
    size_t input_available, size_t verified_output_capacity,
    VhMapDecodeStatus *decode_status, size_t *written) {
    if (decode_status == NULL || written == NULL)
        return VH_MAP_LOAD_PREFLIGHT_FAILED;
    *decode_status = VH_MAP_DECODE_INVALID_ARGUMENT;
    *written = 0;
    if (verified_output_capacity == 0 ||
        verified_output_capacity > vh_map_capacity_before_units(map_number))
        return VH_MAP_LOAD_PREFLIGHT_FAILED;
    return vh_map_load_checked(memory, input_available,
                               verified_output_capacity,
                               decode_status, written);
}

#endif
