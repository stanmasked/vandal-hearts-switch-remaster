#include "save_slot.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { CARD_HEADER_US = 384, CARD_LISTING_SIZE = 128, CARD_SIZE = 512 };

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

static uint32_t crc32_update(uint32_t crc, const uint8_t *data, size_t size)
{
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
    return crc;
}

static uint32_t container_crc(const uint8_t *container, size_t total_size)
{
    uint32_t crc = UINT32_C(0xffffffff);
    crc = crc32_update(crc, container, 20U);
    crc = crc32_update(crc, container + VH_SAVE_SLOT_HEADER_SIZE,
                       total_size - VH_SAVE_SLOT_HEADER_SIZE);
    return ~crc;
}

static void make_card(uint8_t card[CARD_SIZE], uint8_t marker)
{
    uint8_t *listing;
    memset(card, 0, CARD_SIZE);
    card[0] = 'S';
    card[1] = 'C';
    card[2] = 0x12;
    card[3] = 0x02;
    card[10] = marker; /* unused header byte, outside the listing checksum */
    listing = card + CARD_HEADER_US;
    write_u32_le(listing, crc32_bytes(listing + 4, CARD_LISTING_SIZE - 4U));
}

static size_t encode(uint8_t *out, uint64_t generation,
                     const uint8_t card[CARD_SIZE])
{
    size_t size = 0U;
    assert(vh_save_slot_encode(out, VH_SAVE_SLOT_HEADER_SIZE + CARD_SIZE,
                               generation, card, CARD_SIZE, CARD_HEADER_US,
                               &size) == 1);
    assert(size == VH_SAVE_SLOT_HEADER_SIZE + CARD_SIZE);
    return size;
}

int main(void)
{
    uint8_t card_a[CARD_SIZE];
    uint8_t card_b[CARD_SIZE];
    uint8_t slot_a[VH_SAVE_SLOT_HEADER_SIZE + CARD_SIZE];
    uint8_t slot_b[VH_SAVE_SLOT_HEADER_SIZE + CARD_SIZE];
    uint8_t corrupt[VH_SAVE_SLOT_HEADER_SIZE + CARD_SIZE];
    size_t size_a;
    size_t size_b;
    size_t payload_size = 0U;
    uint64_t generation = 0U;
    const uint8_t *payload = NULL;
    unsigned int selected = 99U;

    make_card(card_a, 0x11U);
    make_card(card_b, 0x22U);
    size_a = encode(slot_a, 3U, card_a);
    size_b = encode(slot_b, 4U, card_b);

    assert(vh_save_slot_validate(slot_a, size_a, CARD_HEADER_US,
                                 &generation, &payload, &payload_size) == 1);
    assert(generation == 3U && payload_size == CARD_SIZE);
    assert(payload != NULL && memcmp(payload, card_a, CARD_SIZE) == 0);

    assert(vh_save_slot_select(NULL, 0U, NULL, 0U, CARD_HEADER_US,
                               &selected) == VH_SAVE_SLOT_INVALID);

    assert(vh_save_slot_select(slot_a, size_a, NULL, 0U, CARD_HEADER_US,
                               &selected) == VH_SAVE_SLOT_VALID);
    assert(selected == 0U);

    assert(vh_save_slot_select(slot_a, size_a, slot_b, size_b, CARD_HEADER_US,
                               &selected) == VH_SAVE_SLOT_VALID);
    assert(selected == 1U);

    memcpy(corrupt, slot_b, size_b);
    corrupt[size_b - 1U] ^= 0x80U;
    assert(vh_save_slot_validate(corrupt, size_b, CARD_HEADER_US,
                                 NULL, NULL, NULL) == 0);
    assert(vh_save_slot_select(slot_a, size_a, corrupt, size_b, CARD_HEADER_US,
                               &selected) == VH_SAVE_SLOT_VALID);
    assert(selected == 0U);

    assert(vh_save_slot_validate(slot_a, size_a - 1U, CARD_HEADER_US,
                                 NULL, NULL, NULL) == 0);
    assert(vh_save_slot_validate(slot_a, size_a, 512U,
                                 NULL, NULL, NULL) == 0);

    memcpy(corrupt, slot_a, size_a);
    write_u32_le(corrupt + 4, 2U); /* unsupported envelope version */
    /* Keep checksum valid so this specifically exercises version rejection. */
    write_u32_le(corrupt + 20, container_crc(corrupt, size_a));
    assert(vh_save_slot_validate(corrupt, size_a, CARD_HEADER_US,
                                 NULL, NULL, NULL) == 0);

    assert(vh_save_slot_encode(slot_a, size_a - 1U, 5U, card_a, CARD_SIZE,
                               CARD_HEADER_US, NULL) == 0);
    assert(vh_save_slot_encode(slot_a, size_a, 0U, card_a, CARD_SIZE,
                               CARD_HEADER_US, NULL) == 0);

    size_a = encode(slot_a, 7U, card_a);
    size_b = encode(slot_b, 7U, card_a);
    assert(vh_save_slot_select(slot_a, size_a, slot_b, size_b, CARD_HEADER_US,
                               &selected) == VH_SAVE_SLOT_VALID);
    assert(selected == 0U);

    size_b = encode(slot_b, 7U, card_b);
    assert(vh_save_slot_select(slot_a, size_a, slot_b, size_b, CARD_HEADER_US,
                               &selected) == VH_SAVE_SLOT_AMBIGUOUS);

    size_a = encode(slot_a, UINT64_MAX, card_a);
    size_b = encode(slot_b, UINT64_MAX - 1U, card_b);
    assert(vh_save_slot_select(slot_a, size_a, slot_b, size_b, CARD_HEADER_US,
                               &selected) == VH_SAVE_SLOT_VALID);
    assert(selected == 0U);

    puts("save slot container tests: PASS");
    return 0;
}
