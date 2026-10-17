#ifndef VH82_PRIVATE_PUBLISH_H
#define VH82_PRIVATE_PUBLISH_H
#include <stddef.h>
/* POSIX-only private, exclusive, readback-verified publication.
 * No replacement of an existing final file, never public upload. */
int vh82_publish_private(const char *path,const char *bytes,size_t size);
#endif
