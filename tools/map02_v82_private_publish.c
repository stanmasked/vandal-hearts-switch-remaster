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
#ifndef O_DIRECTORY
#error "v100 directory durability needs O_DIRECTORY"
#endif
#define VH82_MAX_PATH 4096u
#define VH82_MAX_BYTES 524288u

/* Directory-fsync evidence is an aggregate counter, never private bytes. */
static unsigned int vh100_synced_directories;
unsigned int vh100_directory_syncs(void){return vh100_synced_directories;}
#ifdef VH100_FAULT_TEST
/* Isolated native tests only; never compiled into pinned production PCSX. */
static int vh100_test_fault;
void vh100_test_fail_at(int phase){vh100_test_fault=phase;}
#define VH100_FAIL(phase) (vh100_test_fault==(phase))
#else
#define VH100_FAIL(phase) (0)
#endif

int vh82_publish_private(const char *path,const char *bytes,size_t size) {
    char tmp[VH82_MAX_PATH],parent[VH82_MAX_PATH];
    char readback[4096];
    size_t at=0;
    int fd=-1,reader=-1,dirfd=-1,owned=0,linked=0,ok=-1;
    if(!path || !bytes || path[0]!='/' || !size || size>VH82_MAX_BYTES) return -1;
    size_t n=strnlen(path,VH82_MAX_PATH);
    if(n==0 || n+5>=sizeof(tmp) || strstr(path,"/../") || strstr(path,"/./"))return -1;
    const char *slash=strrchr(path,'/');
    if(!slash || !slash[1])return -1;
    size_t parent_len=(size_t)(slash-path);
    if(parent_len==0){parent[0]='/';parent[1]='\0';}
    else {memcpy(parent,path,parent_len);parent[parent_len]='\0';}
    dirfd=open(parent,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
    if(dirfd<0)return -1;
    struct stat directory;
    if(fstat(dirfd,&directory)<0 || !S_ISDIR(directory.st_mode))
        goto finish;
    memcpy(tmp,path,n);
    memcpy(tmp+n,".tmp",5);
    fd=open(tmp,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);
    if(fd<0)goto finish;
    owned=1;
    while(at<size) {
        ssize_t wrote=write(fd,bytes+at,size-at);
        if(wrote<=0)goto finish;
        at+=(size_t)wrote;
    }
    if(fsync(fd)<0)goto finish;
    if(close(fd)<0){fd=-1;goto finish;}
    fd=-1;
    reader=open(tmp,O_RDONLY|O_NOFOLLOW);
    if(reader<0)goto finish;
    at=0;
    while(at<size) {
        size_t want=size-at<sizeof(readback)?size-at:sizeof(readback);
        ssize_t got=read(reader,readback,want);
        if(got<=0 || memcmp(bytes+at,readback,(size_t)got)!=0)goto finish;
        at+=(size_t)got;
    }
    if(read(reader,readback,1)!=0)goto finish;
    if(close(reader)<0){reader=-1;goto finish;}
    reader=-1;
    /* Original no-replace hard link. Final can exist after a later failure;
     * we intentionally NEVER roll it back or reuse its pathname. */
    if(link(tmp,path)<0)goto finish;
    linked=1;
    /* fsync the PARENT DIRECTORY to persist the newly created final name,
     * not just the content of the already-fsynced stage file. */
    if(VH100_FAIL(1) || fsync(dirfd)<0)goto finish;
    vh100_synced_directories++;
    if(VH100_FAIL(2))goto finish;
    /* Remove ONLY our owned temporary stage and persist that unlink. */
    if(unlink(tmp)<0)goto finish;
    owned=0;
    if(VH100_FAIL(3) || fsync(dirfd)<0)goto finish;
    vh100_synced_directories++;
    /* The completed name is never trusted solely because link/fsync
     * succeeded: re-open BOTH file and parent, compare ALL bytes and
     * independently sync the committed file and directory again. */
    if(vh101_verify_private_commit(path,bytes,size)!=0)goto finish;
    ok=0;
finish:
    if(fd>=0)close(fd);
    if(reader>=0)close(reader);
    /* On pre-link failure, the old v82 rule cleans up our own temp.
     * On any post-link error, retain a possibly committed final file.
     * Never hide its ambiguous state or overwrite on a retry. */
    if(owned && !linked){
        if(unlink(tmp)==0)(void)fsync(dirfd);
    }
    if(dirfd>=0 && close(dirfd)<0)ok=-1;
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


/* Verified commit counts contain no private payload or path details. */
static unsigned int vh101_commits;
static unsigned int vh101_parent_syncs;
unsigned int vh101_verified_commits(void){return vh101_commits;}
unsigned int vh101_reopened_directory_syncs(void){return vh101_parent_syncs;}
#ifdef VH100_FAULT_TEST
static int vh101_test_fault;
void vh101_test_fail_at(int phase){vh101_test_fault=phase;}
#define VH101_FAIL(phase) (vh101_test_fault==(phase))
#else
#define VH101_FAIL(phase) (0)
#endif

/* Read-only revalidation of a completed private journal. The reopening
 * matters: do NOT assume that a successful write/fsync of a temporary
 * file proves the final name points at the same bytes on its own.
 * Both data and parent directory must successfully fsync AGAIN.
 * No rename, replace or implicit cleanup is attempted on failure.
 */
int vh101_verify_private_commit(const char *path,const char *bytes,size_t size){
    char parent[VH82_MAX_PATH],scratch[4096];
    struct stat initial,again,named,dir_stat;
    int fd=-1,dirfd=-1,ok=-1;
    if(!path || !bytes || !size || size>VH82_MAX_BYTES ||
       path[0]!='/')return -1;
    size_t n=strnlen(path,VH82_MAX_PATH);
    if(n==0 || n+5>=VH82_MAX_PATH ||
       strstr(path,"/../") || strstr(path,"/./"))return -1;
    const char *slash=strrchr(path,'/');
    if(!slash || !slash[1])return -1;
    size_t parent_length=(size_t)(slash-path);
    if(parent_length==0){parent[0]='/';parent[1]='\0';}
    else{memcpy(parent,path,parent_length);parent[parent_length]='\0';}
    dirfd=open(parent,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
    if(dirfd<0)goto finish;
    if(VH101_FAIL(1) || fstat(dirfd,&dir_stat)<0 ||
       !S_ISDIR(dir_stat.st_mode))goto finish;
    /* A final file with a leftover .tmp (or linked-to-stage inode)
     * remains ambiguous: a re-open must not certify it as complete. */
    if(vh99_private_state(path)!=1)goto finish;
    fd=open(path,O_RDONLY|O_NOFOLLOW);
    if(fd<0)goto finish;
    if(fstat(fd,&initial)<0 || !S_ISREG(initial.st_mode) ||
       (initial.st_mode&0777)!=0600 || initial.st_nlink!=1 ||
       initial.st_size<0 || (size_t)initial.st_size!=size)goto finish;
    size_t pos=0;
    while(pos<size){
        size_t want=size-pos<sizeof(scratch)?size-pos:sizeof(scratch);
        ssize_t got=read(fd,scratch,want);
        if(got<=0 || memcmp(bytes+pos,scratch,(size_t)got)!=0)
            goto finish;
        pos+=(size_t)got;
    }
    if(read(fd,scratch,1)!=0)goto finish;
    if(VH101_FAIL(2) || fsync(fd)<0)goto finish;
    if(VH101_FAIL(3) || fsync(dirfd)<0)goto finish;
    vh101_parent_syncs++;
    if(fstat(fd,&again)<0 || lstat(path,&named)<0 ||
       named.st_dev!=initial.st_dev || named.st_ino!=initial.st_ino ||
       again.st_dev!=initial.st_dev || again.st_ino!=initial.st_ino ||
       again.st_size!=initial.st_size ||
       named.st_size!=initial.st_size || named.st_nlink!=1 ||
       !S_ISREG(named.st_mode) || (named.st_mode&0777)!=0600)
        goto finish;
    ok=0;
finish:
    if(fd>=0 && close(fd)<0)ok=-1;
    if(dirfd>=0 && close(dirfd)<0)ok=-1;
    if(ok==0)vh101_commits++;
    return ok;
}
