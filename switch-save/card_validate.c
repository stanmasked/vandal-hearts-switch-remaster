#include "card_validate.h"

#include <stdint.h>

enum {
    VH_CARD_HEADER_US = 384,
    VH_CARD_HEADER_JP = 512,
    VH_CARD_LISTING_SIZE = 128,
    VH_CARD_RECORD_STRIDE = 0x400,
    VH_CARD_SAVE_SIZE = 0x300,
    VH_CARD_SLOT_COUNT = 3
};

static uint32_t read_u32_le(const uint8_t *p)
{
    return (uint32_t)p[0] |
           ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static uint32_t crc32_bytes(const uint8_t *data, size_t size)
{
    uint32_t crc = UINT32_C(0xffffffff);
    size_t i;

    for (i = 0; i < size; ++i) {
        unsigned int bit;
        crc ^= data[i];
        for (bit = 0; bit < 8; ++bit) {
            crc = (crc & 1U) != 0U
                ? (crc >> 1) ^ UINT32_C(0xedb88320)
                : crc >> 1;
        }
    }
    return ~crc;
}

static int span_fits(size_t image_size, size_t offset, size_t length)
{
    return offset <= image_size && length <= image_size - offset;
}

static int validate_layout(const uint8_t *image, size_t image_size,
                            size_t header_size)
{
    const uint8_t *listing;
    size_t slot;

    if (!span_fits(image_size, header_size, VH_CARD_LISTING_SIZE)) {
        return 0;
    }

    listing = image + header_size;
    if (read_u32_le(listing) != crc32_bytes(listing + 4, 124)) {
        return 0;
    }

    for (slot = 0; slot < VH_CARD_SLOT_COUNT; ++slot) {
        size_t record_offset;
        const uint8_t *record;

        if (listing[4 + slot] == 0) {
            continue;
        }

        /* Card record n begins one stride after the listing's header. */
        if (slot + 1U > (size_t)-1 / VH_CARD_RECORD_STRIDE) {
            return 0;
        }
        record_offset = header_size + (slot + 1U) * VH_CARD_RECORD_STRIDE;
        if (record_offset < header_size ||
            !span_fits(image_size, record_offset, VH_CARD_SAVE_SIZE)) {
            return 0;
        }

        record = image + record_offset;
        if (read_u32_le(record) !=
            crc32_bytes(record + 4, VH_CARD_SAVE_SIZE - 4U)) {
            return 0;
        }
    }

    return 1;
}

int vh_card_validate_image(const uint8_t *image, size_t image_size,
                           size_t *header_size_out)
{
    static const size_t header_sizes[] = {
        VH_CARD_HEADER_US, VH_CARD_HEADER_JP
    };
    size_t i;

    if (image == NULL || image_size < 4U ||
        image[0] != (uint8_t)'S' || image[1] != (uint8_t)'C' ||
        image[2] != UINT8_C(0x12) || image[3] != UINT8_C(0x02)) {
        return 0;
    }

    for (i = 0; i < sizeof(header_sizes) / sizeof(header_sizes[0]); ++i) {
        if (validate_layout(image, image_size, header_sizes[i])) {
            if (header_size_out != NULL) {
                *header_size_out = header_sizes[i];
            }
            return 1;
        }
    }
    return 0;
}
