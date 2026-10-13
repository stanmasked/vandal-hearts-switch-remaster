#include "save_slot.h"

#include "card_validate.h"

#include <stdint.h>
#include <string.h>

enum {
    VH_SLOT_MAGIC_SIZE = 4,
    VH_SLOT_VERSION_OFFSET = 4,
    VH_SLOT_GENERATION_OFFSET = 8,
    VH_SLOT_PAYLOAD_SIZE_OFFSET = 16,
    VH_SLOT_CHECKSUM_OFFSET = 20,
    VH_SLOT_VERSION = 1
};

static const uint8_t VH_SLOT_MAGIC[VH_SLOT_MAGIC_SIZE] = {
    (uint8_t)'V', (uint8_t)'H', (uint8_t)'S', (uint8_t)'L'
};

/* Treat address-range overflow conservatively as overlap. */
static int ranges_overlap(const void *a, size_t a_size,
                          const void *b, size_t b_size)
{
    uintptr_t a_start;
    uintptr_t b_start;
    uintptr_t a_end;
    uintptr_t b_end;

    if (a_size == 0U || b_size == 0U) return 0;
    a_start = (uintptr_t)a;
    b_start = (uintptr_t)b;
    if (a_size > UINTPTR_MAX - a_start ||
        b_size > UINTPTR_MAX - b_start) {
        return 1;
    }
    a_end = a_start + a_size;
    b_end = b_start + b_size;
    return a_start < b_end && b_start < a_end;
}

