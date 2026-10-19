/* Asset-free PCM witness classification and optical payload regression. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "vh_audio_scene_trace.h"
#include "vh_audio_scene_optical.h"

int main(void) {
    VhAudioSceneTrace trace;
    uint8_t packet[VH_SCENE_OPTICAL_PACKET_BYTES];
    vh_audio_scene_trace_init(&trace);
    assert(vh_audio_scene_trace_record(&trace,
        VH_SCENE_TRACE_PCM_PAGE_NONZERO, 17u, 2u, UINT64_C(7777777)) == 1);
    assert(vh_audio_scene_trace_record(&trace,
        VH_SCENE_TRACE_PCM_PAGE_SILENT, 18u, 1u, UINT64_C(8888888)) == 1);
    assert(vh_audio_scene_trace_record(&trace,
        (VhAudioSceneTraceKind)9, 19u, 2u, UINT64_C(9999999)) == -1);
    assert(vh_audio_scene_trace_dropped(&trace) == 0u);
    VhAudioSceneTraceSlot slot;
    assert(vh_audio_scene_trace_snapshot(&trace, 0u, &slot) == 1);
    assert(slot.kind == VH_SCENE_TRACE_PCM_PAGE_NONZERO &&
           slot.serial == 17u && slot.scene == 2u);
    assert(vh_audio_scene_trace_snapshot(&trace, 1u, &slot) == 1);
    assert(slot.kind == VH_SCENE_TRACE_PCM_PAGE_SILENT &&
           slot.serial == 18u && slot.scene == 1u);
    assert(vh_audio_scene_optical_encode(&trace, packet) == 2);
    assert(packet[8] == 2u);
    assert(packet[13] == (uint8_t)VH_SCENE_TRACE_PCM_PAGE_NONZERO);
    assert(packet[14] == 2u && packet[15] == 17u);
    assert(packet[27] == (uint8_t)VH_SCENE_TRACE_PCM_PAGE_SILENT);
    assert(packet[28] == 1u && packet[29] == 18u);
    puts("PASS: both first-page PCM witness kinds retain ticket provenance");
    return 0;
}
