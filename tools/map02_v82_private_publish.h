#ifndef VH82_PRIVATE_PUBLISH_H
#define VH82_PRIVATE_PUBLISH_H
#include <stddef.h>
/* POSIX-only private, exclusive, readback-verified publication.
 * No replacement of an existing final file, never public upload. */
int vh82_publish_private(const char *path,const char *bytes,size_t size);
/* An existing private file must be immutable. Only a DISTINCT unused path
 * may receive a recovered observer lifetime; never rename/replace old. */
int vh98_publish_recovery(const char *previous_path,const char *next_path,
                          const char *bytes,size_t size);
#endif
