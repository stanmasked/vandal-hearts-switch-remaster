#ifndef VANDAL_HEARTS_SWITCH_RGB24_PRESENTER_H
#define VANDAL_HEARTS_SWITCH_RGB24_PRESENTER_H

#include <GLES2/gl2.h>
#include "rgb24_frame.h"
#include "switch_presenter_layout.h"

/* Requires a current GLES2 context. Does not create a window or swap buffers. */
typedef struct {
    GLuint program;
    GLuint vertex_buffer;
    GLuint texture;
    GLint sampler_location;
    int initialized;
} VhSwitchRgb24Presenter;

/* Returns 1 on success, 0 on failure. Safe to call destroy after failed init. */
int vh_switch_rgb24_presenter_init(VhSwitchRgb24Presenter *presenter);

/* Uploads a borrowed bottom-up packed RGB24 frame; data must remain valid for this call. */
int vh_switch_rgb24_presenter_upload(VhSwitchRgb24Presenter *presenter,
                                     const VhRgb24Frame *frame);

/* Draws the most recently uploaded frame inside the supplied viewport, preserving aspect ratio. */
int vh_switch_rgb24_presenter_draw(VhSwitchRgb24Presenter *presenter,
                                   int viewport_width, int viewport_height);

/* Releases owned GL objects. Requires the same current GLES2 context. */
void vh_switch_rgb24_presenter_destroy(VhSwitchRgb24Presenter *presenter);

#endif
