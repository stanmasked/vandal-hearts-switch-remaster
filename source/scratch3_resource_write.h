#ifndef VH_SCRATCH3_RESOURCE_WRITE_H
#define VH_SCRATCH3_RESOURCE_WRITE_H

/* Synthetic, range-checked writes into shared PS1 scratch3 RAM.
 * This adapter is not wired into the upstream LoadCdFile implementation.
 * The map's logical validity is revoked only after a successful nonempty
 * write intersecting its conservative possible location.
 */
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "map_unit_phase.h"

typedef enum VhScratch3WriteResult {
    VH_SCRATCH3_WRITE_OK = 0,
    VH_SCRATCH3_WRITE_INVALID_ARGUMENT,
    VH_SCRATCH3_WRITE_OUT_OF_RANGE
} VhScratch3WriteResult;

static inline VhScratch3WriteResult vh_scratch3_resource_write(
    VhMapUnitPhase *phase, const VhPs1MemoryView *memory,
    size_t offset, const void *bytes, size_t length) {
    uint8_t *destination;
    const size_t span = VH_PS1_RAM_SIZE -
                      (size_t)(VH_MAP_OUTPUT_ADDR - VH_PS1_RAM_BASE);

    if (phase == NULL || memory == NULL || (length != 0 && bytes == NULL))
        return VH_SCRATCH3_WRITE_INVALID_ARGUMENT;
    if (offset > span || length > span - offset)
        return VH_SCRATCH3_WRITE_OUT_OF_RANGE;
    if (length == 0) return VH_SCRATCH3_WRITE_OK;
    destination = vh_ps1_memory_span(memory,
                       VH_MAP_OUTPUT_ADDR + (uint32_t)offset, length);
    if (destination == NULL) return VH_SCRATCH3_WRITE_OUT_OF_RANGE;

    /* Resources can be staged in another part of shared PS1 RAM.
     * memmove permits source and destination host spans to overlap.
     * All destination bounds are verified above; a real loader must also
     * validate the source span before calling this synthetic adapter.
     */
    memmove(destination, bytes, length);
    vh_map_unit_phase_scratch3_write(phase, offset, length);
    return VH_SCRATCH3_WRITE_OK;
}

#endif
