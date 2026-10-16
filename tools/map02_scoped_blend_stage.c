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

#define VH_STAGE_LIMIT (16u * 1024u)
#define VH_BLEND_PENDING "blendg1-native-events.pending.jsonl"
#define VH_PIXEL_PENDING "putpixel-native-events.pending.jsonl"

/* Staged files are not trusted final evidence: the Python publisher requires
 * verified original DrawOTag/VRAM records and a separate SHA-bound manifest. */
typedef struct VHStageFile {
    char data[VH_STAGE_LIMIT];
    char temp_name[128];
    size_t size;
    const char *final_name;
    int fd;
    int temporary;
    int linked;
} VHStageFile;

static int append_line(VHStageFile *file, const char *line, int count) {
    if (count <= 0 || (size_t)count > sizeof(file->data) - file->size)
        return 0;
    memcpy(file->data + file->size, line, (size_t)count);
    file->size += (size_t)count;
    return 1;
}

static int collect(VHStageFile *pixels, VHStageFile *blends, int paired) {
    char line[512];
    unsigned i, count = vh_map02_scope_count();
    if (vh_map02_scope_failed() || !count || count >= 64u) return 0;
    for (i = 0; i < count; i++) {
        VHMap02BlendEvent event;
        int size;
        if (!vh_map02_scope_copy(i, &event)) return 0;
        if (paired) {
            size = vh_map02_scope_format_putpixel(i, line, sizeof(line));
            if (!append_line(pixels, line, size)) return 0;
        }
        if (event.has_blend) {
            size = vh_map02_scope_format_blendg1(i, line, sizeof(line));
            if (!append_line(blends, line, size)) return 0;
        }
    }
    if (!blends->size || blends->data[blends->size - 1] != '\n')
        return 0;
    if (paired && (!pixels->size || pixels->data[pixels->size - 1] != '\n'))
        return 0;
    return 1;
}

static int write_all(int fd, const char *buf, size_t len) {
    size_t written = 0;
    while (written < len) {
        ssize_t result = write(fd, buf + written, len - written);
        if (result < 0 && errno == EINTR) continue;
        if (result <= 0) return 0;
        written += (size_t)result;
    }
    return 1;
}

static int read_equal(int fd, const char *expected, size_t len) {
    char chunk[512];
    size_t offset = 0;
    if (lseek(fd, 0, SEEK_SET) != 0) return 0;
    while (offset < len) {
        size_t want = len - offset;
        ssize_t got;
        if (want > sizeof(chunk)) want = sizeof(chunk);
        got = read(fd, chunk, want);
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0 || memcmp(chunk, expected + offset, (size_t)got))
            return 0;
        offset += (size_t)got;
    }
    { char extra; ssize_t got;
      do { got = read(fd, &extra, 1); } while (got < 0 && errno == EINTR);
      return got == 0;
    }
}

static int create_checked_temp(int dirfd, VHStageFile *file, unsigned slot) {
    unsigned attempt;
    for (attempt = 0; attempt < 32u; attempt++) {
        int count = snprintf(file->temp_name, sizeof(file->temp_name),
            ".vh-map02-%u.%ld.%u.tmp", slot, (long)getpid(), attempt);
        if (count < 0 || (size_t)count >= sizeof(file->temp_name))
            return 0;
        file->fd = openat(dirfd, file->temp_name,
                          O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC | O_RDWR,
                          0600);
        if (file->fd >= 0) { file->temporary = 1; break; }
        if (errno != EEXIST) return 0;
    }
    if (!file->temporary) return 0;
    if (fchmod(file->fd, 0600) != 0 ||
        !write_all(file->fd, file->data, file->size) ||
        fsync(file->fd) != 0 ||
        !read_equal(file->fd, file->data, file->size))
        return 0;
    if (close(file->fd) != 0) { file->fd = -1; return 0; }
    file->fd = -1;
    return 1;
}

static int stage(const char *private_directory, int paired) {
    VHStageFile files[2];
    struct stat directory_stat;
    int dirfd = -1, ok = 0;
    unsigned i, active = paired ? 2u : 1u;

    memset(files, 0, sizeof files);
    files[0].fd = files[1].fd = -1;
    files[0].final_name = VH_BLEND_PENDING;
    files[1].final_name = VH_PIXEL_PENDING;
    if (!private_directory || !*private_directory ||
        !collect(&files[1], &files[0], paired)) return 0;

    dirfd = open(private_directory,
                 O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (dirfd < 0) return 0;
    if (fstat(dirfd, &directory_stat) ||
        !S_ISDIR(directory_stat.st_mode) ||
        directory_stat.st_uid != geteuid() ||
        (directory_stat.st_mode & 0777) != 0700)
        goto done;

    /* Write and verify BOTH temp files before exposing either final name.
     * Exclusive hard-links refuse existing files and symlinks. */
    for (i = 0; i < active; i++)
        if (!create_checked_temp(dirfd, &files[i], i)) goto done;
    for (i = 0; i < active; i++) {
        if (linkat(dirfd, files[i].temp_name, dirfd,
                   files[i].final_name, 0) != 0) goto done;
        files[i].linked = 1;
    }
    if (fsync(dirfd) != 0) goto done;
    for (i = 0; i < active; i++) {
        if (unlinkat(dirfd, files[i].temp_name, 0) != 0) goto done;
        files[i].temporary = 0;
    }
    if (fsync(dirfd) != 0) goto done;
    ok = 1;
done:
    if (!ok) {
        for (i = 0; i < active; i++)
            if (files[i].linked)
                (void)unlinkat(dirfd, files[i].final_name, 0);
    }
    for (i = 0; i < active; i++) {
        if (files[i].temporary)
            (void)unlinkat(dirfd, files[i].temp_name, 0);
        if (files[i].fd >= 0) (void)close(files[i].fd);
    }
    if (dirfd >= 0) (void)close(dirfd);
    return ok;
}

int vh_map02_stage_private_blendg1(const char *private_directory) {
    return stage(private_directory, 0);
}

int vh_map02_stage_private_pair(const char *private_directory) {
    return stage(private_directory, 1);
}
