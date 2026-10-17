#define _POSIX_C_SOURCE 200809L
#include "map02_scoped_blend_stage.h"
#include "map02_scoped_blend_sink.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#ifdef VH_MAP02_VRAM_EDGE_PROBE
#include "map02_vram_edges.h"
#endif
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#define VH_STAGE_LIMIT (16u * 1024u)
#define VH_BLEND_PENDING "blendg1-native-events.pending.jsonl"
#define VH_PIXEL_PENDING "putpixel-native-events.pending.jsonl"
#define VH_EDGE_PENDING "vram-edges-native-events.pending.jsonl"
#define VH_EDGE_LIMIT (2u * 1024u * 1024u)

/* Staged files are not trusted final evidence: the Python publisher requires
 * verified original DrawOTag/VRAM records and a separate SHA-bound manifest. */
typedef struct VHStageFile {
    char data[VH_STAGE_LIMIT];
    char *external_data;
    size_t capacity;
    char temp_name[128];
    size_t size;
    const char *final_name;
    int fd;
    int temporary;
    int linked;
} VHStageFile;

static const char *payload(const VHStageFile *file) {
    return file->external_data ? file->external_data : file->data;
}

static int append_line(VHStageFile *file, const char *line, int count) {
    if (count <= 0 || (size_t)count > file->capacity - file->size)
        return 0;
    memcpy((char *)payload(file) + file->size, line, (size_t)count);
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
    if (!blends->size || payload(blends)[blends->size - 1] != '\n')
        return 0;
    if (paired && (!pixels->size || payload(pixels)[pixels->size - 1] != '\n'))
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
        !write_all(file->fd, payload(file), file->size) ||
        fsync(file->fd) != 0 ||
        !read_equal(file->fd, payload(file), file->size))
        return 0;
    if (close(file->fd) != 0) { file->fd = -1; return 0; }
    file->fd = -1;
    return 1;
}

static int stage(const char *private_directory, int paired) {
    VHStageFile files[3];
    struct stat directory_stat;
    int dirfd = -1, ok = 0;
    unsigned i, active = paired ? 2u : 1u;

    memset(files, 0, sizeof files);
    files[0].fd = files[1].fd = files[2].fd = -1;
    files[0].final_name = VH_BLEND_PENDING;
    files[1].final_name = VH_PIXEL_PENDING;
    files[2].final_name = VH_EDGE_PENDING;
    for (i = 0; i < 3u; ++i) files[i].capacity = VH_STAGE_LIMIT;
    if (!private_directory || !*private_directory ||
        !collect(&files[1], &files[0], paired)) return 0;
#ifdef VH_MAP02_VRAM_EDGE_PROBE
    if (paired) {
        char line[256];
        unsigned edge_count, edge;
        active = 3u;
        edge_count = vh_map02_edges_count();
        if (vh_map02_edges_failed() || !edge_count ||
            edge_count > VH_MAP02_MAX_DRAW_EDGES) goto done;
        files[2].external_data = (char *)malloc(VH_EDGE_LIMIT);
        if (!files[2].external_data) goto done;
        files[2].capacity = VH_EDGE_LIMIT;
        for (edge = 0; edge < edge_count; ++edge) {
            int n = vh_map02_edges_format_jsonl(edge, line, sizeof(line));
            if (!append_line(&files[2], line, n)) goto done;
        }
        if (!files[2].size ||
            payload(&files[2])[files[2].size - 1] != '\n') goto done;
    }
#endif

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
    free(files[2].external_data);
    return ok;
}

int vh_map02_stage_private_blendg1(const char *private_directory) {
    return stage(private_directory, 0);
}

int vh_map02_stage_private_pair(const char *private_directory) {
    return stage(private_directory, 1);
}
