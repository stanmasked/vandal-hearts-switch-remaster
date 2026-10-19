#ifndef VH_GUEST_SYNC_STUDIO_C_H
#define VH_GUEST_SYNC_STUDIO_C_H
#include <stdint.h>
#include "software_renderer.h"

/* A synthetic, clock-aligned DSP research fixture in the Switch guest.
 * Never reads original PS1 assets, copies output PCM, or touches the
 * live audout owner. Must run after the audio worker has joined. */
typedef struct {
    uint64_t prefix_hash, wet_hash, reset_hash;
    uint32_t prefix_frames, tail_frames, different_pages;
    uint32_t wet_nonzero, reset_first_page_nonzero, reset_later_nonzero;
    uint32_t verified_roundtrips;
} VhGuestNative48k;

typedef struct {
    uint64_t initial_hash, wet_hash, reset_hash;
    uint32_t pre_blocks, post_blocks, different_blocks;
    uint32_t wet_nonzero, reset_nonzero;
    uint32_t pre_note_ons, next_note_ons;
    uint32_t verified_roundtrips;
    uint32_t failure_line; /* 0 only if all checks succeeded */
    VhGuestNative48k native48;
} VhGuestSyncStudioC;

int vh_guest_sync_studio_c_run(VhGuestSyncStudioC *result);
int vh_guest_sync_studio_c_encode(const VhGuestSyncStudioC *metrics,
    uint8_t packet[924]);
void vh_guest_native_48k_init(VhGuestNative48k *metrics);
int vh_guest_native_48k_observe(VhGuestNative48k *metrics,
    const int16_t *wet_pcm, const int16_t *reset_pcm,
    unsigned tail, unsigned tail_index);
int vh_guest_native_48k_encode(const VhGuestSyncStudioC *metrics,
    uint8_t packet[924]);
int vh_guest_native_48k_draw(VhCanvas *canvas,
    const VhGuestSyncStudioC *metrics,
    uint32_t black, uint32_t white, uint32_t marker);
int vh_guest_sync_studio_c_draw(VhCanvas *canvas,
    const VhGuestSyncStudioC *metrics,
    uint32_t black, uint32_t white, uint32_t marker);
#endif
