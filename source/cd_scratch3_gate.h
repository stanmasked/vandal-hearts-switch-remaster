#ifndef VH_CD_SCRATCH3_GATE_H
#define VH_CD_SCRATCH3_GATE_H

/* Synthetic preflight for pinned src/core/cd.c LoadCdFile / CdRead.
 * Upstream reads gCdFiles[cdf].sectorCt sectors into bufferPtr, and
 * ContinueLoadingCdFile calls CdRead with that pointer. This is NOT
 * installed in the original CD loader. Only scratch3-bound transfers
 * should be routed through this adapter.
 */
#include <stddef.h>
#include <stdint.h>
#include "scratch3_resource_write.h"

#define VH_CD_USER_SECTOR_BYTES ((size_t)2048)

static inline VhScratch3WriteResult vh_cd_scratch3_transfer(
    VhMapUnitPhase *phase, const VhPs1MemoryView *memory,
    uint32_t target_address, uint32_t source_address, size_t sector_count) {
    const uint64_t target = target_address;
    const uint64_t start = VH_MAP_OUTPUT_ADDR;
    const uint64_t span = VH_PS1_RAM_SIZE -
                           (uint64_t)(VH_MAP_OUTPUT_ADDR - VH_PS1_RAM_BASE);
    size_t count;

    if (phase == NULL || memory == NULL || sector_count == 0)
        return VH_SCRATCH3_WRITE_INVALID_ARGUMENT;
    if (sector_count > SIZE_MAX / VH_CD_USER_SECTOR_BYTES)
        return VH_SCRATCH3_WRITE_OUT_OF_RANGE;
    count = sector_count * VH_CD_USER_SECTOR_BYTES;
    if (target < start || target - start >= span)
        return VH_SCRATCH3_WRITE_OUT_OF_RANGE;
    if ((uint64_t)count > span - (target - start))
        return VH_SCRATCH3_WRITE_OUT_OF_RANGE;
    return vh_scratch3_resource_copy_ps1(
        phase, memory, source_address, (size_t)(target - start), count);
}

#endif
