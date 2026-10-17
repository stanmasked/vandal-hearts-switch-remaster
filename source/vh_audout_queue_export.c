#define _POSIX_C_SOURCE 200809L
#include "vh_audout_queue_export.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int exists(const char *p) {
    struct stat st;
    if(stat(p,&st)==0) return 1;
    return errno==ENOENT ? 0 : -1;
}
static int make_path(char *out,size_t cap,const char *dir,
                     unsigned slot,const char *ext,const char *stem) {
    const size_t n=strlen(dir);
    const int slash=dir[n-1]=='/' ? 0 : 1;
    const int k=snprintf(out,cap,"%s%saudio-audout-%s-%04u.%s",
                         dir,slash?"/":"",stem,slot,ext);
    return k>0 && (size_t)k<cap;
}
typedef int (*VhWriter)(const VhAudoutQueueTelemetry *,FILE *);
static VhAudoutQueueExportResult export_csv(
    const VhAudoutQueueTelemetry *t,const char *directory,
    char *committed_path,size_t capacity,const char *stem,
    VhWriter writer,VhWriter verify) {
    if(committed_path && capacity) committed_path[0]='\0';
    if(!t || !directory || !*directory || !committed_path || !capacity)
        return VH_AUDOUT_QUEUE_EXPORT_INVALID;
    char dest[VH_AUDOUT_QUEUE_EXPORT_PATH_CAP];
    char temp[VH_AUDOUT_QUEUE_EXPORT_PATH_CAP];
    unsigned slot=0;
    for(;slot<VH_AUDOUT_QUEUE_EXPORT_SLOTS;slot++) {
        if(!make_path(dest,sizeof dest,directory,slot,"csv",stem) ||
           !make_path(temp,sizeof temp,directory,slot,"tmp",stem))
            return VH_AUDOUT_QUEUE_EXPORT_PATH;
        const int old=exists(dest),pending=exists(temp);
        if(old<0 || pending<0) return VH_AUDOUT_QUEUE_EXPORT_IO;
        if(!old && !pending) break;
    }
    if(slot==VH_AUDOUT_QUEUE_EXPORT_SLOTS)
        return VH_AUDOUT_QUEUE_EXPORT_FULL;
    const size_t length=strlen(dest)+1u;
    if(length>capacity) return VH_AUDOUT_QUEUE_EXPORT_PATH;
    /* O_EXCL rejects symlinks and protects previously staged captures. */
    const int fd=open(temp,O_WRONLY|O_CREAT|O_EXCL,0600);
    if(fd<0) return VH_AUDOUT_QUEUE_EXPORT_OPEN;
    FILE *f=fdopen(fd,"wb");
    if(!f) {
        (void)close(fd);
        (void)remove(temp);
        return VH_AUDOUT_QUEUE_EXPORT_OPEN;
    }
    VhAudoutQueueExportResult status=VH_AUDOUT_QUEUE_EXPORT_OK;
    if(writer(t,f)<0 || fflush(f)!=0)
        status=VH_AUDOUT_QUEUE_EXPORT_IO;
    if(fclose(f)!=0) status=VH_AUDOUT_QUEUE_EXPORT_IO;
    if(status==VH_AUDOUT_QUEUE_EXPORT_OK) {
        FILE *readback=fopen(temp,"rb");
        if(!readback) status=VH_AUDOUT_QUEUE_EXPORT_VERIFY;
        else {
            if(verify(t,readback)!=0)
                status=VH_AUDOUT_QUEUE_EXPORT_VERIFY;
            if(fclose(readback)!=0)
                status=VH_AUDOUT_QUEUE_EXPORT_VERIFY;
        }
    }
    if(status==VH_AUDOUT_QUEUE_EXPORT_OK) {
        const int published=exists(dest);
        if(published<0) status=VH_AUDOUT_QUEUE_EXPORT_IO;
        else if(published) status=VH_AUDOUT_QUEUE_EXPORT_FULL;
        else if(rename(temp,dest)!=0)
            status=VH_AUDOUT_QUEUE_EXPORT_RENAME;
    }
    if(status!=VH_AUDOUT_QUEUE_EXPORT_OK) {
        (void)remove(temp);
        return status;
    }
    memcpy(committed_path,dest,length);
    return VH_AUDOUT_QUEUE_EXPORT_OK;
}

VhAudoutQueueExportResult vh_audout_queue_export(
    const VhAudoutQueueTelemetry *t,const char *directory,
    char *committed_path,size_t capacity) {
    return export_csv(t,directory,committed_path,capacity,
        "queue",vh_audout_queue_write_csv,vh_audout_queue_verify_csv);
}
VhAudoutQueueExportResult vh_audout_latency_export(
    const VhAudoutQueueTelemetry *t,const char *directory,
    char *committed_path,size_t capacity) {
    return export_csv(t,directory,committed_path,capacity,
        "latency",vh_audout_latency_write_csv,vh_audout_latency_verify_csv);
}

VhAudoutQueueExportResult vh_audout_clock_export(
    const VhAudoutQueueTelemetry *t,const char *directory,
    char *committed_path,size_t capacity) {
    return export_csv(t,directory,committed_path,capacity,
        "clock",vh_audout_clock_write_csv,vh_audout_clock_verify_csv);
}

VhAudoutQueueExportResult vh_audout_slow_export(
    const VhAudoutQueueTelemetry *t,const char *directory,
    char *committed_path,size_t capacity) {
    return export_csv(t,directory,committed_path,capacity,
        "slow",vh_audout_slow_write_csv,vh_audout_slow_verify_csv);
}
