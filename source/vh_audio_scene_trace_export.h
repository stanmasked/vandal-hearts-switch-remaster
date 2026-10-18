#ifndef VH_AUDIO_SCENE_TRACE_EXPORT_H
#define VH_AUDIO_SCENE_TRACE_EXPORT_H

#include <stddef.h>
#include <stdio.h>
#include "vh_audio_scene_trace.h"

/* Export AFTER the audio producer joins, never from frame/audout callbacks.
 * A complete table has a per-row overflow count in an additional column.
 * Never open an existing numbered CSV or .tmp for writing. */
#define VH_SCENE_TRACE_EXPORT_SLOTS 64u
#define VH_SCENE_TRACE_EXPORT_PATH_CAP 512u
#define VH_SCENE_TRACE_SD_DIRECTORY "sdmc:/switch/vandal-hearts-remake"

typedef enum {
    VH_SCENE_EXPORT_OK=0,
    VH_SCENE_EXPORT_INVALID=-1,
    VH_SCENE_EXPORT_PATH=-2,
    VH_SCENE_EXPORT_SLOTS_FULL=-3,
    VH_SCENE_EXPORT_OPEN=-4,
    VH_SCENE_EXPORT_WRITE=-5,
    VH_SCENE_EXPORT_FLUSH=-6,
    VH_SCENE_EXPORT_CLOSE=-7,
    VH_SCENE_EXPORT_READ=-8,
    VH_SCENE_EXPORT_VERIFY=-9,
    VH_SCENE_EXPORT_STAT=-10,
    VH_SCENE_EXPORT_RENAME=-11
} VhSceneExportResult;

typedef struct {
    void *context;
    /* exists: 1 present, 0 absent, -1 stat failure. */
    int (*exists)(void *, const char *);
    /* MUST exclusively create a new temp; never truncate an existing path. */
    FILE *(*create_exclusive)(void *, const char *);
    FILE *(*open_read)(void *, const char *);
    int (*flush)(void *, FILE *);
    int (*close)(void *, FILE *);
    int (*rename)(void *, const char *, const char *);
    int (*remove)(void *, const char *);
} VhSceneTraceExportOps;

/* Valid canonical CSV:
 *   index,event,serial,scene,monotonic_ns,dropped_total
 *   0,INPUT,1,2,123456789,0
 * ...
 * All rows contain the same post-join dropped count. A full 64-row
 * trace with dropped>0 is INCOMPLETE evidence; it must not be reported
 * as a complete internal timeline.
 *
 * Each write is read back byte-for-byte (including exact EOF) before
 * publishing via rename. Existing names are checked twice; on FAT
 * rename cannot guarantee atomic no-replace against a concurrent
 * writer, so the caller must own the directory exclusively.
 * No SD power-loss durability is claimed.
 */
VhSceneExportResult vh_audio_scene_trace_export(
    const VhAudioSceneTrace *trace, const char *directory,
    const VhSceneTraceExportOps *optional_ops,
    char *committed_path, size_t committed_path_capacity);

#endif
