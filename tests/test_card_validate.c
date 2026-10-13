#include "card_validate.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum {
    HEADER_US = 384,
    HEADER_JP = 512,
    LISTING_SIZE = 128,
    RECORD_STRIDE = 0x400,
    SAVE_SIZE = 0x300,
    IMAGE_SIZE = HEADER_JP + 3 * RECORD_STRIDE + SAVE_SIZE
};

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

static void write_u32_le(uint8_t *p, uint32_t value)
{
    p[0] = (uint8_t)value;
    p[1] = (uint8_t)(value >> 8);
    p[2] = (uint8_t)(value >> 16);
    p[3] = (uint8_t)(value >> 24);
}

static void set_crc(uint8_t *data, size_t size)
{
    write_u32_le(data, crc32_bytes(data + 4, size - 4));
}

static uint8_t *make_image(size_t header_size, int occupied_slot)
{
    uint8_t *image = (uint8_t *)calloc(IMAGE_SIZE, 1);
    uint8_t *listing;
    assert(image != NULL);

    image[0] = 'S';
    image[1] = 'C';
    image[2] = 0x12;
    image[3] = 0x02;

    listing = image + header_size;
    if (occupied_slot >= 0) {
        size_t record_offset = header_size +
            ((size_t)occupied_slot + 1U) * RECORD_STRIDE;
        listing[4 + occupied_slot] = 1;
        /* Synthetic deterministic payload; checksum matches this fixture. */
        image[record_offset + 4] = 0x5a;
        image[record_offset + 5] = (uint8_t)occupied_slot;
        set_crc(image + record_offset, SAVE_SIZE);
    }
    set_crc(listing, LISTING_SIZE);
    return image;
}

int main(void)
{
    uint8_t *image;
    size_t header_size = 0;

    image = make_image(HEADER_US, 0);
    assert(vh_card_validate_image(image, IMAGE_SIZE, &header_size) == 1);
    assert(header_size == HEADER_US);
    free(image);

    image = make_image(HEADER_JP, 2);
    assert(vh_card_validate_image(image, IMAGE_SIZE, &header_size) == 1);
    assert(header_size == HEADER_JP);
    free(image);

    image = make_image(HEADER_US, -1);
    assert(vh_card_validate_image(image, IMAGE_SIZE, NULL) == 1);
    image[HEADER_US + 8] ^= 0x01; /* listing data no longer matches its CRC */
    assert(vh_card_validate_image(image, IMAGE_SIZE, NULL) == 0);
    free(image);

    image = make_image(HEADER_US, 1);
    image[HEADER_US + RECORD_STRIDE + 4] ^= 0x80;
    assert(vh_card_validate_image(image, IMAGE_SIZE, NULL) == 0);
    free(image);

    image = make_image(HEADER_US, 2);
    assert(vh_card_validate_image(image, HEADER_US + 0x100, NULL) == 0);
    free(image);

    image = make_image(HEADER_US, -1);
    image[2] = 0;
    assert(vh_card_validate_image(image, IMAGE_SIZE, NULL) == 0);
    free(image);

    puts("card validation tests: PASS");
    return 0;
}
