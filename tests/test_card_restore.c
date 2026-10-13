#include "card_restore.h"
#include "card_validate.h"

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
        for (bit = 0; bit < 8; ++bit) {
            crc = (crc & 1U) ? (crc >> 1) ^ UINT32_C(0xedb88320) : crc >> 1;
        }
    }
    return ~crc;
}

static void write_u32_le(uint8_t *p, uint32_t value)
{
    p[0] = (uint8_t)value;
    p[1] = (uint8_t)(value >> 8);
    p[2] = (uint8_t)(value >> 16);
    p[3] = (uint8_t)(value >> 24);
}

static size_t make_card(uint8_t *image, size_t header_size)
{
    memset(image, 0, IMAGE_CAP);
    image[0] = 'S'; image[1] = 'C'; image[2] = 0x12; image[3] = 0x02;
    write_u32_le(image + header_size, crc32_bytes(image + header_size + 4, 124));
    return header_size + LISTING_SIZE;
}

static void *mock_open(void *ctx, const char *dst, char *tmp, size_t cap)
{
    mock_fs *fs = (mock_fs *)ctx;
    (void)dst;
    fs->open_calls++;
    if (cap < sizeof("restore.tmp")) return NULL;
    memcpy(tmp, "restore.tmp", sizeof("restore.tmp"));
    return fs;
}
static int mock_write(void *ctx, void *handle, const void *data, size_t size)
{
    (void)ctx; (void)data; (void)size;
    return handle != NULL;
}
static int mock_flush(void *ctx, void *handle) { (void)ctx; return handle != NULL; }
static int mock_close(void *ctx, void *handle) { (void)ctx; return handle != NULL; }
static int mock_replace(void *ctx, const char *tmp, const char *dst)
{
    mock_fs *fs = (mock_fs *)ctx;
    assert(strcmp(tmp, "restore.tmp") == 0);
    assert(strcmp(dst, "active-card.bin") == 0);
    fs->replace_calls++;
    fs->destination_value = 99;
    return 1;
}
static void mock_remove(void *ctx, const char *tmp) { (void)ctx; (void)tmp; }

static const vh_atomic_write_ops OPS = {
    mock_open, mock_write, mock_flush, mock_close, mock_replace, mock_remove
};

int main(void)
{
    uint8_t image[IMAGE_CAP];
    size_t size;
    mock_fs fs;

    memset(&fs, 0, sizeof(fs));
    fs.destination_value = 7;
    size = make_card(image, US_HEADER);
    assert(vh_restore_card(&OPS, &fs, "active-card.bin", image, size, US_HEADER));
    assert(fs.open_calls == 1 && fs.replace_calls == 1 && fs.destination_value == 99);

    memset(&fs, 0, sizeof(fs));
    fs.destination_value = 7;
    size = make_card(image, US_HEADER);
    image[US_HEADER + 8] ^= 1U; /* invalidates listing CRC */
    assert(!vh_restore_card(&OPS, &fs, "active-card.bin", image, size, US_HEADER));
    assert(fs.open_calls == 0 && fs.replace_calls == 0 && fs.destination_value == 7);

    memset(&fs, 0, sizeof(fs));
    fs.destination_value = 7;
    size = make_card(image, JP_HEADER);
    assert(!vh_restore_card(&OPS, &fs, "active-card.bin", image, size, US_HEADER));
    assert(fs.open_calls == 0 && fs.replace_calls == 0 && fs.destination_value == 7);

    memset(&fs, 0, sizeof(fs));
    fs.destination_value = 7;
    size = make_card(image, JP_HEADER);
    assert(vh_restore_card(&OPS, &fs, "active-card.bin", image, size, JP_HEADER));
    assert(fs.open_calls == 1 && fs.replace_calls == 1);

    assert(!vh_restore_card(&OPS, &fs, "active-card.bin", image, size, 123U));
    puts("card restore coordinator tests: PASS");
    return 0;
}
