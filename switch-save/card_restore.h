#ifndef VH_CARD_RESTORE_H
#define VH_CARD_RESTORE_H

#include <stddef.h>
#include <stdint.h>

#include "atomic_write.h"

/*
 * Validate a card image and its expected region layout before starting any
 * filesystem write. expected_header_size must be 384 (US) or 512 (JP).
 * Returns 1 only if validation and the atomic-write orchestration succeed.
 */
int vh_restore_card(const vh_atomic_write_ops *ops, void *context,
                    const char *destination, const uint8_t *image,
                    size_t image_size, size_t expected_header_size);

#endif
