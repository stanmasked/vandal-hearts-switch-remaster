#include "checked_path.h"

#include <string.h>

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
    if (needed > out_size) {
        return 0;
    }

    memcpy(out, root, root_len);
    if (separator != 0U) {
        out[root_len] = '/';
    }
    memcpy(out + root_len + separator, leaf, leaf_len + 1U);
    return 1;
}
