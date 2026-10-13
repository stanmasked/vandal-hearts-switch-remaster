#include "save_update.h"

#include <stdint.h>
#include <string.h>

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

static int ops_valid(const vh_save_update_ops *ops)
{
    return ops != NULL && ops->read_slot != NULL &&
           ops->open_write != NULL && ops->write_all != NULL &&
           ops->flush != NULL && ops->close != NULL;
}

vh_save_update_result vh_save_slot_update(
    const vh_save_update_ops *ops, void *context,
    size_t expected_header_size,
    const uint8_t *card_image, size_t card_image_size,
    uint8_t *slot_a_buffer, uint8_t *slot_b_buffer, size_t slot_capacity,
    uint8_t *verify_buffer, size_t verify_capacity,
    unsigned int *selected_slot_out, uint64_t *generation_out)
{
    size_t size_a = 0U;
    size_t size_b = 0U;
    size_t verify_size = 0U;
    size_t encoded_size = 0U;
    uint64_t current_generation = 0U;
    uint64_t verify_generation = 0U;
    const uint8_t *current_card = NULL;
    const uint8_t *verify_card = NULL;
    size_t current_card_size = 0U;
    size_t verify_card_size = 0U;
    unsigned int current_slot = 0U;
    unsigned int target_slot;
    uint8_t *target_buffer;
    vh_save_io_result read_a;
    vh_save_io_result read_b;
    vh_save_slot_selection selection;
    int write_ok = 0;
    int flush_ok = 0;
    int close_ok = 0;

    if (!ops_valid(ops) || card_image == NULL ||
        slot_a_buffer == NULL || slot_b_buffer == NULL ||
        verify_buffer == NULL || slot_capacity < VH_SAVE_SLOT_HEADER_SIZE ||
        verify_capacity < VH_SAVE_SLOT_HEADER_SIZE ||
        ranges_overlap(slot_a_buffer, slot_capacity,
                       slot_b_buffer, slot_capacity) ||
        ranges_overlap(slot_a_buffer, slot_capacity,
                       verify_buffer, verify_capacity) ||
        ranges_overlap(slot_b_buffer, slot_capacity,
                       verify_buffer, verify_capacity) ||
        ranges_overlap(card_image, card_image_size,
                       slot_a_buffer, slot_capacity) ||
        ranges_overlap(card_image, card_image_size,
                       slot_b_buffer, slot_capacity) ||
        ranges_overlap(card_image, card_image_size,
                       verify_buffer, verify_capacity)) {
        return VH_SAVE_UPDATE_INVALID_ARGUMENT;
    }

    read_a = ops->read_slot(context, 0U, slot_a_buffer, slot_capacity, &size_a);
    read_b = ops->read_slot(context, 1U, slot_b_buffer, slot_capacity, &size_b);
    if ((read_a != VH_SAVE_IO_OK && read_a != VH_SAVE_IO_MISSING) ||
        (read_b != VH_SAVE_IO_OK && read_b != VH_SAVE_IO_MISSING) ||
        (read_a == VH_SAVE_IO_OK && size_a > slot_capacity) ||
        (read_b == VH_SAVE_IO_OK && size_b > slot_capacity)) {
        return VH_SAVE_UPDATE_IO_FAILURE;
    }
    if (read_a == VH_SAVE_IO_MISSING) size_a = 0U;
    if (read_b == VH_SAVE_IO_MISSING) size_b = 0U;

    selection = vh_save_slot_select(
        read_a == VH_SAVE_IO_OK ? slot_a_buffer : NULL, size_a,
        read_b == VH_SAVE_IO_OK ? slot_b_buffer : NULL, size_b,
        expected_header_size, &current_slot);
    if (selection == VH_SAVE_SLOT_AMBIGUOUS) {
        return VH_SAVE_UPDATE_AMBIGUOUS_BASE;
    }
    if (selection != VH_SAVE_SLOT_VALID) {
        return VH_SAVE_UPDATE_NO_VALID_BASE;
    }

    if (!vh_save_slot_validate(current_slot == 0U ? slot_a_buffer : slot_b_buffer,
                               current_slot == 0U ? size_a : size_b,
                               expected_header_size, &current_generation,
                               &current_card, &current_card_size)) {
        return VH_SAVE_UPDATE_NO_VALID_BASE;
    }
    (void)current_card;
    (void)current_card_size;
    if (current_generation == UINT64_MAX) {
        return VH_SAVE_UPDATE_GENERATION_EXHAUSTED;
    }

    target_slot = 1U - current_slot;
    target_buffer = target_slot == 0U ? slot_a_buffer : slot_b_buffer;
    if (!vh_save_slot_encode(target_buffer, slot_capacity,
                             current_generation + 1U, card_image,
                             card_image_size, expected_header_size,
                             &encoded_size)) {
        return VH_SAVE_UPDATE_INVALID_ARGUMENT;
    }

    if (!ops->open_write(context, target_slot)) {
        return VH_SAVE_UPDATE_IO_FAILURE;
    }
    write_ok = ops->write_all(context, target_slot, target_buffer, encoded_size);
    if (write_ok) flush_ok = ops->flush(context, target_slot);
    close_ok = ops->close(context, target_slot);
    if (!write_ok || !flush_ok || !close_ok) {
        return VH_SAVE_UPDATE_IO_FAILURE;
    }

    if (ops->read_slot(context, target_slot, verify_buffer,
                       verify_capacity, &verify_size) != VH_SAVE_IO_OK ||
        verify_size > verify_capacity ||
        !vh_save_slot_validate(verify_buffer, verify_size,
                               expected_header_size, &verify_generation,
                               &verify_card, &verify_card_size) ||
        verify_generation != current_generation + 1U ||
        verify_card_size != card_image_size ||
        memcmp(verify_card, card_image, card_image_size) != 0) {
        return VH_SAVE_UPDATE_VERIFY_FAILURE;
    }

    if (selected_slot_out != NULL) *selected_slot_out = target_slot;
    if (generation_out != NULL) *generation_out = verify_generation;
    return VH_SAVE_UPDATE_OK;
}
