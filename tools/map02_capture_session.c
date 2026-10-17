#define _POSIX_C_SOURCE 200809L
#include "map02_capture_session.h"
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <unistd.h>

/* A fresh 128-bit OS-random value per process. No environment-supplied
 * "session ID" can impersonate a separate process's in-process token.
 * If randomness is unavailable, refuse publication rather than falling
 * back to predictable PID/time or constant IDs. */
const char *vh_map02_capture_session_token(void) {
    static char hex[33];
    static int initialized = 0;
    static int failed = 0;
    unsigned char bytes[16];
    static const char digits[] = "0123456789abcdef";
    size_t offset = 0;
    int fd;
    unsigned i;
    if (initialized) return failed ? NULL : hex;
    initialized = 1;
    failed = 1;
    fd = open("/dev/urandom", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return NULL;
    while (offset < sizeof(bytes)) {
        ssize_t n = read(fd, bytes + offset, sizeof(bytes) - offset);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { (void)close(fd); return NULL; }
        offset += (size_t)n;
    }
    if (close(fd) != 0) return NULL;
    for (i = 0; i < sizeof(bytes); ++i) {
        hex[2u * i] = digits[bytes[i] >> 4];
        hex[2u * i + 1] = digits[bytes[i] & 15u];
    }
    hex[32] = '\0';
    failed = 0;
    return hex;
}
