/* MAP02 same-process ordering observer. No retail data or VRAM retained.
 * All calls must be linked into ONE real instrumented process to matter.
 * Synthetic tests exercise the state machine, not the original game loop. */
#define _POSIX_C_SOURCE 200809L
#include "map02_cycle_order.h"
#include "map02_capture_session.h"
#include "map02_cd_read_probe.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <sys/stat.h>
#include <unistd.h>

#define MAP02_LBA 0x1bcc
#define MAP02_SECTORS 12
#define OUTPUT_NAME "map02-single-process-cycle.jsonl"
#define SEAL_NAME "map02-cycle-clean-exit.jsonl"

static struct {
    int step, failed;
    unsigned frame, draw_primitives;
} observed;

/* Two 64-event native windows hold fewer than 128 events; every supported
 * DRAW needs paired before/after snapshots. Bound to 63 complete pairs. */
#define MAP02_MAX_DRAW_PAIRS 63u

static int overlaps_map02_extent(int lba, int sectors) {
    int64_t start = (int64_t)lba;
    int64_t end = start + (int64_t)sectors;
    return sectors > 0 && end > MAP02_LBA &&
           start < MAP02_LBA + MAP02_SECTORS;
}

static void transition(int expected, int next) {
    if (observed.step != expected) observed.failed = 1;
    else observed.step = next;
}
static int selected_frame(unsigned frame) {
    const char *s = getenv("VH_MAP02_PROBE_FRAME");
    unsigned long long value = 0;
    const unsigned char *p;
    if (!s || !*s) return 0; /* no explicit selection, no witness */
    for (p = (const unsigned char *)s; *p; ++p) {
        if (*p < '0' || *p > '9') {
            observed.failed = 1;
            return 0;
        }
        value = 10u * value + (unsigned)(*p - '0');
        if (value > 0xffffffffULL) {
            observed.failed = 1;
            return 0;
        }
    }
    if (!value) { observed.failed = 1; return 0; }
    return value == frame;
}
void vh_map02_cycle_load(int cdf, int target, int lba, int sectors) {
    if (cdf != target) return;
    if (lba != MAP02_LBA || sectors != MAP02_SECTORS)
        observed.failed = 1;
    transition(0, 1);
}
void vh_map02_cycle_read_start(int lba, int sectors) {
    if (!overlaps_map02_extent(lba, sectors)) return;
    if (lba != MAP02_LBA || sectors != MAP02_SECTORS)
        observed.failed = 1;
    transition(1, 2);
}
void vh_map02_cycle_read_finish(int lba, int sectors) {
    if (!overlaps_map02_extent(lba, sectors)) return;
    if (lba != MAP02_LBA || sectors != MAP02_SECTORS)
        observed.failed = 1;
    transition(2, 3);
}
void vh_map02_cycle_loader_complete(int cdf, int target, int state) {
    if (cdf != target) return;
    if (state != 99) observed.failed = 1;
    transition(3, 4);
}
void vh_map02_cycle_draw_start(unsigned frame) {
    if (!selected_frame(frame)) return;
    transition(4, 5);
    observed.frame = frame;
    observed.draw_primitives = 0;
}
void vh_map02_cycle_draw_primitive(unsigned frame) {
    if (!selected_frame(frame)) return;
    if (observed.step != 5 || observed.frame != frame ||
            observed.draw_primitives >= MAP02_MAX_DRAW_PAIRS) {
        observed.failed = 1;
        return;
    }
    ++observed.draw_primitives;
}
int vh_map02_cycle_failed(void) {
    char cd_receipt[512];
    return observed.failed || vh_map02_cd_probe_failed() ||
           (observed.step == 6 &&
            vh_map02_cd_probe_format_jsonl(cd_receipt, sizeof cd_receipt) <= 0);
}
int vh_map02_cycle_format_jsonl(char *out, size_t capacity) {
    const char *token;
    char cd_receipt[512];
    unsigned raw_crc32;
    char raw_sha256[65];
    int n;
    if (observed.failed || observed.step != 6 || !out || !capacity ||
            !observed.draw_primitives ||
            observed.draw_primitives > MAP02_MAX_DRAW_PAIRS)
        return 0;
    /* This receipt can only be published after BOTH observers agree:
     * 12 consecutive original sectors copied without CRC modification,
     * one completed loader, and the ordered DrawOTag boundary. The CD
     * receipt is privately staged separately; never embed its raw values. */
    if (vh_map02_cd_probe_failed() ||
        vh_map02_cd_probe_format_jsonl(cd_receipt, sizeof cd_receipt) <= 0 ||
        !vh_map02_cd_probe_raw_crc32(&raw_crc32) ||
        !vh_map02_cd_probe_raw_sha256_hex(raw_sha256))
        return 0;
    token = vh_map02_capture_session_token();
    if (!token || strlen(token) != 32u) return 0;
    n = snprintf(out, capacity,
        "{\"schema\":\"vh.map02.cycle-order.v4\","
        "\"capture_session\":\"%s\",\"gpu_draw_frame\":%u,"
        "\"original_cd_raw_user_crc32\":\"%08x\","
        "\"original_cd_raw_user_sha256\":\"%s\","
        "\"observed_draw_primitive_count\":%u,"
        "\"ordered_source_hooks_observed\":true,"
        "\"cd_payload_verified_by_this_receipt\":false,"
        "\"original_map02_rendering_proven\":false,"
        "\"physical_ps1_equivalence_proven\":false}\n",
        token, observed.frame, raw_crc32, raw_sha256,
        observed.draw_primitives);
    return n > 0 && (size_t)n < capacity ? n : 0;
}
/* Identity is checked both via the opened file descriptor and the
 * directory entry: same-name substitution cannot satisfy this audit.
 * No game data is written; only the bounded JSONL capture metadata. */
