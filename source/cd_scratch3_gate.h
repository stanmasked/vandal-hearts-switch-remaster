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

/* Logical payload extraction is deliberately separate from physical CD
 * transfer. sector_count is the capacity in 2048-byte user-data sectors,
 * NOT proof of an asset's actual payload length. The caller must obtain
 * verified_payload_bytes from an independent asset-format check.
 * This helper copies only the verified logical bytes and cannot reproduce
 * the original CdRead write of whole sectors. */
static inline VhScratch3WriteResult vh_cd_scratch3_payload_copy(
    VhMapUnitPhase *phase, const VhPs1MemoryView *memory,
    uint32_t target_address, uint32_t source_address,
    size_t sector_count, size_t verified_payload_bytes) {
    const uint64_t target = target_address;
    const uint64_t start = VH_MAP_OUTPUT_ADDR;
    const uint64_t span = VH_PS1_RAM_SIZE -
                           (uint64_t)(VH_MAP_OUTPUT_ADDR - VH_PS1_RAM_BASE);
    size_t padded_capacity;

    if (phase == NULL || memory == NULL ||
        sector_count == 0 || verified_payload_bytes == 0)
        return VH_SCRATCH3_WRITE_INVALID_ARGUMENT;
    if (sector_count > SIZE_MAX / VH_CD_USER_SECTOR_BYTES)
        return VH_SCRATCH3_WRITE_OUT_OF_RANGE;
    padded_capacity = sector_count * VH_CD_USER_SECTOR_BYTES;
    if (verified_payload_bytes > padded_capacity)
        return VH_SCRATCH3_WRITE_OUT_OF_RANGE;
    if (target < start || target - start >= span ||
        (uint64_t)verified_payload_bytes > span - (target - start))
        return VH_SCRATCH3_WRITE_OUT_OF_RANGE;
    return vh_scratch3_resource_copy_ps1(
        phase, memory, source_address, (size_t)(target - start),
        verified_payload_bytes);
}

#endif
