#ifndef VH_ATOMIC_WRITE_H
#define VH_ATOMIC_WRITE_H

#include <stddef.h>

typedef struct {
    /* Creates a unique temporary file on the same filesystem as destination. */
    void *(*open_temporary)(void *context, const char *destination,
                            char *temporary_path, size_t path_capacity);
    /* Must write the complete span or return 0. */
    int (*write_all)(void *context, void *handle,
                     const void *data, size_t size);
    int (*flush)(void *context, void *handle);
    /* Consumes/closes handle; returns 1 only if close completed successfully. */
    int (*close)(void *context, void *handle);
    /*
     * Replaces destination only on success. The backend must document whether
     * replacement is atomic and what durability it guarantees.
     */
    int (*replace)(void *context, const char *temporary_path,
                   const char *destination);
    void (*remove_temporary)(void *context, const char *temporary_path);
} vh_atomic_write_ops;

/*
 * Write bytes to a temporary file, flush and close it, then replace destination.
 * Returns 1 only if every stage succeeds. Any failure after temporary creation
 * attempts to close the handle (if still open) and remove the temporary file.
 * This orchestrator does not implement a filesystem and is not yet wired into
 * the game; platform callbacks supply all actual I/O behavior.
 */
int vh_atomic_write(const vh_atomic_write_ops *ops, void *context,
                    const char *destination, const void *data, size_t size);

#endif
