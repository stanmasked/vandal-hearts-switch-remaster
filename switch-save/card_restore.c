#include "card_restore.h"

#include "card_validate.h"

int vh_restore_card(const vh_atomic_write_ops *ops, void *context,
                    const char *destination, const uint8_t *image,
                    size_t image_size, size_t expected_header_size)
{
    size_t actual_header_size = 0U;

    if (expected_header_size != 384U && expected_header_size != 512U) {
        return 0;
    }

    if (!vh_card_validate_image(image, image_size, &actual_header_size) ||
        actual_header_size != expected_header_size) {
        return 0;
    }

    return vh_atomic_write(ops, context, destination, image, image_size);
}
