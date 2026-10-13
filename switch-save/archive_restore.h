#ifndef VH_ARCHIVE_RESTORE_H
#define VH_ARCHIVE_RESTORE_H

#include <stddef.h>
#include <stdint.h>

#include "atomic_write.h"

/*
 * Validate an archive basename, card image, and expected region before
 * starting any destination write. archive_image must already have been read
 * by the caller from the file identified by archive_name.
 *
 * active_card_prefix is trusted region-specific configuration.
 * expected_header_size must be 384 (US) or 512 (JP).
 */
int vh_restore_archive(const vh_atomic_write_ops *ops, void *context,
                       const char *destination, const char *archive_name,
                       const char *active_card_prefix,
                       const uint8_t *archive_image, size_t image_size,
                       size_t expected_header_size);

#endif
