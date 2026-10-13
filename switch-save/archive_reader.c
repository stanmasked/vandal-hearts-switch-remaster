#include "archive_reader.h"

#include "archive_name.h"

int vh_restore_archive_file(const vh_atomic_write_ops *write_ops,
                            const vh_archive_read_ops *read_ops,
                            void *context, const char *destination,
                            const char *archive_name,
                            const char *active_card_prefix,
                            uint8_t *image_buffer, size_t image_capacity,
                            size_t expected_header_size)
{
    void *handle;
    size_t image_size = 0;
    int read_ok;
    int close_ok;

    if (!vh_archive_name_valid(archive_name, active_card_prefix) ||
        read_ops == 0 || read_ops->open_archive == 0 ||
        read_ops->read_all == 0 || read_ops->close_archive == 0 ||
        image_buffer == 0 || image_capacity == 0) {
        return 0;
    }

    handle = read_ops->open_archive(context, archive_name);
    if (handle == 0) {
        return 0;
    }

    read_ok = read_ops->read_all(context, handle, image_buffer,
                                 image_capacity, &image_size);
    close_ok = read_ops->close_archive(context, handle);

    if (!read_ok || !close_ok || image_size == 0 ||
        image_size > image_capacity) {
        return 0;
    }

    return vh_restore_archive(write_ops, context, destination, archive_name,
                              active_card_prefix, image_buffer, image_size,
                              expected_header_size);
}
