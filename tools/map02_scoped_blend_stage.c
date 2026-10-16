#define _POSIX_C_SOURCE 200809L
#include "map02_scoped_blend_stage.h"
#include "map02_scoped_blend_sink.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#define VH_STAGE_NAME "blendg1-native-events.pending.jsonl"
#define VH_STAGE_LIMIT (16u * 1024u)

static int write_all(int fd, const char *buf, size_t len) {
    size_t done = 0;
    while (done < len) {
        ssize_t result = write(fd, buf + done, len - done);
        if (result < 0 && errno == EINTR) continue;
        if (result <= 0) return 0;
        done += (size_t)result;
    }
    return 1;
}

static int read_equal(int fd, const char *expected, size_t len) {
    char chunk[512];
    size_t offset = 0;
    if (lseek(fd, 0, SEEK_SET) != 0) return 0;
    while (offset < len) {
        size_t want = len - offset;
        if (want > sizeof(chunk)) want = sizeof(chunk);
        ssize_t got = read(fd, chunk, want);
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0 || memcmp(chunk, expected + offset, (size_t)got)) return 0;
        offset += (size_t)got;
    }
    { char extra;
      ssize_t got;
      do { got = read(fd, &extra, 1); } while (got < 0 && errno == EINTR);
      return got == 0;
    }
}

/* Caller opts in with an explicit, owner-private directory (0700).
 * Returns 0 on incomplete capture or ANY publication/readback failure. */
int vh_map02_stage_private_blendg1(const char *private_directory) {
    char data[VH_STAGE_LIMIT], line[512], temp_name[128];
    unsigned count, i, attempt;
    size_t size = 0;
    int dirfd = -1, fd = -1, temporary = 0, linked = 0, ok = 0;
    struct stat directory_stat;
    if (!private_directory || !*private_directory || vh_map02_scope_failed()) return 0;
    count = vh_map02_scope_count();
    if (!count || count >= 64u) return 0;
    /* All rows are collected BEFORE any filesystem access. */
    for (i = 0; i < count; ++i) {
        VHMap02BlendEvent event;
        int n;
        if (!vh_map02_scope_copy(i, &event)) return 0;
        if (!event.has_blend) continue;
        n = vh_map02_scope_format_blendg1(i, line, sizeof(line));
        if (n <= 0 || (size_t)n > VH_STAGE_LIMIT - size) return 0;
        memcpy(data + size, line, (size_t)n);
        size += (size_t)n;
    }
    if (!size || data[size - 1] != '\n') return 0;
    dirfd = open(private_directory, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (dirfd < 0) return 0;
    if (fstat(dirfd, &directory_stat) != 0 ||
        !S_ISDIR(directory_stat.st_mode) ||
        directory_stat.st_uid != geteuid() ||
        (directory_stat.st_mode & 0777) != 0700) goto done;
    /* O_EXCL prevents races and collisions; O_NOFOLLOW refuses links. */
    for (attempt = 0; attempt < 32; ++attempt) {
        int n = snprintf(temp_name, sizeof(temp_name),
                         ".vh-map02-blend.%ld.%u.tmp", (long)getpid(), attempt);
        if (n < 0 || (size_t)n >= sizeof(temp_name)) goto done;
        fd = openat(dirfd, temp_name,
                    O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC | O_RDWR, 0600);
        if (fd >= 0) { temporary = 1; break; }
        if (errno != EEXIST) goto done;
    }
    if (!temporary) goto done;
    if (fchmod(fd, 0600) || !write_all(fd, data, size) ||
        fsync(fd) || !read_equal(fd, data, size)) goto done;
    /* Hard-link publication is exclusive; a preexisting staged log wins. */
    if (linkat(dirfd, temp_name, dirfd, VH_STAGE_NAME, 0) != 0) goto done;
    linked = 1;
    if (fsync(dirfd) != 0) goto done;
    if (unlinkat(dirfd, temp_name, 0) != 0) goto done;
    temporary = 0;
    if (fsync(dirfd) != 0) goto done;
    ok = 1;
done:
    if (!ok && linked) (void)unlinkat(dirfd, VH_STAGE_NAME, 0);
    if (temporary) (void)unlinkat(dirfd, temp_name, 0);
    if (fd >= 0) (void)close(fd);
    if (dirfd >= 0) (void)close(dirfd);
    return ok;
}
