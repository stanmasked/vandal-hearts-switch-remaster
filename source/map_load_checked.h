#ifndef VH_MAP_LOAD_CHECKED_H
#define VH_MAP_LOAD_CHECKED_H

/* Synthetic-only integration: PS1 address views -> map preflight -> bounded
 * decoder. No upstream game code or files are linked here. The caller must
 * provide a separately justified decompressed capacity. Decode failures can
 * leave a partial output; consumers MUST check status before using the map.
 */
#include <stddef.h>
#include "map_buffer_gate.h"
#include "map_decode_checked.h"

typedef enum VhMapLoadStatus {
    VH_MAP_LOAD_OK = 0,
    VH_MAP_LOAD_PREFLIGHT_FAILED,
    VH_MAP_LOAD_DECODE_FAILED
} VhMapLoadStatus;

static inline VhMapLoadStatus vh_map_load_checked(
    const VhPs1MemoryView *memory, size_t available_input,
    size_t verified_output_capacity, VhMapDecodeStatus *decode_status,
    size_t *written) {
    VhMapBuffers buffers;
    if (decode_status == NULL || written == NULL)
        return VH_MAP_LOAD_PREFLIGHT_FAILED;
    *decode_status = VH_MAP_DECODE_INVALID_ARGUMENT;
    *written = 0;
    if (!vh_map_buffers_prepare(memory, available_input,
                                verified_output_capacity, &buffers))
        return VH_MAP_LOAD_PREFLIGHT_FAILED;
    *decode_status = vh_map_decode_checked(buffers.compressed,
                          buffers.compressed_length, buffers.output,
                          buffers.output_capacity, written);
    return *decode_status == VH_MAP_DECODE_OK
           ? VH_MAP_LOAD_OK : VH_MAP_LOAD_DECODE_FAILED;
}
#endif
