#ifndef VH_AUDIO_SCENE_OPTICAL_H
#define VH_AUDIO_SCENE_OPTICAL_H

#include <stdint.h>
#include "vh_audio_scene_trace.h"
#include "software_renderer.h"

/* Fixed, bounded single-frame visual transport of post-join guest events.
 * One 924-byte packet occupies 112x66 black/white modules, each 7x7
 * framebuffer pixels. A magenta one-module border supplies scale and
 * position calibration to the screenshot decoder.
 *
 * NRO does not read these pixels back or use framebuffer timestamps as
 * a proxy for the DAC. No image is rendered until after the audio
 * worker has been joined. Never transmits content/asset pointers.
 */
#define VH_SCENE_OPTICAL_PACKET_BYTES 924u
#define VH_SCENE_OPTICAL_GRID_COLS 112u
#define VH_SCENE_OPTICAL_GRID_ROWS 66u
#define VH_SCENE_OPTICAL_MODULE 7u
#define VH_SCENE_OPTICAL_LEFT 250
#define VH_SCENE_OPTICAL_TOP 160
#define VH_SCENE_OPTICAL_BORDER (VH_SCENE_OPTICAL_MODULE)
#define VH_SCENE_OPTICAL_WIDTH ((VH_SCENE_OPTICAL_GRID_COLS+2u)*VH_SCENE_OPTICAL_MODULE)
#define VH_SCENE_OPTICAL_HEIGHT ((VH_SCENE_OPTICAL_GRID_ROWS+2u)*VH_SCENE_OPTICAL_MODULE)

/* Returns count 0..64 on success, -1 if invalid/pending.
 * CRC32 ISO-HDLC (IEEE reflected), little-endian. Reserved bytes must
 * be zero. Every used event carries its kind, scene, serial and
 * monotonic guest nanoseconds. */
int vh_audio_scene_optical_encode(const VhAudioSceneTrace *trace,
                                  uint8_t packet[VH_SCENE_OPTICAL_PACKET_BYTES]);
/* Draw over the framebuffer after joining the audio worker. Caller
 * supplies native pixel packing (RGBA8_MAXALPHA in libnx), avoiding
 * any portable-host dependence on Switch pixel channel order. */
/* Draw caller-owned CRC32 optical packet with the same calibrated border.
 * May only be invoked after the audout owner is joined. */
int vh_audio_scene_optical_draw_packet(VhCanvas *canvas,
    const uint8_t packet[VH_SCENE_OPTICAL_PACKET_BYTES],
    uint32_t black,uint32_t white,uint32_t marker);
int vh_audio_scene_optical_draw(VhCanvas *canvas,
                                const VhAudioSceneTrace *trace,
                                uint32_t black,uint32_t white,uint32_t marker);

#endif
