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
#include <sys/stat.h>
#include <unistd.h>

#define MAP02_LBA 0x1bcc
#define MAP02_SECTORS 12
#define OUTPUT_NAME "map02-single-process-cycle.jsonl"

static struct {
    int step, failed;
    unsigned frame;
} observed;

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
    if (lba + sectors <= MAP02_LBA ||
        lba >= MAP02_LBA + MAP02_SECTORS) return;
    if (lba != MAP02_LBA || sectors != MAP02_SECTORS)
        observed.failed = 1;
    transition(1, 2);
}
void vh_map02_cycle_read_finish(int lba, int sectors) {
    if (lba + sectors <= MAP02_LBA ||
        lba >= MAP02_LBA + MAP02_SECTORS) return;
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
}
int vh_map02_cycle_failed(void) { return observed.failed; }
int vh_map02_cycle_format_jsonl(char *out, size_t capacity) {
    const char *token;
    char cd_receipt[512];
    int n;
    if (observed.failed || observed.step != 6 || !out || !capacity)
        return 0;
    /* This receipt can only be published after BOTH observers agree:
     * 12 consecutive original sectors copied without CRC modification,
     * one completed loader, and the ordered DrawOTag boundary. The CD
     * receipt is privately staged separately; never embed its raw values. */
    if (vh_map02_cd_probe_failed() ||
        vh_map02_cd_probe_format_jsonl(cd_receipt, sizeof cd_receipt) <= 0)
        return 0;
    token = vh_map02_capture_session_token();
    if (!token || strlen(token) != 32u) return 0;
    n = snprintf(out, capacity,
        "{\"schema\":\"vh.map02.cycle-order.v1\","
        "\"capture_session\":\"%s\",\"gpu_draw_frame\":%u,"
        "\"ordered_source_hooks_observed\":true,"
        "\"cd_payload_verified_by_this_receipt\":false,"
        "\"original_map02_rendering_proven\":false,"
        "\"physical_ps1_equivalence_proven\":false}\n",
        token, observed.frame);
    return n > 0 && (size_t)n < capacity ? n : 0;
}
/* Only an explicit, owned 0700 directory receives one exclusive 0600
 * receipt. No symlink following, fallback location, or replacement. */
static void publish_if_requested(void) {
    const char *directory = getenv("VH_MAP02_CYCLE_OUTPUT_DIR");
    char data[512];
    int dfd = -1, fd = -1, n, ok = 0, created = 0;
    struct stat st;
    ssize_t written;
    if (!directory || !*directory) return;
    n = vh_map02_cycle_format_jsonl(data, sizeof data);
    if (!n) { observed.failed = 1; return; }
    dfd = open(directory, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (dfd < 0) goto done;
    if (fstat(dfd, &st) || !S_ISDIR(st.st_mode) ||
        st.st_uid != geteuid() || (st.st_mode & 0777) != 0700) goto done;
    fd = openat(dfd, OUTPUT_NAME,
                O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0) goto done;
    created = 1;
    written = write(fd, data, (size_t)n);
    if (written != n || fsync(fd)) goto done;
    if (close(fd)) { fd = -1; goto done; }
    fd = -1;
    if (fsync(dfd)) goto done;
    ok = 1;
done:
    if (fd >= 0) (void)close(fd);
    if (!ok) {
        /* Never unlink a pre-existing file: created is set only after O_EXCL. */
        if (dfd >= 0 && created) (void)unlinkat(dfd, OUTPUT_NAME, 0);
        observed.failed = 1;
    }
    if (dfd >= 0) (void)close(dfd);
}
void vh_map02_cycle_draw_finish(unsigned frame, int walk_complete) {
    if (!selected_frame(frame)) return;
    if (frame != observed.frame || !walk_complete) observed.failed = 1;
    transition(5, 6);
    if (!observed.failed) publish_if_requested();
}
