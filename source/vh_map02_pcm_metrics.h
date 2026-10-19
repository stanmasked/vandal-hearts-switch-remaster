#ifndef VH_MAP02_PCM_METRICS_H
#define VH_MAP02_PCM_METRICS_H
#include <stdint.h>
#include <stddef.h>
#include "software_renderer.h"

/* This research-only witness is owned by the native audio thread;
 * consumers access it only after threadWaitForExit. No pointers to
 * samples survive capture, and no data is written to storage. */
#define VH_MAP02_PCM_METRIC_PACKET_BYTES 924u
typedef struct {
    unsigned serial, scene, frames, nonzero, peak;
    uint64_t sum_squares, fnv1a64;
} VhMap02PcmMetric;
typedef struct {
    VhMap02PcmMetric items[2];
    unsigned captured_mask;
} VhMap02PcmMetrics;

void vh_map02_pcm_metrics_init(VhMap02PcmMetrics *metrics);
/* Returns 1 newly captured, 0 irrelevant/repeated ticket, -1 invalid.
 * Only ticket 1 / selected scene 2 and ticket 2 / field scene 1 count. */
int vh_map02_pcm_metrics_capture(VhMap02PcmMetrics *metrics,
    unsigned serial, unsigned scene, const int16_t *pcm, size_t frames);
/* Returns 2 only with both tickets; CRC-checked reserved-zero sidecar. */
int vh_map02_pcm_metrics_encode(const VhMap02PcmMetrics *metrics,
    uint8_t packet[VH_MAP02_PCM_METRIC_PACKET_BYTES]);
/* Call ONLY after audout owner joined, using same magenta optical frame. */
int vh_map02_pcm_metrics_draw(VhCanvas *canvas, const VhMap02PcmMetrics *metrics,
    uint32_t black, uint32_t white, uint32_t marker);
#endif
