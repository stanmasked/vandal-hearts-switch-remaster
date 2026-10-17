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
/* Classify native private journal state WITHOUT opening a .tmp for replay.
 * -1 unsafe or unexpected IO; 0 entirely fresh; 1 committed-only;
 * 2 abandoned stage only; 3 committed with residual stage.
 * This does not modify either pathname. */
int vh99_private_state(const char *final_path);
/* After an interrupted, uncommitted stage, publish only to a DIFFERENT
 * empty final pathname. Never re-use, unlink or publish the staged file. */
int vh99_publish_after_interruption(const char *abandoned_final,
                                   const char *fresh_final,
                                   const char *bytes,size_t size);
#endif
