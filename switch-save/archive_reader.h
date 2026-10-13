#ifndef VH_ARCHIVE_READER_H
#define VH_ARCHIVE_READER_H

#include <stddef.h>
#include <stdint.h>

#include "archive_restore.h"

/*
 * The backend resolves only the supplied validated basename beneath its
 * trusted archive directory. read_all must fail on I/O errors or when the
 * file does not fit in capacity, and set image_size to the bytes read.
 * close_archive consumes the handle and reports close/I/O errors.
 */
typedef struct {
    void *(*open_archive)(void *context, const char *validated_basename);
    int (*read_all)(void *context, void *handle, uint8_t *buffer,
                    size_t capacity, size_t *image_size);
    int (*close_archive)(void *context, void *handle);
} vh_archive_read_ops;

/*
 * Validate the basename before opening anything, read into caller-owned
 * bounded memory, and require both read and close to succeed before invoking
 * the existing card validator/atomic-write sequence. The reader callback must
 * not accept arbitrary paths; it receives only the validated basename.
 */
int vh_restore_archive_file(const vh_atomic_write_ops *write_ops,
                            const vh_archive_read_ops *read_ops,
                            void *context, const char *destination,
                            const char *archive_name,
                            const char *active_card_prefix,
                            uint8_t *image_buffer, size_t image_capacity,
                            size_t expected_header_size);

#endif
