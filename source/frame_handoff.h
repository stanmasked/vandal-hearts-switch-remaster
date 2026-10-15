#ifndef VH_FRAME_HANDOFF_H
#define VH_FRAME_HANDOFF_H
#include "rgb24_frame.h"

/* Callback borrows frame pixels only until it returns. No retention allowed. */
typedef int (*VhFrameConsumer)(void *context, const VhRgb24Frame *frame);

/* Synchronous frame handoff; rejects invalid frames without invoking consumer. */
static inline int vh_frame_handoff(const VhRgb24Frame *frame,
                                   VhFrameConsumer consumer, void *context) {
    if (!vh_rgb24_frame_valid(frame) || !consumer)
        return 0;
    return consumer(context, frame) ? 1 : 0;
}
#endif
