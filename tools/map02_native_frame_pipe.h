#ifndef VH_MAP02_NATIVE_FRAME_PIPE_H
#define VH_MAP02_NATIVE_FRAME_PIPE_H

/*
 * Diagnostic-only producer for the private MAP02 Linux ELF stdout protocol.
 * This module is not compiled into production builds. Only a completed,
 * caller-owned framebuffer may be passed to vh_map02_frame_pipe_emit().
 * The caller is responsible for buffer lifetime and GPU flush sequencing.
 *
 * Link with -DVH_MAP02_PRIVATE_FRAME_PIPE_TRACE=1 on a Linux host only.
 * Return 0 on success, -1 on errors (errno set). No allocation.
 */
#include <stdint.h>

int vh_map02_frame_pipe_wait_release(int input_fd);

/* BGR555 words are encoded little-endian. stride is in uint16_t pixels.
 * width/height <= 1024, 0 < frame <= UINT32_MAX, width*height*2 <= 2MiB,
 * width <= stride_pixels <= 4096. No writes on invalid parameters.
 */
int vh_map02_frame_pipe_emit(int output_fd, uint32_t frame,
                              uint32_t width, uint32_t height,
                              const uint16_t *completed_pixels,
                              uint32_t stride_pixels);

#endif
