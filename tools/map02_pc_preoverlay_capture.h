/* Explicit, private same-process native PC RGB24 capture.
 * Captures before SDL overlays, only for the selected DrawOTag frame.
 * This is not a PS1 screen equivalence / authentic retail provenance proof. */
#ifndef VH_MAP02_PC_PREOVERLAY_CAPTURE_H
#define VH_MAP02_PC_PREOVERLAY_CAPTURE_H
#include <stddef.h>
int vh_map02_pc_capture_preoverlay(unsigned frame, const unsigned char *bottom_up_rgb,
                                    unsigned width, unsigned height,
                                    int movie_overlay, int hires_active);
#endif
