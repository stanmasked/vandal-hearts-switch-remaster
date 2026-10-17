#include "map02_cd_read_probe.h"
#include "map02_capture_session.h"
#include <stdint.h>
#include <stdio.h>

#define MAP02_LBA 0x1bcc
#define MAP02_SECTORS 12
#define USER_SECTOR 2048

/* Intentionally no raw game bytes or addresses in global storage. */
static struct {
    unsigned claimed, started, finished, completed, count, failed;
    unsigned raw_crc, transferred_crc;
    int observing;
} state;

static int overlaps_map02_extent(int lba, int sectors) {
    int64_t start = (int64_t)lba;
    int64_t end = start + (int64_t)sectors;
    return sectors > 0 && end > MAP02_LBA &&
           start < MAP02_LBA + MAP02_SECTORS;
}

static uint32_t crc32_append(uint32_t crc, const unsigned char *data,
                             size_t size) {
    size_t i;
    for (i = 0; i < size; i++) {
        unsigned bit;
        crc ^= data[i];
        for (bit = 0; bit < 8; bit++)
            crc = (crc >> 1) ^ ((crc & 1u) ? 0xedb88320u : 0u);
    }
    return crc;
}

void vh_map02_cd_loader_claim(int cdf, int target_cdf, int lba, int sectors) {
    if (cdf != target_cdf) return;
    if (state.claimed++ || lba != MAP02_LBA || sectors != MAP02_SECTORS)
        state.failed = 1;
}

void vh_map02_cd_read_start(int lba, int sectors) {
    if (!overlaps_map02_extent(lba, sectors)) return;
    if (!state.claimed || state.started++ || lba != MAP02_LBA ||
            sectors != MAP02_SECTORS || state.finished)
        state.failed = 1;
    state.observing = 1;
    state.raw_crc = 0xffffffffu;
}

void vh_map02_cd_read_sector(int lba, const unsigned char *user2048) {
    if (!state.observing) return;
    if (!user2048 || lba != MAP02_LBA + (int)state.count ||
            state.count >= MAP02_SECTORS) {
        state.failed = 1;
        return;
    }
    state.raw_crc = crc32_append(state.raw_crc, user2048, USER_SECTOR);
    state.count++;
}

void vh_map02_cd_read_finish(int lba, int sectors,
                             const unsigned char *transferred) {
    if (!state.observing) return;
    if (lba != MAP02_LBA || sectors != MAP02_SECTORS ||
            state.count != MAP02_SECTORS || !transferred || state.finished++)
        state.failed = 1;
    if (transferred) {
        state.transferred_crc = crc32_append(
            0xffffffffu, transferred, MAP02_SECTORS * USER_SECTOR);
        /* Original game material must not be silently modified by
         * PC_LangPatchRead or a translation pack for source comparison. */
        if (state.transferred_crc != state.raw_crc) state.failed = 1;
    }
    state.observing = 0;
}

void vh_map02_cd_loader_complete(int cdf, int target_cdf, int state_after) {
    if (cdf != target_cdf) return;
    if (state_after != 99 || state.completed++ || state.claimed != 1 ||
            state.started != 1 || state.finished != 1 ||
            state.count != MAP02_SECTORS)
        state.failed = 1;
}

int vh_map02_cd_probe_failed(void) {
    return (int)state.failed;
}

int vh_map02_cd_probe_raw_crc32(unsigned *out) {
    if (!out || state.failed || state.claimed != 1 || state.started != 1 ||
        state.finished != 1 || state.completed != 1 ||
        state.count != MAP02_SECTORS ||
        state.raw_crc != state.transferred_crc)
        return 0;
    *out = state.raw_crc ^ 0xffffffffu;
    return 1;
}

int vh_map02_cd_probe_format_jsonl(char *out, size_t capacity) {
    const char *session;
    int n;
    if (state.failed || state.claimed != 1 || state.started != 1 ||
            state.finished != 1 || state.completed != 1 ||
            state.count != MAP02_SECTORS || !out || !capacity)
        return 0;
    session = vh_map02_capture_session_token();
    if (!session) return 0;
    n = snprintf(out, capacity,
        "{\"schema\":\"vh.map02.original-cd-read.v1\","
        "\"capture_session\":\"%s\","
        "\"source\":\"original-CdRead-and-ContinueLoadingCdFile\","
        "\"cdf\":\"CDF_M_MAP02_PRS\","
        "\"lba\":%d,\"sectors\":%d,\"bytes\":%d,"
        "\"raw_user_crc32\":\"%08x\",\"returned_user_crc32\":\"%08x\","
        "\"loader_completed\":true}\n",
        session, MAP02_LBA, MAP02_SECTORS,
        MAP02_SECTORS * USER_SECTOR,
        (unsigned)(state.raw_crc ^ 0xffffffffu),
        (unsigned)(state.transferred_crc ^ 0xffffffffu));
    if (n <= 0 || (size_t)n >= capacity) return 0;
    return n;
}
