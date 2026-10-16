#include "vh_audio_diag_export.h"

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

static int disk_exists(void *unused, const char *path) {
    struct stat statbuf;
    (void)unused;
    if(stat(path,&statbuf)==0) return 1;
    return errno==ENOENT ? 0 : -1;
}
static FILE *disk_open(void *unused, const char *path) {
    (void)unused;
    return fopen(path,"wb");
}
static FILE *disk_open_read(void *unused,const char *path) {
    (void)unused;
    return fopen(path,"rb");
}
static int disk_write(void *unused,const VhAudioDiagJournal *j,FILE *f) {
    (void)unused;
    return vh_audio_diag_journal_write_csv(j,f);
}
static int disk_flush(void *unused,FILE *f) {
    (void)unused;
    return fflush(f);
}
static int disk_close(void *unused,FILE *f) {
    (void)unused;
    return fclose(f);
}
static int disk_rename(void *unused,const char *from,const char *to) {
    (void)unused;
    return rename(from,to);
}
static int disk_remove(void *unused,const char *path) {
    (void)unused;
    return remove(path);
}
static const VhAudioDiagExportOps disk_ops={
    NULL,disk_exists,disk_open,disk_open_read,disk_write,disk_flush,disk_close,
    disk_rename,disk_remove
};
static int ready(const VhAudioDiagExportOps *o) {
    return o && o->exists && o->open && o->open_read &&
           o->write && o->flush &&
           o->close && o->rename && o->remove;
}
static int build_path(char *target,size_t capacity,const char *dir,
                      const char *name) {
    const size_t len=strlen(dir);
    const int slash=len && dir[len-1]=='/' ? 0 : 1;
    const int n=snprintf(target,capacity,"%s%s%s",dir,
                         slash ? "/" : "",name);
    return n>0 && (size_t)n<capacity;
}

VhAudioDiagExportResult vh_audio_diag_export(
    const VhAudioDiagJournal *j,const char *directory,
    const VhAudioDiagExportOps *optional,
    char *dest,size_t dest_capacity) {
    if(dest && dest_capacity) dest[0]='\0';
    const VhAudioDiagExportOps *ops=optional ? optional : &disk_ops;
    if(!j || !directory || !directory[0] || !dest || !dest_capacity ||
       !ready(ops) || !j->count ||
       j->count>VH_AUDIO_DIAG_JOURNAL_CAPACITY ||
       j->head>=VH_AUDIO_DIAG_JOURNAL_CAPACITY)
        return VH_AUDIO_EXPORT_INVALID;
    char target[VH_AUDIO_DIAG_EXPORT_PATH_CAP];
    char temp[VH_AUDIO_DIAG_EXPORT_PATH_CAP];
    char name[48];
    if(!build_path(temp,sizeof temp,directory,"audio-diagnostics.tmp"))
        return VH_AUDIO_EXPORT_PATH;

    unsigned slot;
    for(slot=0;slot<VH_AUDIO_DIAG_EXPORT_SLOTS;slot++) {
        (void)snprintf(name,sizeof name,"audio-diagnostics-%04u.csv",slot);
        if(!build_path(target,sizeof target,directory,name))
            return VH_AUDIO_EXPORT_PATH;
        const int present=ops->exists(ops->context,target);
        if(present<0) return VH_AUDIO_EXPORT_STAT;
        if(present==0) break;
    }
    if(slot==VH_AUDIO_DIAG_EXPORT_SLOTS)
        return VH_AUDIO_EXPORT_SLOTS_FULL;
    if(strlen(target)+1u>dest_capacity)
        return VH_AUDIO_EXPORT_PATH;

    /* Even if a stale .tmp remains after power loss, replacing it
     * cannot damage any previously COMMITTED numbered CSV file. */
    FILE *f=ops->open(ops->context,temp);
    if(!f) return VH_AUDIO_EXPORT_OPEN;
    VhAudioDiagExportResult result=VH_AUDIO_EXPORT_OK;
    if(ops->write(ops->context,j,f)!=(int)j->count)
        result=VH_AUDIO_EXPORT_WRITE;
    if(ops->flush(ops->context,f)!=0 && result==VH_AUDIO_EXPORT_OK)
        result=VH_AUDIO_EXPORT_FLUSH;
    if(ops->close(ops->context,f)!=0 && result==VH_AUDIO_EXPORT_OK)
        result=VH_AUDIO_EXPORT_CLOSE;
    if(result==VH_AUDIO_EXPORT_OK) {
        /* READ-BACK CHECK: a successful write/flush/close can still
         * produce truncated or corrupted data on a faulty SD card.
         * Reopen in rb mode and require a byte-for-byte canonical CSV
         * match including an exact EOF. Never publish a damaged .tmp.
         */
        FILE *readback=ops->open_read(ops->context,temp);
        if(!readback) result=VH_AUDIO_EXPORT_READ;
        else {
            if(vh_audio_diag_journal_verify_csv(j,readback)!=(int)j->count)
                result=VH_AUDIO_EXPORT_VERIFY;
            if(ops->close(ops->context,readback)!=0 &&
               result==VH_AUDIO_EXPORT_OK)
                result=VH_AUDIO_EXPORT_CLOSE;
        }
    }
    if(result==VH_AUDIO_EXPORT_OK) {
        /* A second absence check prevents accidental overwrite if
         * another process created the target during export. This
         * is best-effort on FAT, not an atomic compare-and-swap. */
        const int still_free=ops->exists(ops->context,target);
        if(still_free<0) result=VH_AUDIO_EXPORT_STAT;
        else if(still_free!=0) result=VH_AUDIO_EXPORT_SLOTS_FULL;
        else if(ops->rename(ops->context,temp,target)!=0)
            result=VH_AUDIO_EXPORT_RENAME;
    }
    if(result!=VH_AUDIO_EXPORT_OK) {
        (void)ops->remove(ops->context,temp);
        return result;
    }
    memcpy(dest,target,strlen(target)+1u);
    return VH_AUDIO_EXPORT_OK;
}
