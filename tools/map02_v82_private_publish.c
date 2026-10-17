#define _POSIX_C_SOURCE 200809L
#include "vh82_private_publish.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#ifndef O_NOFOLLOW
#error "v82 POSIX private publisher requires O_NOFOLLOW"
#endif
#define VH82_MAX_PATH 4096u
#define VH82_MAX_BYTES 524288u

int vh82_publish_private(const char *path,const char *bytes,size_t size) {
    char tmp[VH82_MAX_PATH];
    char readback[4096];
    size_t at=0;
    int fd=-1,reader=-1,owned=0,ok=-1;
    if(!path || !bytes || path[0]!='/' || !size || size>VH82_MAX_BYTES) return -1;
    size_t n=strnlen(path,VH82_MAX_PATH);
    if(n==0 || n+5>=sizeof(tmp) || strstr(path,"/../") || strstr(path,"/./")) return -1;
    memcpy(tmp,path,n);
    memcpy(tmp+n,".tmp",5);
    fd=open(tmp,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);
    if(fd<0) return -1;
    owned=1;
    while(at<size) {
        ssize_t wrote=write(fd,bytes+at,size-at);
        if(wrote<=0) goto fail;
        at+=(size_t)wrote;
    }
    if(fsync(fd)<0 || close(fd)<0) { fd=-1;goto fail; }
    fd=-1;
    reader=open(tmp,O_RDONLY|O_NOFOLLOW);
    if(reader<0) goto fail;
    at=0;
    while(at<size) {
        size_t want=size-at<sizeof(readback)?size-at:sizeof(readback);
        ssize_t got=read(reader,readback,want);
        if(got<=0 || memcmp(bytes+at,readback,(size_t)got)!=0) goto fail;
        at+=(size_t)got;
    }
    if(read(reader,readback,1)!=0 || close(reader)<0) { reader=-1;goto fail; }
    reader=-1;
    /* Hard link is exclusive: unlike rename(), it cannot replace final. */
    if(link(tmp,path)<0) goto fail;
    ok=0;
fail:
    if(fd>=0) close(fd);
    if(reader>=0) close(reader);
    if(owned) unlink(tmp);
    return ok;
}
