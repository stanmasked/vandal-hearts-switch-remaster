#include "archive_restore.h"

#include "archive_name.h"
#include "card_restore.h"

int vh_restore_archive(const vh_atomic_write_ops *ops, void *context,
                       const char *destination, const char *archive_name,
                       const char *active_card_prefix,
                       const uint8_t *archive_image, size_t image_size,
                       size_t expected_header_size)
{
    if (!vh_archive_name_valid(archive_name, active_card_prefix)) {
        return 0;
    }

    return vh_restore_card(ops, context, destination, archive_image,
                           image_size, expected_header_size);
}
