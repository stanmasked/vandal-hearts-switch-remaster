#ifndef VH_AUDOUT_QUEUE_EXPORT_H
#define VH_AUDOUT_QUEUE_EXPORT_H
#include <stddef.h>
#include "vh_audout_queue_telemetry.h"

/* Independent numbered evidence on guest SD, separate from the scene
 * optical/SD trace and from opt-in hardware diagnostic journal. */
#define VH_AUDOUT_QUEUE_EXPORT_PATH_CAP 256u
#define VH_AUDOUT_QUEUE_EXPORT_SLOTS 100u
typedef enum {
    VH_AUDOUT_QUEUE_EXPORT_OK=0,
    VH_AUDOUT_QUEUE_EXPORT_INVALID=-1,
    VH_AUDOUT_QUEUE_EXPORT_PATH=-2,
    VH_AUDOUT_QUEUE_EXPORT_FULL=-3,
    VH_AUDOUT_QUEUE_EXPORT_OPEN=-4,
    VH_AUDOUT_QUEUE_EXPORT_IO=-5,
    VH_AUDOUT_QUEUE_EXPORT_VERIFY=-6,
    VH_AUDOUT_QUEUE_EXPORT_RENAME=-7
} VhAudoutQueueExportResult;

/* Only after worker join. Exclusive temp -> write/close -> exact
 * readback -> no-replace precheck -> rename. Checks visible bytes,
 * not SD persistence across console power loss. */
VhAudoutQueueExportResult vh_audout_queue_export(
    const VhAudoutQueueTelemetry *t,const char *directory,
    char *committed_path,size_t capacity);
/* Separate numbered latency-only CSV, never overwrites the queue CSV. */
VhAudoutQueueExportResult vh_audout_slow_export(
    const VhAudoutQueueTelemetry *t,const char *directory,
    char *committed_path,size_t capacity);
VhAudoutQueueExportResult vh_audout_clock_export(
    const VhAudoutQueueTelemetry *t,const char *directory,
    char *committed_path,size_t capacity);
VhAudoutQueueExportResult vh_audout_latency_export(
    const VhAudoutQueueTelemetry *t,const char *directory,
    char *committed_path,size_t capacity);
#endif
