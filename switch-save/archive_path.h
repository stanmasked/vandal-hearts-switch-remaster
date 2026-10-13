#ifndef VH_ARCHIVE_PATH_H
#define VH_ARCHIVE_PATH_H

#include <stddef.h>

/*
 * Construct root/basename only after validating the archive name against the
 * trusted active-card prefix. root must be selected by trusted backend code.
 * This is path construction, not mount or symlink validation.
 */
int vh_archive_path_join(char *out, size_t out_size, const char *root,
                         const char *archive_name,
                         const char *active_card_prefix);

#endif