static int same_inode(const struct stat *a, const struct stat *b) {
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino;
}
static int same_contents_metadata(const struct stat *a, const struct stat *b) {
    /* chmod/chown/link changes are part of evidence identity, even if the
     * inode and receipt bytes stay the same between fsync/read passes. */
    return same_inode(a, b) && a->st_uid == b->st_uid &&
           a->st_mode == b->st_mode && a->st_nlink == b->st_nlink &&
           a->st_size == b->st_size &&
           a->st_mtim.tv_sec == b->st_mtim.tv_sec &&
           a->st_mtim.tv_nsec == b->st_mtim.tv_nsec &&
           a->st_ctim.tv_sec == b->st_ctim.tv_sec &&
           a->st_ctim.tv_nsec == b->st_ctim.tv_nsec;
}
static int verify_published_fd(int dfd, int fd, const char *name,
                               const char *data, size_t length,
                               const struct stat *baseline) {
    struct stat file, named, after;
    char checked[512];
    size_t done = 0;
    if (length > sizeof checked ||
        fstat(fd, &file) || !same_contents_metadata(&file, baseline) ||
        !S_ISREG(file.st_mode) || file.st_uid != geteuid() ||
        (file.st_mode & 0777) != 0600 || file.st_nlink != 1 ||
        file.st_size != (off_t)length ||
        fstatat(dfd, name, &named, AT_SYMLINK_NOFOLLOW) ||
        !same_contents_metadata(&file, &named) ||
        !S_ISREG(named.st_mode))
        return 0;
    while (done < length) {
        ssize_t n = pread(fd, checked + done, length - done, (off_t)done);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return 0;
        done += (size_t)n;
    }
    if (memcmp(data, checked, length) != 0 ||
        fstat(fd, &after) || !same_contents_metadata(&file, &after) ||
        fstatat(dfd, name, &named, AT_SYMLINK_NOFOLLOW) ||
        !same_contents_metadata(&file, &named))
        return 0;
    return 1;
}