static uint32_t read_u32_le(const uint8_t *p)
{
    return (uint32_t)p[0] |
           ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static uint64_t read_u64_le(const uint8_t *p)
{
    return (uint64_t)read_u32_le(p) |
           ((uint64_t)read_u32_le(p + 4) << 32);
}

static void write_u32_le(uint8_t *p, uint32_t value)
{
    p[0] = (uint8_t)value;
    p[1] = (uint8_t)(value >> 8);
    p[2] = (uint8_t)(value >> 16);
    p[3] = (uint8_t)(value >> 24);
}

static void write_u64_le(uint8_t *p, uint64_t value)
{
    write_u32_le(p, (uint32_t)value);
    write_u32_le(p + 4, (uint32_t)(value >> 32));
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

static uint32_t container_crc(const uint8_t *container, size_t payload_size)
{
    uint32_t crc = UINT32_C(0xffffffff);
    crc = crc32_update(crc, container, VH_SLOT_CHECKSUM_OFFSET);
    crc = crc32_update(crc, container + VH_SAVE_SLOT_HEADER_SIZE,
                       payload_size);
    return ~crc;
}

int vh_save_slot_encode(uint8_t *out, size_t out_capacity,
                        uint64_t generation, const uint8_t *card_image,
                        size_t card_image_size, size_t expected_header_size,
                        size_t *container_size_out)
{
    size_t validated_header_size = 0U;
    size_t total_size;

    if (out == NULL || generation == 0U || card_image == NULL ||
        card_image_size > UINT32_MAX ||
        card_image_size > (size_t)-1 - VH_SAVE_SLOT_HEADER_SIZE ||
        (expected_header_size != 384U && expected_header_size != 512U) ||
        !vh_card_validate_image(card_image, card_image_size,
                                &validated_header_size) ||
        validated_header_size != expected_header_size) {
        return 0;
    }

    total_size = VH_SAVE_SLOT_HEADER_SIZE + card_image_size;
    if (out_capacity < total_size ||
        ranges_overlap(out, total_size, card_image, card_image_size)) {
        return 0;
    }

    memset(out, 0, VH_SAVE_SLOT_HEADER_SIZE);
    memcpy(out, VH_SLOT_MAGIC, sizeof(VH_SLOT_MAGIC));
    write_u32_le(out + VH_SLOT_VERSION_OFFSET, VH_SLOT_VERSION);
    write_u64_le(out + VH_SLOT_GENERATION_OFFSET, generation);
    write_u32_le(out + VH_SLOT_PAYLOAD_SIZE_OFFSET,
                  (uint32_t)card_image_size);
    memcpy(out + VH_SAVE_SLOT_HEADER_SIZE, card_image, card_image_size);
    write_u32_le(out + VH_SLOT_CHECKSUM_OFFSET,
                 container_crc(out, card_image_size));

    if (container_size_out != NULL) {
        *container_size_out = total_size;
    }
    return 1;
}

int vh_save_slot_validate(const uint8_t *container, size_t container_size,
                          size_t expected_header_size,
                          uint64_t *generation_out,
                          const uint8_t **card_image_out,
                          size_t *card_image_size_out)
{
    uint32_t payload_size_u32;
    size_t payload_size;
    size_t actual_header_size = 0U;
    uint64_t generation;

    if (container == NULL ||
        container_size < VH_SAVE_SLOT_HEADER_SIZE ||
        (expected_header_size != 384U && expected_header_size != 512U) ||
        memcmp(container, VH_SLOT_MAGIC, sizeof(VH_SLOT_MAGIC)) != 0 ||
        read_u32_le(container + VH_SLOT_VERSION_OFFSET) != VH_SLOT_VERSION) {
        return 0;
    }

    generation = read_u64_le(container + VH_SLOT_GENERATION_OFFSET);
    payload_size_u32 = read_u32_le(container + VH_SLOT_PAYLOAD_SIZE_OFFSET);
    payload_size = (size_t)payload_size_u32;
    if (generation == 0U ||
        payload_size > (size_t)-1 - VH_SAVE_SLOT_HEADER_SIZE ||
        container_size != VH_SAVE_SLOT_HEADER_SIZE + payload_size ||
        read_u32_le(container + VH_SLOT_CHECKSUM_OFFSET) !=
            container_crc(container, payload_size) ||
        !vh_card_validate_image(container + VH_SAVE_SLOT_HEADER_SIZE,
                                payload_size, &actual_header_size) ||
        actual_header_size != expected_header_size) {
        return 0;
    }

    if (generation_out != NULL) *generation_out = generation;
    if (card_image_out != NULL) {
        *card_image_out = container + VH_SAVE_SLOT_HEADER_SIZE;
    }
    if (card_image_size_out != NULL) *card_image_size_out = payload_size;
    return 1;
}

vh_save_slot_selection vh_save_slot_select(
    const uint8_t *slot_a, size_t slot_a_size,
    const uint8_t *slot_b, size_t slot_b_size,
    size_t expected_header_size, unsigned int *selected_slot_out)
{
    uint64_t generation_a = 0U;
    uint64_t generation_b = 0U;
    const uint8_t *card_a = NULL;
    const uint8_t *card_b = NULL;
    size_t card_a_size = 0U;
    size_t card_b_size = 0U;
    int valid_a = vh_save_slot_validate(slot_a, slot_a_size,
                                        expected_header_size, &generation_a,
                                        &card_a, &card_a_size);
    int valid_b = vh_save_slot_validate(slot_b, slot_b_size,
                                        expected_header_size, &generation_b,
                                        &card_b, &card_b_size);

    if (!valid_a && !valid_b) return VH_SAVE_SLOT_INVALID;
    if (valid_a && !valid_b) {
        if (selected_slot_out != NULL) *selected_slot_out = 0U;
        return VH_SAVE_SLOT_VALID;
    }
    if (!valid_a && valid_b) {
        if (selected_slot_out != NULL) *selected_slot_out = 1U;
        return VH_SAVE_SLOT_VALID;
    }

    if (generation_a == generation_b) {
        if (card_a_size != card_b_size ||
            memcmp(card_a, card_b, card_a_size) != 0) {
            return VH_SAVE_SLOT_AMBIGUOUS;
        }
        if (selected_slot_out != NULL) *selected_slot_out = 0U;
        return VH_SAVE_SLOT_VALID;
    }

    if (selected_slot_out != NULL) {
        *selected_slot_out = generation_a > generation_b ? 0U : 1U;
    }
    return VH_SAVE_SLOT_VALID;
}
