#ifndef VH_MAP_UNIT_PHASE_H
#define VH_MAP_UNIT_PHASE_H

/* Synthetic phase contract for future port integration. No original engine
 * state is intercepted here. Staging unit input into scratch3 invalidates any
 * previously published map at scratch3 base. A successful checked reload is
 * required before map data can be consumed again.
 */
#include <stddef.h>
#include <stdint.h>
#include "map_unit_boundary.h"

typedef struct VhMapUnitPhase {
    unsigned map_number;
    unsigned map_valid;
} VhMapUnitPhase;

static inline void vh_map_unit_phase_init(VhMapUnitPhase *phase,
                                           unsigned map_number) {
    if (!phase) return;
    phase->map_number = map_number;
    phase->map_valid = 0;
}

/* Conservative lifetime fence for ANY writer into scratch3.
 * Offsets are relative to VH_MAP_OUTPUT_ADDR. [0, unit-start) is treated
 * as potentially containing map data, not as a proven decoded map span.
 * For unknown/overflowing ranges, invalidate conservatively.
 * Call before the external writer changes shared memory.
 */
static inline void vh_map_unit_phase_scratch3_write(
    VhMapUnitPhase *phase, size_t offset, size_t length) {
    size_t boundary;
    if (phase == NULL || length == 0) return;
    boundary = vh_map_capacity_before_units(phase->map_number);
    if (offset < boundary || offset > SIZE_MAX - length)
        phase->map_valid = 0;
}

/* Unit files are staged at scratch3 offset zero. */
static inline void vh_map_unit_phase_stage_units(VhMapUnitPhase *phase) {
    vh_map_unit_phase_scratch3_write(phase, 0, 1);
}

static inline int vh_map_unit_phase_can_read_map(const VhMapUnitPhase *phase) {
    return phase != NULL && phase->map_valid != 0;
}

/* Failed reload leaves previously published map bytes intact, but cannot
 * revalidate a view invalidated by unit staging. */
static inline VhMapLoadStatus vh_map_unit_phase_reload(
    VhMapUnitPhase *phase, const VhPs1MemoryView *memory,
    size_t input_available, size_t verified_output_capacity,
    VhMapDecodeStatus *decode_status, size_t *written) {
    VhMapLoadStatus status;
    if (!phase) {
        if (decode_status) *decode_status = VH_MAP_DECODE_INVALID_ARGUMENT;
        if (written) *written = 0;
        return VH_MAP_LOAD_PREFLIGHT_FAILED;
    }
    status = vh_map_load_before_units(memory, phase->map_number,
                  input_available, verified_output_capacity,
                  decode_status, written);
    if (status == VH_MAP_LOAD_OK) phase->map_valid = 1;
    return status;
}

#endif
