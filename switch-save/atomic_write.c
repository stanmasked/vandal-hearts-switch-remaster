#include "atomic_write.h"

#include <string.h>

enum { VH_TEMP_PATH_CAPACITY = 1024 };

int vh_atomic_write(const vh_atomic_write_ops *ops, void *context,
                    const char *destination, const void *data, size_t size)
{
    char temporary[VH_TEMP_PATH_CAPACITY];
    void *handle;
    int write_ok;
    int flush_ok;
    int close_ok;
    int replace_ok;

    if (ops == NULL || destination == NULL || destination[0] == '\0' ||
        (data == NULL && size != 0U) ||
        ops->open_temporary == NULL || ops->write_all == NULL ||
        ops->flush == NULL || ops->close == NULL ||
        ops->replace == NULL || ops->remove_temporary == NULL) {
        return 0;
    }

    temporary[0] = '\0';
    handle = ops->open_temporary(context, destination, temporary,
                                 sizeof(temporary));
    if (handle == NULL) {
        return 0;
    }

    /* A backend must provide a usable temporary path when it returns a handle. */
    if (temporary[0] == '\0' ||
        memchr(temporary, '\0', sizeof(temporary)) == NULL) {
        (void)ops->close(context, handle);
        return 0;
    }

    write_ok = ops->write_all(context, handle, data, size);
    flush_ok = write_ok ? ops->flush(context, handle) : 0;
    close_ok = ops->close(context, handle);

    if (!write_ok || !flush_ok || !close_ok) {
        ops->remove_temporary(context, temporary);
        return 0;
    }

    replace_ok = ops->replace(context, temporary, destination);
    if (!replace_ok) {
        ops->remove_temporary(context, temporary);
        return 0;
    }

    return 1;
}
