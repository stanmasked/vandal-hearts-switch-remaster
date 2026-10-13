#ifndef VH_SAVE_SLOT_H
#define VH_SAVE_SLOT_H

#include <stddef.h>
#include <stdint.h>

enum {
    VH_SAVE_SLOT_HEADER_SIZE = 24
};

typedef enum {
    VH_SAVE_SLOT_INVALID = 0,
    VH_SAVE_SLOT_VALID = 1,
    VH_SAVE_SLOT_AMBIGUOUS = -1
} vh_save_slot_selection;

/*
 * Encode a version-1 container around a validated PS1 card image.
 * The payload must match expected_header_size (384 or 512) and pass the
 * existing in-memory card validator. Source and encoded destination ranges must
 * not overlap. container_size_out, when non-NULL, must not overlap either
 * input or output buffer. On failure, out and container_size_out are left
 * unchanged.
 * Returns 1 on success.
 */
int vh_save_slot_encode(uint8_t *out, size_t out_capacity,
                        uint64_t generation, const uint8_t *card_image,
                        size_t card_image_size, size_t expected_header_size,
                        size_t *container_size_out);

/*
 * Validate one complete container. On success, optional outputs receive its
 * generation and a borrowed pointer/size for the embedded card image. If
 * validation fails, all output arguments are left unchanged. Non-NULL output
 * objects must be mutually disjoint and must not overlap the container bytes.
 */
int vh_save_slot_validate(const uint8_t *container, size_t container_size,
                          size_t expected_header_size,
                          uint64_t *generation_out,
                          const uint8_t **card_image_out,
                          size_t *card_image_size_out);

/*
 * Select between two complete containers. Returns slot index 0 or 1,
 * VH_SAVE_SLOT_INVALID if neither is valid, or VH_SAVE_SLOT_AMBIGUOUS when
 * valid containers have the same generation but different card payloads.
 * selected_slot_out is written only when a slot is successfully selected; if
 * non-NULL, it must not overlap either input container.
 */
vh_save_slot_selection vh_save_slot_select(
    const uint8_t *slot_a, size_t slot_a_size,
    const uint8_t *slot_b, size_t slot_b_size,
    size_t expected_header_size, unsigned int *selected_slot_out);

#endif