/* DrawOTag's receipt is provisional until the normal atexit path.
 * A successful exit writes a second exclusively created, independently
 * checked owner-private copy of the SAME receipt. The private verifier
 * requires both different inodes with identical data. _exit(0) bypasses
 * atexit and CANNOT create this clean-exit seal. Late CD/order errors
 * revoke the provisional receipt instead. No foreign inode is deleted. */
static struct {
    int armed, dirfd;
    struct stat file, directory;
    char directory_path[4096];
} published;

/* The original name must continue to resolve to the verified directory,
 * not merely to a new private directory replacing it after DrawOTag.
 * Directory mtime/ctime can legitimately change as receipts are created,
 * so compare stable inode/owner/mode/link metadata only. */
static int same_private_directory(const struct stat *a, const struct stat *b) {
    return S_ISDIR(a->st_mode) && S_ISDIR(b->st_mode) &&
           same_inode(a, b) && a->st_uid == b->st_uid &&
           a->st_mode == b->st_mode && a->st_nlink == b->st_nlink &&
           (a->st_mode & 0777) == 0700;
}
static int published_directory_still_named(void) {
    struct stat fdinfo, named;
    return published.armed &&
           !fstat(published.dirfd, &fdinfo) &&
           !fstatat(AT_FDCWD, published.directory_path, &named,
                    AT_SYMLINK_NOFOLLOW) &&
           same_private_directory(&published.directory, &fdinfo) &&
           same_private_directory(&published.directory, &named);
}

