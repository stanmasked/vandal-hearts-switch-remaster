#include "archive_reader.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum { US_HEADER = 384, LISTING_SIZE = 128, IMAGE_CAP = 640 };

typedef struct {
    int open_calls, read_calls, close_calls;
    int fail_open;
    int read_success, close_success;
    int write_open_calls, replace_calls;
    size_t reported_size;
    uint8_t image[IMAGE_CAP];
} fixture;

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

static void make_card(fixture *f)
{
    memset(f->image, 0, sizeof(f->image));
    f->image[0] = 'S'; f->image[1] = 'C';
    f->image[2] = 0x12; f->image[3] = 0x02;
    put_u32(f->image + US_HEADER,
            crc32_bytes(f->image + US_HEADER + 4, 124));
    f->reported_size = US_HEADER + LISTING_SIZE;
}

static void *read_open(void *ctx, const char *name)
{
    fixture *f = (fixture *)ctx;
    f->open_calls++;
    assert(strcmp(name, "BASLUS-00447VH.20261013-203000") == 0);
    return f->fail_open ? NULL : f;
}
static int read_all(void *ctx, void *h, uint8_t *buffer,
                    size_t capacity, size_t *size)
{
    fixture *f = (fixture *)ctx;
    f->read_calls++;
    assert(h == f);
    if (!f->read_success) return 0;
    *size = f->reported_size;
    if (*size > capacity) return 0;
    memcpy(buffer, f->image, *size);
    return 1;
}
static int read_close(void *ctx, void *h)
{
    fixture *f = (fixture *)ctx;
    f->close_calls++;
    assert(h == f);
    return f->close_success;
}
static void *write_open(void *ctx, const char *dst, char *tmp, size_t cap)
{
    fixture *f = (fixture *)ctx;
    (void)dst;
    f->write_open_calls++;
    if (cap < sizeof("restore.tmp")) return 0;
    memcpy(tmp, "restore.tmp", sizeof("restore.tmp"));
    return f;
}
static int write_all(void *ctx, void *h, const void *p, size_t n)
{ (void)ctx; (void)p; return h != 0 && n != 0; }
static int flush_file(void *ctx, void *h) { (void)ctx; return h != 0; }
static int close_file(void *ctx, void *h) { (void)ctx; return h != 0; }
static int replace_file(void *ctx, const char *tmp, const char *dst)
{
    fixture *f = (fixture *)ctx;
    assert(strcmp(tmp, "restore.tmp") == 0);
    assert(strcmp(dst, "active-card.bin") == 0);
    f->replace_calls++;
    return 1;
}
static void remove_temp(void *ctx, const char *tmp) { (void)ctx; (void)tmp; }

static const vh_archive_read_ops READ_OPS = {read_open, read_all, read_close};
static const vh_atomic_write_ops WRITE_OPS = {
    write_open, write_all, flush_file, close_file, replace_file, remove_temp
};

static int restore(fixture *f, uint8_t *buffer, size_t cap)
{
    return vh_restore_archive_file(&WRITE_OPS, &READ_OPS, f,
        "active-card.bin", "BASLUS-00447VH.20261013-203000",
        "BASLUS-00447VH", buffer, cap, US_HEADER);
}

int main(void)
{
    fixture f;
    uint8_t buffer[IMAGE_CAP];
    vh_archive_read_ops incomplete_read_ops = READ_OPS;

    memset(&f, 0, sizeof(f));
    make_card(&f); f.read_success = 1; f.close_success = 1;
    assert(restore(&f, buffer, sizeof(buffer)));
    assert(f.open_calls == 1 && f.read_calls == 1 && f.close_calls == 1);
    assert(f.write_open_calls == 1 && f.replace_calls == 1);

    memset(&f, 0, sizeof(f));
    make_card(&f); f.read_success = 0; f.close_success = 1;
    assert(!restore(&f, buffer, sizeof(buffer)));
    assert(f.close_calls == 1 && f.write_open_calls == 0 && f.replace_calls == 0);

    memset(&f, 0, sizeof(f));
    make_card(&f); f.read_success = 1; f.close_success = 0;
    assert(!restore(&f, buffer, sizeof(buffer)));
    assert(f.close_calls == 1 && f.write_open_calls == 0 && f.replace_calls == 0);

    memset(&f, 0, sizeof(f));
    make_card(&f); f.read_success = 1; f.close_success = 1;
    f.reported_size = sizeof(buffer) + 1;
    assert(!restore(&f, buffer, sizeof(buffer)));
    assert(f.close_calls == 1 && f.write_open_calls == 0 && f.replace_calls == 0);

    /* An empty archive is not a valid card image and must never reach writes. */
    memset(&f, 0, sizeof(f));
    make_card(&f); f.read_success = 1; f.close_success = 1;
    f.reported_size = 0;
    assert(!restore(&f, buffer, sizeof(buffer)));
    assert(f.close_calls == 1 && f.write_open_calls == 0 && f.replace_calls == 0);

    /* A too-small caller buffer must fail closed and still close the reader. */
    memset(&f, 0, sizeof(f));
    make_card(&f); f.read_success = 1; f.close_success = 1;
    assert(!restore(&f, buffer, US_HEADER));
    assert(f.close_calls == 1 && f.write_open_calls == 0 && f.replace_calls == 0);

    /* Missing reader callbacks are rejected before opening the archive. */
    memset(&f, 0, sizeof(f));
    make_card(&f); f.read_success = 1; f.close_success = 1;
    incomplete_read_ops.close_archive = NULL;
    assert(!vh_restore_archive_file(&WRITE_OPS, &incomplete_read_ops, &f,
        "active-card.bin", "BASLUS-00447VH.20261013-203000",
        "BASLUS-00447VH", buffer, sizeof(buffer), US_HEADER));
    assert(f.open_calls == 0 && f.write_open_calls == 0);

    /* Failed open must not attempt read, close, or destination mutation. */
    memset(&f, 0, sizeof(f));
    make_card(&f); f.fail_open = 1; f.read_success = 1; f.close_success = 1;
    assert(!restore(&f, buffer, sizeof(buffer)));
    assert(f.open_calls == 1 && f.read_calls == 0 && f.close_calls == 0);
    assert(f.write_open_calls == 0 && f.replace_calls == 0);

    memset(&f, 0, sizeof(f));
    make_card(&f); f.read_success = 1; f.close_success = 1;
    assert(!vh_restore_archive_file(&WRITE_OPS, &READ_OPS, &f,
        "active-card.bin", "../BASLUS-00447VH.backup", "BASLUS-00447VH",
        buffer, sizeof(buffer), US_HEADER));
    assert(f.open_calls == 0 && f.write_open_calls == 0);

    puts("archive reader and restore tests: PASS");
    return 0;
}
