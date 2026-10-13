#include "checked_path.h"

#include <stdint.h>
#include <string.h>

/* Reject overlap and address-range overflow before any output mutation. */
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

static int valid_leaf(const char *leaf)
{
    const unsigned char *p;

    if (leaf == NULL || leaf[0] == '\0' ||
        (leaf[0] == '.' && leaf[1] == '\0') ||
        (leaf[0] == '.' && leaf[1] == '.' && leaf[2] == '\0')) {
        return 0;
    }

    for (p = (const unsigned char *)leaf; *p != '\0'; ++p) {
        if (*p == '/' || *p == '\\' || *p < 0x20 || *p == 0x7f) {
            return 0;
        }
    }
    return 1;
}

int vh_checked_path_join(char *out, size_t out_size,
                         const char *root, const char *leaf)
{
    size_t root_len;
    size_t leaf_len;
    size_t separator;
    size_t needed;

    if (out == NULL || out_size == 0 || root == NULL ||
        root[0] == '\0' || !valid_leaf(leaf)) {
        return 0;
    }

    root_len = strlen(root);
    leaf_len = strlen(leaf);
    separator = root[root_len - 1] == '/' ? 0U : 1U;

    /* Check each addition before computing required capacity. */
    if (root_len > (size_t)-1 - separator ||
        root_len + separator > (size_t)-1 - leaf_len ||
        root_len + separator + leaf_len > (size_t)-1 - 1U) {
        return 0;
    }
    needed = root_len + separator + leaf_len + 1U;
    if (needed > out_size ||
        ranges_overlap(out, needed, root, root_len + 1U) ||
        ranges_overlap(out, needed, leaf, leaf_len + 1U)) {
        return 0;
    }

    memcpy(out, root, root_len);
    if (separator != 0U) {
        out[root_len] = '/';
    }
    memcpy(out + root_len + separator, leaf, leaf_len + 1U);
    return 1;
}
