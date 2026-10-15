#ifndef VH_MAP_LOAD_CHECKED_H
#define VH_MAP_LOAD_CHECKED_H

/* Synthetic-only integration: PS1 address views -> map preflight -> bounded
 * decoder. No upstream game code or files are linked here. The caller must
 * provide a separately justified decompressed capacity.
 *
 * Transactional handoff: decode into temporary host storage, then copy only
 * a successfully decoded payload into shared PS1 RAM. Failed decodes preserve
 * all pre-existing output bytes. This interface is not yet game-integrated.
 */
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include "map_buffer_gate.h"
#include "map_decode_checked.h"

typedef enum VhMapLoadStatus {
    VH_MAP_LOAD_OK = 0,
    VH_MAP_LOAD_PREFLIGHT_FAILED,
    VH_MAP_LOAD_DECODE_FAILED,
    VH_MAP_LOAD_ALLOCATION_FAILED
} VhMapLoadStatus;

static inline VhMapLoadStatus vh_map_load_checked(
    const VhPs1MemoryView *memory, size_t available_input,
    size_t verified_output_capacity, VhMapDecodeStatus *decode_status,
    size_t *written) {
    VhMapBuffers buffers;
    uint8_t *temporary;
    size_t decoded_size = 0;

    if (decode_status == NULL || written == NULL)
        return VH_MAP_LOAD_PREFLIGHT_FAILED;
    *decode_status = VH_MAP_DECODE_INVALID_ARGUMENT;
    *written = 0;
    if (!vh_map_buffers_prepare(memory, available_input,
                                verified_output_capacity, &buffers))
        return VH_MAP_LOAD_PREFLIGHT_FAILED;
    temporary = (uint8_t *)malloc(buffers.output_capacity);
    if (temporary == NULL)
        return VH_MAP_LOAD_ALLOCATION_FAILED;

    *decode_status = vh_map_decode_checked(buffers.compressed,
                          buffers.compressed_length, temporary,
                          buffers.output_capacity, &decoded_size);
    if (*decode_status != VH_MAP_DECODE_OK) {
        free(temporary);
        return VH_MAP_LOAD_DECODE_FAILED;
    }

    memcpy(buffers.output, temporary, decoded_size);
    free(temporary);
    *written = decoded_size;
    return VH_MAP_LOAD_OK;
}
#endif
