#ifndef VH_AUDOUT_PRESUBMIT_OPTICAL_H
#define VH_AUDOUT_PRESUBMIT_OPTICAL_H

#include "vh_audout_presubmit_witness.h"
#include "vh_audio_scene_optical.h"

/* A single 924-byte after-join optical receipt. The existing renderer
 * supplies a calibrated 112x66 screen, 7 px per bit, with magenta border.
 * This packet only attests to guest-owned BEFORE-CALL PCM observations.
 */
int vh_audout_presubmit_optical_encode(const VhAudoutPresubmitWitness *w,
    uint8_t packet[VH_SCENE_OPTICAL_PACKET_BYTES]);

#endif