static void revoke_invalid_cycle_at_exit(void) {
    struct stat directory, named, seal_baseline = {0}, seal_named;
    int fd = -1, seal_fd = -1, seal_created = 0, clean = 0, n;
    char data[512];
    if (!published.armed) return;
    if (fstat(published.dirfd, &directory) ||
        !published_directory_still_named())
        goto done;
    if (vh_map02_cycle_failed()) goto done;
    n = vh_map02_cycle_format_jsonl(data, sizeof data);
    if (!n) goto done;
    fd = openat(published.dirfd, OUTPUT_NAME,
                O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0 ||
        !verify_published_fd(published.dirfd, fd, OUTPUT_NAME,
                             data, (size_t)n, &published.file))
        goto done;
    /* No seal can be issued merely by observing a zero process exit code.
     * Only this normal-exit handler, reached after all recorded hooks,
     * creates it; a missing/malformed/existing seal fails closed. */
    seal_fd = openat(published.dirfd, SEAL_NAME,
                     O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (seal_fd < 0) goto done;
    seal_created = 1;
    if (fstat(seal_fd, &seal_baseline)) goto done;
    if (write(seal_fd, data, (size_t)n) != n ||
        fsync(seal_fd) || fstat(seal_fd, &seal_baseline) ||
        !verify_published_fd(published.dirfd, seal_fd, SEAL_NAME,
                             data, (size_t)n, &seal_baseline) ||
        fsync(published.dirfd) ||
        !published_directory_still_named() ||
        !verify_published_fd(published.dirfd, seal_fd, SEAL_NAME,
                             data, (size_t)n, &seal_baseline) ||
        !verify_published_fd(published.dirfd, fd, OUTPUT_NAME,
                             data, (size_t)n, &published.file))
        goto done;
    if (close(seal_fd)) { seal_fd = -1; goto done; }
    seal_fd = -1;
    if (fstatat(published.dirfd, SEAL_NAME, &seal_named,
                AT_SYMLINK_NOFOLLOW) ||
        !same_contents_metadata(&seal_baseline, &seal_named) ||
        !published_directory_still_named())
        goto done;
    clean = 1;
done:
    if (seal_fd >= 0) (void)close(seal_fd);
    if (fd >= 0) (void)close(fd);
    if (!clean) {
        if (seal_created &&
            !fstatat(published.dirfd, SEAL_NAME, &named,
                     AT_SYMLINK_NOFOLLOW) &&
            S_ISREG(named.st_mode) && same_inode(&seal_baseline, &named))
            (void)unlinkat(published.dirfd, SEAL_NAME, 0);
        if (!fstatat(published.dirfd, OUTPUT_NAME, &named,
                     AT_SYMLINK_NOFOLLOW) &&
            S_ISREG(named.st_mode) && same_inode(&published.file, &named))
            (void)unlinkat(published.dirfd, OUTPUT_NAME, 0);
        (void)fsync(published.dirfd);
    }
    (void)close(published.dirfd);
    published.dirfd = -1;
    published.armed = 0;
}

/* Only an explicit, owned 0700 directory receives one exclusive 0600
 * receipt. Open with O_RDWR so every byte is re-read after fsync; a second
 * complete read after directory fsync catches post-write replacement.
 * Never delete a foreign/replaced inode on cleanup. */
static void publish_if_requested(void) {
    const char *directory = getenv("VH_MAP02_CYCLE_OUTPUT_DIR");
    char data[512];
    int dfd = -1, fd = -1, n, ok = 0, created = 0;
    struct stat st, baseline, named;
    ssize_t written;
    if (!directory || !*directory) return;
    if (strlen(directory) >= sizeof published.directory_path) {
        observed.failed = 1;
        return;
    }
    n = vh_map02_cycle_format_jsonl(data, sizeof data);
    if (!n) { observed.failed = 1; return; }
    dfd = open(directory, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (dfd < 0) goto done;
    if (fstat(dfd, &st) || !S_ISDIR(st.st_mode) ||
        st.st_uid != geteuid() || (st.st_mode & 0777) != 0700) goto done;
    fd = openat(dfd, OUTPUT_NAME,
                O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0) goto done;
    created = 1;
    if (fstat(fd, &baseline)) goto done;
    written = write(fd, data, (size_t)n);
    if (written != n || fsync(fd)) goto done;
    /* Capture the metadata AFTER our own write. Subsequent in-place
     * changes can no longer pass the before/after metadata checks. */
    if (fstat(fd, &baseline) ||
        !verify_published_fd(dfd, fd, OUTPUT_NAME, data, (size_t)n, &baseline) ||
        fsync(dfd) ||
        !verify_published_fd(dfd, fd, OUTPUT_NAME, data, (size_t)n, &baseline))
        goto done;
    if (close(fd)) { fd = -1; goto done; }
    fd = -1;
    if (fstatat(dfd, OUTPUT_NAME, &named, AT_SYMLINK_NOFOLLOW) ||
        !same_contents_metadata(&baseline, &named) ||
        fstatat(AT_FDCWD, directory, &named, AT_SYMLINK_NOFOLLOW) ||
        !same_private_directory(&st, &named) ||
        published.armed || atexit(revoke_invalid_cycle_at_exit))
        goto done;
    published.file = baseline;
    published.directory = st;
    memcpy(published.directory_path, directory, strlen(directory) + 1);
    published.dirfd = dfd;
    published.armed = 1;
    dfd = -1; /* exit guard owns the verified directory descriptor */
    ok = 1;
done:
    if (fd >= 0) (void)close(fd);
    if (!ok) {
        /* Cleanup must never remove a same-name symlink or replacement.
         * A concurrent rename after this check remains a POSIX race;
         * the independent verifier must re-open and audit final bytes. */
        if (dfd >= 0 && created &&
            !fstatat(dfd, OUTPUT_NAME, &named, AT_SYMLINK_NOFOLLOW) &&
            same_inode(&baseline, &named) && S_ISREG(named.st_mode))
            (void)unlinkat(dfd, OUTPUT_NAME, 0);
        observed.failed = 1;
    }
    if (dfd >= 0) (void)close(dfd);
}
void vh_map02_cycle_draw_finish(unsigned frame, int walk_complete) {
    if (!selected_frame(frame)) return;
    if (frame != observed.frame || !walk_complete ||
            !observed.draw_primitives) observed.failed = 1;
    transition(5, 6);
    if (!observed.failed) publish_if_requested();
}
