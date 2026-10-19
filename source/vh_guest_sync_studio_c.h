#ifndef VH_GUEST_SYNC_STUDIO_C_H
#define VH_GUEST_SYNC_STUDIO_C_H
#include <stdint.h>
#include "software_renderer.h"

/* A synthetic, clock-aligned DSP research fixture in the Switch guest.
 * Never reads original PS1 assets, copies output PCM, or touches the
 * live audout owner. Must run after the audio worker has joined. */
typedef struct {
    uint64_t initial_hash, wet_hash, reset_hash;
    uint32_t pre_blocks, post_blocks, different_blocks;
    uint32_t wet_nonzero, reset_nonzero;
    uint32_t pre_note_ons, next_note_ons;
    uint32_t verified_roundtrips;
    uint32_t failure_line; /* 0 only if all checks succeeded */
} VhGuestSyncStudioC;

int vh_guest_sync_studio_c_run(VhGuestSyncStudioC *result);
int vh_guest_sync_studio_c_draw(VhCanvas *canvas,
    const VhGuestSyncStudioC *metrics,
    uint32_t black, uint32_t white, uint32_t marker);
#endif
