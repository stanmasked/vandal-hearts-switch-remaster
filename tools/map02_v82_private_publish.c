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
    if(fsync(fd)<0) goto fail;
    if(close(fd)<0) { fd=-1;goto fail; }
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
    if(read(reader,readback,1)!=0) goto fail;
    if(close(reader)<0) { reader=-1;goto fail; }
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

/* A failed/restarted observation may only publish to a fresh pathname.
 * Prior export must exist as a sole-owned 0600 regular file, and must
 * retain its original identity and metadata across this function. This
 * is NOT an atomic guard against arbitrary concurrent external writers.
 * The v82 publisher still enforces O_EXCL temp and no-clobber hard link.
 */
int vh98_publish_recovery(const char *previous_path,const char *next_path,
                          const char *bytes,size_t size) {
    struct stat before, after, named;
    int prev=-1, status=-1;
    if(!previous_path || !next_path || !bytes || !size ||
       previous_path[0]!='/' || next_path[0]!='/' ||
       strcmp(previous_path,next_path)==0 ||
       strstr(previous_path,"/../") || strstr(next_path,"/../") ||
       strstr(previous_path,"/./") || strstr(next_path,"/./"))
        return -1;
    if(strnlen(previous_path,VH82_MAX_PATH)>=VH82_MAX_PATH ||
       strnlen(next_path,VH82_MAX_PATH)>=VH82_MAX_PATH)
        return -1;
    prev=open(previous_path,O_RDONLY|O_NOFOLLOW);
    if(prev<0)return -1;
    if(fstat(prev,&before)<0 || !S_ISREG(before.st_mode) ||
       (before.st_mode&0777)!=0600 || before.st_nlink!=1)
        goto done;
    /* Recovered target is never allowed to replace the previous file. */
    if(vh82_publish_private(next_path,bytes,size)!=0)goto done;
    if(fstat(prev,&after)<0 || lstat(previous_path,&named)<0 ||
       before.st_dev!=after.st_dev || before.st_ino!=after.st_ino ||
       before.st_size!=after.st_size ||
       before.st_dev!=named.st_dev || before.st_ino!=named.st_ino ||
       before.st_size!=named.st_size ||
       (named.st_mode&0777)!=0600 || !S_ISREG(named.st_mode))
        goto done;
    status=0;
done:
    close(prev);
    return status;
}

/* Interrupted v82 publication leaves <final>.tmp, not <final>.
 * Distinguish a crash before the exclusive hard link from one after it.
 * Never use partial staged bytes as completed, and never unlink a stage
 * of unknown ownership. All calls assume an exclusively controlled
 * private directory; metadata checks cannot stop outside TOCTOU writers.
 */
static int vh99_private_path_ok(const char *path) {
    if(!path || path[0]!='/')return 0;
    size_t n=strnlen(path,VH82_MAX_PATH);
    if(n==0 || n+5>=VH82_MAX_PATH ||
       strstr(path,"/../") || strstr(path,"/./") ||
       (n>=3 && strcmp(path+n-3,"/..")==0) ||
       (n>=2 && strcmp(path+n-2,"/.")==0))
        return 0;
    return 1;
}
static int vh99_lstat_expected(const char *path,struct stat *s){
    if(lstat(path,s)==0){
        if(!S_ISREG(s->st_mode) || (s->st_mode&0777)!=0600 ||
           s->st_nlink!=1)return -1;
        return 1;
    }
    return errno==ENOENT?0:-1;
}
int vh99_private_state(const char *final_path){
    char tmp[VH82_MAX_PATH];
    struct stat final_stat,tmp_stat;
    if(!vh99_private_path_ok(final_path))return -1;
    size_t n=strlen(final_path);
    memcpy(tmp,final_path,n);
    memcpy(tmp+n,".tmp",5);
    int f=vh99_lstat_expected(final_path,&final_stat);
    int t=vh99_lstat_expected(tmp,&tmp_stat);
    if(f<0 || t<0)return -1;
    return f+(t*2);
}
int vh99_publish_after_interruption(const char *abandoned_final,
                                   const char *fresh_final,
                                   const char *bytes,size_t size){
    char abandoned_tmp[VH82_MAX_PATH];
    struct stat before,after;
    if(!vh99_private_path_ok(abandoned_final) ||
       !vh99_private_path_ok(fresh_final) || !bytes ||
       !size || size>VH82_MAX_BYTES ||
       strcmp(abandoned_final,fresh_final)==0)
        return -1;
    /* The submitted stage must be incomplete and the target truly unused.
     * Refuse any pre-existing completed file, bad mode, or symlink. */
    if(vh99_private_state(abandoned_final)!=2 ||
       vh99_private_state(fresh_final)!=0)return -1;
    size_t n=strlen(abandoned_final);
    memcpy(abandoned_tmp,abandoned_final,n);
    memcpy(abandoned_tmp+n,".tmp",5);
    if(lstat(abandoned_tmp,&before)!=0 || !S_ISREG(before.st_mode) ||
       (before.st_mode&0777)!=0600 || before.st_nlink!=1)return -1;
    if(vh82_publish_private(fresh_final,bytes,size)!=0)return -1;
    /* Confirm abandoned staged bytes still belong to the same inode.
     * A malicious external concurrent writer is outside this guarantee. */
    if(lstat(abandoned_tmp,&after)!=0 ||
       before.st_dev!=after.st_dev || before.st_ino!=after.st_ino ||
       before.st_size!=after.st_size || before.st_nlink!=after.st_nlink ||
       before.st_mode!=after.st_mode ||
       vh99_private_state(abandoned_final)!=2 ||
       vh99_private_state(fresh_final)!=1)return -1;
    return 0;
}
