#ifndef VH_CARD_VALIDATE_H
#define VH_CARD_VALIDATE_H

#include <stddef.h>
#include <stdint.h>

/*
 * Validate an in-memory PS1 memory-card image using the layout observed in
 * the pinned PC port. Returns 1 for a valid header/listing and every occupied
 * save record; 0 for malformed or truncated data.
 *
 * On success, header_size_out may receive 384 (US layout) or 512 (JP layout).
 * This function performs no file I/O and does not modify the supplied image.
 */
int vh_card_validate_image(const uint8_t *image, size_t image_size,
                           size_t *header_size_out);

#endif
