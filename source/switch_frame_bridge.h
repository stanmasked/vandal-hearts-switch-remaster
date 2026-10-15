#ifndef VH_SWITCH_FRAME_BRIDGE_H
#define VH_SWITCH_FRAME_BRIDGE_H

#include "frame_handoff.h"
#include "switch_rgb24_presenter.h"

/*
 * Call synchronously from the completed-frame boundary (PC_GpuPresent).
 * A current GLES2 context and initialized presenter are required.
 * The caller retains ownership of pixels; no pointers are retained.
 * This function uploads and draws, but does not swap the window buffers.
 */
int vh_switch_present_frame(VhSwitchRgb24Presenter *presenter,
                            const VhRgb24Frame *frame,
                            int viewport_width, int viewport_height);

#endif
