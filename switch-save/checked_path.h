#ifndef VH_CHECKED_PATH_H
#define VH_CHECKED_PATH_H

#include <stddef.h>

/*
 * Join a trusted application data root and one untrusted path component.
 * Returns 1 on success and 0 on invalid input or insufficient output capacity.
 * The root is supplied by the caller; this helper does not create directories.
 */
int vh_checked_path_join(char *out, size_t out_size,
                         const char *root, const char *leaf);

#endif
