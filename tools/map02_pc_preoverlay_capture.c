#define _POSIX_C_SOURCE 200809L
#include "map02_pc_preoverlay_capture.h"
#include "map02_capture_session.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#define RGB_FILE "map02-pc-present-preoverlay-rgb24.bin"
#define RECEIPT_FILE "map02-pc-present-preoverlay-receipt.jsonl"
#define MAX_RGB_BYTES (1024u * 512u * 3u)

static int consumed;

/* Selection belongs to this same process; never accept attacker-supplied
 * nonce strings. VH_MAP02_PROBE_FRAME is shared with the cycle-order gate. */
static int selected(unsigned frame) {
    const char *v = getenv("VH_MAP02_PROBE_FRAME");
    char *end = NULL;
    unsigned long n;
    if (!v || !*v || *v < '0' || *v > '9') return -1;
    errno = 0;
    n = strtoul(v, &end, 10);
    if (errno || !end || *end || !n || n > UINT_MAX) return -1;
    return n == frame ? 1 : 0;
}

static int same_inode(const struct stat *a, const struct stat *b) {
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino &&
           a->st_uid == b->st_uid && a->st_nlink == b->st_nlink;
}

static int persist_checked(int dir, const char *name,
                           const unsigned char *data, size_t size,
                           struct stat *identity) {
    int fd, ok = 0;
    size_t done = 0;
    unsigned char scratch[4096];
    struct stat named;
    fd = openat(dir, name, O_CREAT | O_EXCL | O_RDWR |
                O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) return -1;
    if (fchmod(fd, 0600)) goto finish;
    if (fstat(fd, identity) || !S_ISREG(identity->st_mode) ||
            identity->st_nlink != 1) goto finish;
    while (done < size) {
        ssize_t n = write(fd, data + done, size - done);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) goto finish;
        done += (size_t)n;
    }
    if (fsync(fd)) goto finish;
    if (fstat(fd, &named) || !same_inode(identity, &named) ||
            (size_t)named.st_size != size) goto finish;
    done = 0;
    while (done < size) {
        size_t chunk = size - done > sizeof scratch ? sizeof scratch : size - done;
        ssize_t n = pread(fd, scratch, chunk, (off_t)done);
        if (n < 0 && errno == EINTR) continue;
        if (n != (ssize_t)chunk || memcmp(data + done, scratch, chunk))
            goto finish;
        done += chunk;
    }
    if (fstatat(dir, name, &named, AT_SYMLINK_NOFOLLOW) ||
            !same_inode(identity, &named) || !S_ISREG(named.st_mode) ||
            (named.st_mode & 0777) != 0600) goto finish;
    ok = 1;
finish:
    if (close(fd)) ok = 0;
    return ok ? 0 : -1;
}

static void unlink_if_owned(int dir, const char *name, const struct stat *owned) {
    struct stat named;
    if (owned->st_ino && !fstatat(dir, name, &named, AT_SYMLINK_NOFOLLOW) &&
            S_ISREG(named.st_mode) && same_inode(owned, &named))
        (void)unlinkat(dir, name, 0);
}

int vh_map02_pc_capture_preoverlay(unsigned frame, const unsigned char *bottom_up_rgb,
                                    unsigned width, unsigned height,
                                    int movie_overlay, int hires_active) {
    const char *output = getenv("VH_MAP02_PC_PREOVERLAY_OUTPUT_DIR");
    const char *token;
    struct stat directory, named, raw_id = {0}, receipt_id = {0};
    char json[512];
    int dfd = -1, ok = 0, choice, n;
    size_t size;
    if (!output || !*output) return 1;  /* capture strictly opt-in */
    choice = selected(frame);
    if (choice < 0) return 0;
    if (!choice) return 1;
    if (consumed++) return 0;  /* selected-frame capture is single-shot */
    if (!bottom_up_rgb || movie_overlay || hires_active ||
            width == 0 || height == 0 || width > 1024 || height > 512 ||
            (size_t)width * height > MAX_RGB_BYTES / 3u)
        return 0;
    token = vh_map02_capture_session_token();
    if (!token || strlen(token) != 32u) return 0;
    for (n = 0; n < 32; ++n) {
        if (!((token[n] >= '0' && token[n] <= '9') ||
              (token[n] >= 'a' && token[n] <= 'f'))) return 0;
    }
    size = (size_t)width * height * 3u;
    n = snprintf(json, sizeof json,
        "{\"schema\":\"vh.map02.pc-preoverlay-capture.v1\","
        "\"capture_session\":\"%s\",\"gpu_draw_frame\":%u,"
        "\"width\":%u,\"height\":%u,\"bytes\":%zu,"
        "\"pixel_format\":\"rgb24-bottom-up\","
        "\"movie_overlay_active\":false,\"hires_active\":false,"
        "\"source_pinned\":true,\"presented_window_authenticated\":false}\n",
        token, frame, width, height, size);
    if (n <= 0 || (size_t)n >= sizeof json) return 0;
    dfd = open(output, O_DIRECTORY | O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (dfd < 0) return 0;
    if (fstat(dfd, &directory) || !S_ISDIR(directory.st_mode) ||
            directory.st_uid != geteuid() ||
            (directory.st_mode & 0777) != 0700) goto finish;
    if (persist_checked(dfd, RGB_FILE, bottom_up_rgb, size, &raw_id) ||
            persist_checked(dfd, RECEIPT_FILE,
                            (const unsigned char *)json, (size_t)n,
                            &receipt_id) ||
            fsync(dfd) ||
            fstatat(AT_FDCWD, output, &named, AT_SYMLINK_NOFOLLOW) ||
            !same_inode(&directory, &named) ||
            (named.st_mode & 0777) != 0700)
        goto finish;
    ok = 1;
finish:
    if (!ok) {
        unlink_if_owned(dfd, RECEIPT_FILE, &receipt_id);
        unlink_if_owned(dfd, RGB_FILE, &raw_id);
    }
    (void)close(dfd);
    return ok;
}
