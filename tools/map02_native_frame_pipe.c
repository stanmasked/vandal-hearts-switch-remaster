/*
 * Diagnostic-only BGR555 frame transport from a completed native framebuffer.
 *
 * This is a Linux ELF host adapter, not a PS1 GPU hook and not a production
 * renderer. Passing an arbitrary pointer can still forge a frame. It does
 * not authenticate framebuffer origin or authorize HD replacements.
 */
#ifndef VH_MAP02_PRIVATE_FRAME_PIPE_TRACE
#error "MAP02 private frame pipe must be explicitly enabled"
#endif
#if VH_MAP02_PRIVATE_FRAME_PIPE_TRACE != 1
#error "MAP02 private frame pipe requires diagnostic value 1"
#endif
#if !defined(__linux__)
#error "MAP02 native frame pipe requires a Linux host"
#endif

#include "map02_native_frame_pipe.h"
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <unistd.h>

_Static_assert(sizeof(uint16_t) == 2, "BGR555 requires 16-bit words");

static void little_u32(unsigned char *target, uint32_t value)
{
    target[0] = (unsigned char)value;
    target[1] = (unsigned char)(value >> 8);
    target[2] = (unsigned char)(value >> 16);
    target[3] = (unsigned char)(value >> 24);
}

static int write_all(int fd, const unsigned char *buffer, size_t count)
{
    while (count != 0) {
        ssize_t done = write(fd, buffer, count);
        if (done == -1 && errno == EINTR)
            continue;
        if (done <= 0) {
            if (done == 0)
                errno = EIO;
            return -1;
        }
        buffer += (size_t)done;
        count -= (size_t)done;
    }
    return 0;
}

int vh_map02_frame_pipe_wait_release(int input_fd)
{
    unsigned char gate = 0;
    ssize_t got;
    if (input_fd < 0) {
        errno = EINVAL;
        return -1;
    }
    do {
        got = read(input_fd, &gate, 1);
    } while (got == -1 && errno == EINTR);
    if (got != 1 || gate != 1) {
        errno = EPROTO;
        return -1;
    }
    return 0;
}

int vh_map02_frame_pipe_emit(int output_fd, uint32_t frame,
                             uint32_t width, uint32_t height,
                             const uint16_t *completed_pixels,
                             uint32_t stride_pixels)
{
    static const unsigned char magic[8] = {'V','H','M','2','F','R','M','1'};
    unsigned char header[20];
    unsigned char row[2048];
    uint32_t y, x;

    /* Validate everything we can before emitting the protocol header. */
    if (output_fd < 0 || frame == 0 || width == 0 || height == 0
            || width > 1024 || height > 1024
            || (uint64_t)width * (uint64_t)height * 2 > 2097152
            || stride_pixels < width || stride_pixels > 4096
            || completed_pixels == NULL) {
        errno = EINVAL;
        return -1;
    }
    for (x = 0; x < 8; ++x)
        header[x] = magic[x];
    little_u32(header + 8, frame);
    little_u32(header + 12, width);
    little_u32(header + 16, height);

    if (write_all(output_fd, header, sizeof(header)) != 0)
        return -1;
    for (y = 0; y < height; ++y) {
        const uint16_t *scanline = completed_pixels +
            (size_t)y * (size_t)stride_pixels;
        for (x = 0; x < width; ++x) {
            uint16_t pixel = scanline[x];
            row[x * 2] = (unsigned char)pixel;
            row[x * 2 + 1] = (unsigned char)(pixel >> 8);
        }
        if (write_all(output_fd, row, (size_t)width * 2) != 0)
            return -1;
    }
    return 0;
}
