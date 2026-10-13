#include "archive_restore.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum { US_HEADER = 384, JP_HEADER = 512, LISTING_SIZE = 128, IMAGE_CAP = 640 };

typedef struct {
    int open_calls;
    int replace_calls;
    int destination_value;
} mock_fs;

static uint32_t crc32_bytes(const uint8_t *data, size_t size)
{
    uint32_t crc = UINT32_C(0xffffffff);
    size_t i;
    for (i = 0; i < size; ++i) {
        unsigned int bit;
        crc ^= data[i];
        for (bit = 0; bit < 8; ++bit)
            crc = (crc & 1U) ? (crc >> 1) ^ UINT32_C(0xedb88320) : crc >> 1;
    }
    return ~crc;
}

static void put_u32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

static size_t make_card(uint8_t *image, size_t header)
{
    memset(image, 0, IMAGE_CAP);
    image[0] = 'S'; image[1] = 'C'; image[2] = 0x12; image[3] = 0x02;
    put_u32(image + header, crc32_bytes(image + header + 4, 124));
    return header + LISTING_SIZE;
}

static void *open_temp(void *ctx, const char *dst, char *tmp, size_t cap)
{
    mock_fs *fs = (mock_fs *)ctx;
    (void)dst;
    fs->open_calls++;
    if (cap < sizeof("archive.tmp")) return NULL;
    memcpy(tmp, "archive.tmp", sizeof("archive.tmp"));
    return fs;
}
static int write_all(void *ctx, void *h, const void *p, size_t n)
{ (void)ctx; (void)p; (void)n; return h != NULL; }
static int flush_file(void *ctx, void *h) { (void)ctx; return h != NULL; }
static int close_file(void *ctx, void *h) { (void)ctx; return h != NULL; }
static int replace_file(void *ctx, const char *tmp, const char *dst)
{
    mock_fs *fs = (mock_fs *)ctx;
    assert(strcmp(tmp, "archive.tmp") == 0);
    assert(strcmp(dst, "active-card.bin") == 0);
    fs->replace_calls++;
    fs->destination_value = 99;
    return 1;
}
static void remove_temp(void *ctx, const char *tmp) { (void)ctx; (void)tmp; }

static const vh_atomic_write_ops OPS = {
    open_temp, write_all, flush_file, close_file, replace_file, remove_temp
};

int main(void)
{
    uint8_t image[IMAGE_CAP];
    size_t size;
    mock_fs fs;

    memset(&fs, 0, sizeof(fs));
    fs.destination_value = 7;
    size = make_card(image, US_HEADER);
    assert(vh_restore_archive(&OPS, &fs, "active-card.bin",
        "BASLUS-00447VH.20261013-203000", "BASLUS-00447VH",
        image, size, US_HEADER));
    assert(fs.open_calls == 1 && fs.replace_calls == 1 && fs.destination_value == 99);

    memset(&fs, 0, sizeof(fs));
    fs.destination_value = 7;
    assert(!vh_restore_archive(&OPS, &fs, "active-card.bin",
        "../BASLUS-00447VH.backup", "BASLUS-00447VH",
        image, size, US_HEADER));
    assert(fs.open_calls == 0 && fs.replace_calls == 0 && fs.destination_value == 7);

    memset(&fs, 0, sizeof(fs));
    fs.destination_value = 7;
    assert(!vh_restore_archive(&OPS, &fs, "active-card.bin",
        "BISLPM-86007VH.20261013-203000", "BASLUS-00447VH",
        image, size, US_HEADER));
    assert(fs.open_calls == 0 && fs.replace_calls == 0 && fs.destination_value == 7);

    memset(&fs, 0, sizeof(fs));
    fs.destination_value = 7;
    image[US_HEADER + 8] ^= 1U;
    assert(!vh_restore_archive(&OPS, &fs, "active-card.bin",
        "BASLUS-00447VH.20261013-203000", "BASLUS-00447VH",
        image, size, US_HEADER));
    assert(fs.open_calls == 0 && fs.replace_calls == 0 && fs.destination_value == 7);

    puts("archive restore coordinator tests: PASS");
    return 0;
}
