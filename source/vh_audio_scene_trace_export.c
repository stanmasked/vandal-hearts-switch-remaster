#define _POSIX_C_SOURCE 200809L
#include "vh_audio_scene_trace_export.h"

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

/* Own only the post-join CSV export. No game-loop or audout I/O. */
static int disk_exists(void *context, const char *path) {
    (void)context;
    struct stat st;
    if (stat(path,&st)==0) return 1;
    return errno==ENOENT ? 0 : -1;
}

static FILE *disk_create_exclusive(void *context, const char *path) {
    (void)context;
    /* O_EXCL also refuses dangling temp symlinks; do not truncate a
     * previous failed capture or a path installed by another process. */
    const int fd=open(path,O_WRONLY|O_CREAT|O_EXCL,0600);
    if (fd<0) return NULL;
    FILE *file=fdopen(fd,"wb");
    if (!file) {
        (void)close(fd);
        (void)remove(path);
    }
    return file;
}
static FILE *disk_open_read(void *context, const char *path) {
    (void)context;
    return fopen(path,"rb");
}
static int disk_flush(void *context, FILE *stream) {
    (void)context;
    return fflush(stream);
}
static int disk_close(void *context, FILE *stream) {
    (void)context;
    return fclose(stream);
}
static int disk_rename(void *context, const char *from, const char *to) {
    (void)context;
    return rename(from,to);
}
static int disk_remove(void *context, const char *path) {
    (void)context;
    return remove(path);
}
static const VhSceneTraceExportOps disk_ops = {
    NULL,disk_exists,disk_create_exclusive,disk_open_read,
    disk_flush,disk_close,disk_rename,disk_remove
};

static int valid_ops(const VhSceneTraceExportOps *ops) {
    return ops && ops->exists && ops->create_exclusive &&
           ops->open_read && ops->flush && ops->close &&
           ops->rename && ops->remove;
}
static const char *event_name(unsigned kind) {
    switch (kind) {
    case VH_SCENE_TRACE_INPUT: return "INPUT";
    case VH_SCENE_TRACE_POST: return "POST";
    case VH_SCENE_TRACE_ACCEPT: return "ACCEPT";
    case VH_SCENE_TRACE_SUBMIT_CALL: return "SUBMIT_CALL";
    case VH_SCENE_TRACE_RELEASE_RETURN: return "RELEASE_RETURN";
    case VH_SCENE_TRACE_SUBMIT_ERROR: return "SUBMIT_ERROR";
    default: return NULL;
    }
}
static int path_for_slot(char *out, size_t capacity,
                         const char *directory, unsigned slot,
                         const char *suffix) {
    const size_t dir_len=strlen(directory);
    const int need_slash=dir_len && directory[dir_len-1]!='/' ? 1 : 0;
    const int written=snprintf(out,capacity,"%s%saudio-scene-trace-%04u.%s",
                               directory, need_slash ? "/" : "",slot,suffix);
    return written>0 && (size_t)written<capacity;
}

static unsigned trace_rows(const VhAudioSceneTrace *trace) {
    const unsigned total=atomic_load_explicit(
        &trace->reserved,memory_order_acquire);
    return total>VH_AUDIO_SCENE_TRACE_CAPACITY
        ? VH_AUDIO_SCENE_TRACE_CAPACITY : total;
}
static const char header[] =
    "index,event,serial,scene,monotonic_ns,dropped_total\n";

/* Return line length or -1 when the record is not yet published. */
static int row_line(const VhAudioSceneTrace *trace, unsigned index,
                    unsigned dropped, char *buffer, size_t size) {
    VhAudioSceneTraceSlot event;
    if(vh_audio_scene_trace_snapshot(trace,index,&event)!=1)
        return -1;
    const char *name=event_name(event.kind);
    if(!name || event.scene>2u) return -1;
    const int written=snprintf(buffer,size,"%u,%s,%u,%u,%" PRIu64 ",%u\n",
                               index,name,event.serial,event.scene,
                               event.monotonic_ns,dropped);
    if(written<=0 || (size_t)written>=size) return -1;
    return written;
}
static int write_csv(FILE *stream, const VhAudioSceneTrace *trace,
                     unsigned rows, unsigned dropped) {
    if(fwrite(header,1,sizeof(header)-1u,stream)!=sizeof(header)-1u)
        return -1;
    for(unsigned i=0;i<rows;i++) {
        char line[160];
        const int n=row_line(trace,i,dropped,line,sizeof line);
        if(n<0 || fwrite(line,1,(size_t)n,stream)!=(size_t)n) return -1;
    }
    return (int)rows;
}
static int readback_csv(FILE *stream, const VhAudioSceneTrace *trace,
                        unsigned rows, unsigned dropped) {
    char seen[160];
    if(fread(seen,1,sizeof(header)-1u,stream)!=sizeof(header)-1u ||
       memcmp(seen,header,sizeof(header)-1u)!=0) return -1;
    for(unsigned i=0;i<rows;i++) {
        char expected[160];
        const int n=row_line(trace,i,dropped,expected,sizeof expected);
        if(n<0 || fread(seen,1,(size_t)n,stream)!=(size_t)n ||
           memcmp(seen,expected,(size_t)n)!=0) return -1;
    }
    if(fgetc(stream)!=EOF || ferror(stream)) return -1;
    return (int)rows;
}

VhSceneExportResult vh_audio_scene_trace_export(
    const VhAudioSceneTrace *trace, const char *directory,
    const VhSceneTraceExportOps *optional_ops,
    char *committed_path, size_t committed_path_capacity) {
    if(committed_path && committed_path_capacity) committed_path[0]='\0';
    const VhSceneTraceExportOps *ops=optional_ops ? optional_ops : &disk_ops;
    if(!trace || !directory || !*directory || !committed_path ||
       !committed_path_capacity || !valid_ops(ops))
        return VH_SCENE_EXPORT_INVALID;
    const unsigned rows=trace_rows(trace);
    if(!rows) return VH_SCENE_EXPORT_INVALID;
    const unsigned dropped=vh_audio_scene_trace_dropped(trace);
    /* Snapshot every slot before creating files. No pending/partially
     * committed row may ever reach the SD staging area. */
    for(unsigned i=0;i<rows;i++) {
        VhAudioSceneTraceSlot event;
        if(vh_audio_scene_trace_snapshot(trace,i,&event)!=1 ||
           !event_name(event.kind) || event.scene>2u)
            return VH_SCENE_EXPORT_INVALID;
    }

    char dest[VH_SCENE_TRACE_EXPORT_PATH_CAP];
    char temp[VH_SCENE_TRACE_EXPORT_PATH_CAP];
    unsigned slot=0;
    for(;slot<VH_SCENE_TRACE_EXPORT_SLOTS;slot++) {
        if(!path_for_slot(dest,sizeof dest,directory,slot,"csv") ||
           !path_for_slot(temp,sizeof temp,directory,slot,"tmp"))
            return VH_SCENE_EXPORT_PATH;
        const int published=ops->exists(ops->context,dest);
        const int pending=ops->exists(ops->context,temp);
        if(published<0 || pending<0) return VH_SCENE_EXPORT_STAT;
        if(!published && !pending) break;
    }
    if(slot==VH_SCENE_TRACE_EXPORT_SLOTS)
        return VH_SCENE_EXPORT_SLOTS_FULL;
    if(strlen(dest)+1u>committed_path_capacity)
        return VH_SCENE_EXPORT_PATH;

    FILE *stream=ops->create_exclusive(ops->context,temp);
    if(!stream) return VH_SCENE_EXPORT_OPEN;
    VhSceneExportResult result=VH_SCENE_EXPORT_OK;
    if(write_csv(stream,trace,rows,dropped)!=(int)rows)
        result=VH_SCENE_EXPORT_WRITE;
    if(ops->flush(ops->context,stream)!=0 && result==VH_SCENE_EXPORT_OK)
        result=VH_SCENE_EXPORT_FLUSH;
    if(ops->close(ops->context,stream)!=0 && result==VH_SCENE_EXPORT_OK)
        result=VH_SCENE_EXPORT_CLOSE;
    if(result==VH_SCENE_EXPORT_OK) {
        FILE *verify=ops->open_read(ops->context,temp);
        if(!verify) result=VH_SCENE_EXPORT_READ;
        else {
            if(readback_csv(verify,trace,rows,dropped)!=(int)rows)
                result=VH_SCENE_EXPORT_VERIFY;
            if(ops->close(ops->context,verify)!=0 &&
               result==VH_SCENE_EXPORT_OK)
                result=VH_SCENE_EXPORT_CLOSE;
        }
    }
    if(result==VH_SCENE_EXPORT_OK) {
        /* FAT/newlib rename lacks an atomic no-replace primitive.
         * Recheck the destination, require exclusive directory ownership
         * and never intentionally overwrite an existing CSV. */
        const int still_absent=ops->exists(ops->context,dest);
        if(still_absent<0) result=VH_SCENE_EXPORT_STAT;
        else if(still_absent!=0) result=VH_SCENE_EXPORT_SLOTS_FULL;
        else if(ops->rename(ops->context,temp,dest)!=0)
            result=VH_SCENE_EXPORT_RENAME;
    }
    if(result!=VH_SCENE_EXPORT_OK) {
        (void)ops->remove(ops->context,temp);
        return result;
    }
    memcpy(committed_path,dest,strlen(dest)+1u);
    return VH_SCENE_EXPORT_OK;
}
