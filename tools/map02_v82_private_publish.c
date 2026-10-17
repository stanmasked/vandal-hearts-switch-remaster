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


/* Every mutating operation uses an already verified directory descriptor.
 * Reopening the name is an identity check, never the authority for writes.
 * Does not promise immunity to arbitrary concurrent directory replacements
 * between checks; test-only races must fail closed whenever observed. */

/* Start at / and open EACH intermediate component using dirfd. A symlink
 * in /private/owner/.. is refused rather than only checking the leaf. */
static unsigned int vh103_parent_walks;
unsigned int vh103_safe_parent_walks(void){return vh103_parent_walks;}
static int vh103_open_parent_safely(const char *absolute){
    if(!absolute || absolute[0]!='/')return -1;
    size_t n=strnlen(absolute,VH82_MAX_PATH);
    if(n==0 || n>=VH82_MAX_PATH)return -1;
    int fd=open("/",O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
    if(fd<0)return -1;
    size_t offset=1;
    while(offset<n){
        if(absolute[offset]=='/'){close(fd);return -1;}
        size_t end=offset;
        while(end<n && absolute[end]!='/')end++;
        size_t size=end-offset;
        if(size==0 || size>255 ||
           (size==1 && absolute[offset]=='.') ||
           (size==2 && absolute[offset]=='.' &&
            absolute[offset+1]=='.')){close(fd);return -1;}
        char part[256];
        memcpy(part,absolute+offset,size);
        part[size]='\0';
        int next=openat(fd,part,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
        if(next<0){close(fd);return -1;}
        if(close(fd)<0){close(next);return -1;}
        fd=next;
        offset=end+1;
        if(end==n-1){close(fd);return -1;}
    }
    vh103_parent_walks++;
    return fd;
}
#ifdef VH100_FAULT_TEST
static char vh103_swap_final[VH82_MAX_PATH];
static char vh103_swap_replacement[VH82_MAX_PATH];
static char vh103_swap_backup[VH82_MAX_PATH];
static int vh103_swap_phase;
int vh103_test_replace_final(const char *original,const char *replacement,
                             const char *backup,int phase){
    if(!original || !replacement || !backup || phase<1 || phase>2 ||
       strlen(original)>=sizeof(vh103_swap_final) ||
       strlen(replacement)>=sizeof(vh103_swap_replacement) ||
       strlen(backup)>=sizeof(vh103_swap_backup))return -1;
    strcpy(vh103_swap_final,original);
    strcpy(vh103_swap_replacement,replacement);
    strcpy(vh103_swap_backup,backup);
    vh103_swap_phase=phase;
    return 0;
}
static int vh103_maybe_swap_final(int phase){
    if(vh103_swap_phase!=phase)return 0;
    vh103_swap_phase=0;
    if(rename(vh103_swap_final,vh103_swap_backup)<0)return -1;
    if(rename(vh103_swap_replacement,vh103_swap_final)<0)return -1;
    return 0;
}
#else
#define vh103_maybe_swap_final(phase) (0)
#endif

static unsigned int vh102_dir_checks, vh102_publishes;
unsigned int vh102_parent_identity_checks(void){return vh102_dir_checks;}
unsigned int vh102_anchored_publishes(void){return vh102_publishes;}
static int vh102_parent_matches(int fd,const char *name){
    struct stat anchored, current;
    int reopened=vh103_open_parent_safely(name);
    if(reopened<0)return -1;
    int ok=(fstat(fd,&anchored)==0 && fstat(reopened,&current)==0 &&
            S_ISDIR(anchored.st_mode) && S_ISDIR(current.st_mode) &&
            anchored.st_dev==current.st_dev &&
            anchored.st_ino==current.st_ino);
    if(close(reopened)<0)ok=0;
    if(ok)vh102_dir_checks++;
    return ok?0:-1;
}
#ifdef VH100_FAULT_TEST
static char vh102_swap_parent[VH82_MAX_PATH];
static char vh102_swap_moved[VH82_MAX_PATH];
static char vh102_swap_target[VH82_MAX_PATH];
static int vh102_swap_phase;
int vh102_test_parent_redirect(const char *parent,const char *moved,
                               const char *target,int phase){
    if(!parent || !moved || !target || phase<1 || phase>3 ||
       strlen(parent)>=sizeof(vh102_swap_parent) ||
       strlen(moved)>=sizeof(vh102_swap_moved) ||
       strlen(target)>=sizeof(vh102_swap_target))return -1;
    strcpy(vh102_swap_parent,parent);
    strcpy(vh102_swap_moved,moved);
    strcpy(vh102_swap_target,target);
    vh102_swap_phase=phase;
    return 0;
}
static int vh102_maybe_swap(int phase){
    if(vh102_swap_phase!=phase)return 0;
    vh102_swap_phase=0;
    if(rename(vh102_swap_parent,vh102_swap_moved)!=0)return -1;
    if(symlink(vh102_swap_target,vh102_swap_parent)!=0)return -1;
    return 0;
}
#else
#define vh102_maybe_swap(phase) (0)
#endif

/* v107: original stage inode must survive every named read/link boundary.
 * Fault hooks belong ONLY to isolated native tests. */
static int vh105_same_metadata(const struct stat *a,const struct stat *b);
#ifdef VH100_FAULT_TEST
static char vh107_stage_path[VH82_MAX_PATH];
static char vh107_stage_replacement[VH82_MAX_PATH];
static char vh107_stage_backup[VH82_MAX_PATH];
static int vh107_stage_phase;
int vh107_test_replace_stage(const char *stage,const char *replacement,
                             const char *backup,int phase){
    if(!stage || !replacement || !backup || phase<1 || phase>3 ||
       strnlen(stage,VH82_MAX_PATH)>=VH82_MAX_PATH ||
       strnlen(replacement,VH82_MAX_PATH)>=VH82_MAX_PATH ||
       strnlen(backup,VH82_MAX_PATH)>=VH82_MAX_PATH)return -1;
    strcpy(vh107_stage_path,stage);
    strcpy(vh107_stage_replacement,replacement);
    strcpy(vh107_stage_backup,backup);
    vh107_stage_phase=phase;
    return 0;
}
static int vh107_maybe_replace_stage(int phase){
    if(vh107_stage_phase!=phase)return 0;
    vh107_stage_phase=0;
    if(rename(vh107_stage_path,vh107_stage_backup)!=0)return -1;
    if(rename(vh107_stage_replacement,vh107_stage_path)!=0)return -1;
    return 0;
}
#else
#define vh107_maybe_replace_stage(phase) (0)
#endif

int vh82_publish_private(const char *path,const char *bytes,size_t size) {
    char parent[VH82_MAX_PATH];
    char readback[4096];
    size_t at=0;
    int fd=-1,reader=-1,dirfd=-1,owned=0,linked=0,ok=-1;
    int staged_identity_known=0;
    struct stat stage_created,stage_written,stage_named,stage_reader,stage_final;
    if(!path || !bytes || path[0]!='/' || !size || size>VH82_MAX_BYTES) return -1;
    size_t n=strnlen(path,VH82_MAX_PATH);
    if(n==0 || n+5>=VH82_MAX_PATH || strstr(path,"/../") || strstr(path,"/./"))return -1;
    const char *slash=strrchr(path,'/');
    if(!slash || !slash[1])return -1;
    size_t parent_len=(size_t)(slash-path);
    if(parent_len==0){parent[0]='/';parent[1]='\0';}
    else {memcpy(parent,path,parent_len);parent[parent_len]='\0';}
    dirfd=vh103_open_parent_safely(parent);
    if(dirfd<0)return -1;
    struct stat directory;
    if(fstat(dirfd,&directory)<0 || !S_ISDIR(directory.st_mode))
        goto finish;
    const char *base=slash+1;
    char stage[VH82_MAX_PATH];
    size_t base_len=strlen(base);
    if(base_len+5>=sizeof(stage) || vh102_parent_matches(dirfd,parent)!=0)
        goto finish;
    memcpy(stage,base,base_len);
    memcpy(stage+base_len,".tmp",5);
    fd=openat(dirfd,stage,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);
    if(fd<0)goto finish;
    owned=1;
    if(fstat(fd,&stage_created)<0 || !S_ISREG(stage_created.st_mode) ||
       (stage_created.st_mode&0777)!=0600 || stage_created.st_nlink!=1)
        goto finish;
    staged_identity_known=1;
    while(at<size) {
        ssize_t wrote=write(fd,bytes+at,size-at);
        if(wrote<=0)goto finish;
        at+=(size_t)wrote;
    }
    if(fsync(fd)<0 ||
       fstat(fd,&stage_written)<0 ||
       stage_written.st_dev!=stage_created.st_dev ||
       stage_written.st_ino!=stage_created.st_ino ||
       stage_written.st_size<0 || (size_t)stage_written.st_size!=size ||
       stage_written.st_nlink!=1 ||
       !S_ISREG(stage_written.st_mode) ||
       (stage_written.st_mode&0777)!=0600)goto finish;
    if(close(fd)<0){fd=-1;goto finish;}
    fd=-1;
    if(vh107_maybe_replace_stage(1)<0)goto finish;
    reader=openat(dirfd,stage,O_RDONLY|O_NOFOLLOW);
    if(reader<0 ||
       fstat(reader,&stage_reader)<0 ||
       fstatat(dirfd,stage,&stage_named,AT_SYMLINK_NOFOLLOW)<0 ||
       !vh105_same_metadata(&stage_written,&stage_reader) ||
       !vh105_same_metadata(&stage_written,&stage_named))
        goto finish;
    at=0;
    while(at<size) {
        size_t want=size-at<sizeof(readback)?size-at:sizeof(readback);
        ssize_t got=read(reader,readback,want);
        if(got<=0 || memcmp(bytes+at,readback,(size_t)got)!=0)goto finish;
        at+=(size_t)got;
    }
    if(read(reader,readback,1)!=0 ||
       fstat(reader,&stage_reader)<0 ||
       fstatat(dirfd,stage,&stage_named,AT_SYMLINK_NOFOLLOW)<0 ||
       !vh105_same_metadata(&stage_written,&stage_reader) ||
       !vh105_same_metadata(&stage_written,&stage_named))goto finish;
    if(close(reader)<0){reader=-1;goto finish;}
    reader=-1;
    if(vh107_maybe_replace_stage(2)<0 ||
       fstatat(dirfd,stage,&stage_named,AT_SYMLINK_NOFOLLOW)<0 ||
       !vh105_same_metadata(&stage_written,&stage_named))goto finish;
    /* Original no-replace hard link. Final can exist after a later failure;
     * we intentionally NEVER roll it back or reuse its pathname. */
    if(vh102_maybe_swap(1)!=0 ||
       vh102_parent_matches(dirfd,parent)!=0 ||
       vh107_maybe_replace_stage(3)<0 ||
       linkat(dirfd,stage,dirfd,base,0)<0)goto finish;
    linked=1;
    /* linkat is no-clobber but can race a malicious stage-name replacement.
     * Never certify a final name linked to a different inode. */
    if(fstatat(dirfd,base,&stage_final,AT_SYMLINK_NOFOLLOW)<0 ||
       !S_ISREG(stage_final.st_mode) ||
       stage_final.st_dev!=stage_created.st_dev ||
       stage_final.st_ino!=stage_created.st_ino ||
       stage_final.st_size!=stage_written.st_size ||
       (stage_final.st_mode&0777)!=0600)goto finish;
    if(vh102_maybe_swap(2)!=0 ||
       vh102_parent_matches(dirfd,parent)!=0)goto finish;
    /* fsync the PARENT DIRECTORY to persist the newly created final name,
     * not just the content of the already-fsynced stage file. */
    if(VH100_FAIL(1) || fsync(dirfd)<0)goto finish;
    vh100_synced_directories++;
    if(VH100_FAIL(2))goto finish;
    /* Remove ONLY our owned temporary stage and persist that unlink. */
    if(unlinkat(dirfd,stage,0)<0)goto finish;
    owned=0;
    if(vh102_maybe_swap(3)!=0 ||
       vh102_parent_matches(dirfd,parent)!=0 ||
       VH100_FAIL(3) || fsync(dirfd)<0)goto finish;
    vh100_synced_directories++;
    /* The completed name is never trusted solely because link/fsync
     * succeeded: re-open BOTH file and parent, compare ALL bytes and
     * independently sync the committed file and directory again. */
    if(vh102_parent_matches(dirfd,parent)!=0 ||
       vh101_verify_private_commit(path,bytes,size)!=0)goto finish;
    ok=0;
finish:
    if(fd>=0)close(fd);
    if(reader>=0)close(reader);
    /* On pre-link failure, the old v82 rule cleans up our own temp.
     * On any post-link error, retain a possibly committed final file.
     * Never hide its ambiguous state or overwrite on a retry. */
    if(owned && !linked && staged_identity_known){
        /* On refusal, NEVER delete an inode planted at our former .tmp name.
         * This check does not make unlinkat atomic against hostile writers
         * swapping the path after fstatat; exclusive directory assumed. */
        if(fstatat(dirfd,stage,&stage_named,AT_SYMLINK_NOFOLLOW)==0 &&
           S_ISREG(stage_named.st_mode) && stage_named.st_nlink==1 &&
           (stage_named.st_mode&0777)==0600 &&
           stage_named.st_dev==stage_created.st_dev &&
           stage_named.st_ino==stage_created.st_ino){
            if(unlinkat(dirfd,stage,0)==0)(void)fsync(dirfd);
        }
    }
    if(dirfd>=0 && close(dirfd)<0)ok=-1;
    if(ok==0)vh102_publishes++;
    return ok;
}

/* v105: recovery must not bless an old same-inode object after an in-place
 * rewrite, even when its size, owner and hard-link count remain unchanged.
 * Metadata is a detectable-change guard, not a cryptographic snapshot of
 * arbitrarily racing/unprivileged writers or coarse timestamp filesystems. */
static int vh105_same_metadata(const struct stat *a,const struct stat *b){
    return a->st_dev==b->st_dev && a->st_ino==b->st_ino &&
           a->st_size==b->st_size && a->st_mode==b->st_mode &&
           a->st_nlink==b->st_nlink &&
           a->st_mtim.tv_sec==b->st_mtim.tv_sec &&
           a->st_mtim.tv_nsec==b->st_mtim.tv_nsec &&
           a->st_ctim.tv_sec==b->st_ctim.tv_sec &&
           a->st_ctim.tv_nsec==b->st_ctim.tv_nsec;
}
#ifdef VH100_FAULT_TEST
/* Isolated native fault injection; not linked into pinned production PCSX.
 * 1 = mutate the previous committed file during v98 recovery,
 * 2 = mutate the abandoned .tmp during v99 recovery. */
static int vh105_change_phase;
void vh105_test_change_during_recovery(int phase){vh105_change_phase=phase;}
static int vh105_maybe_change(int phase,const char *name,
                             const struct stat *original){
    if(vh105_change_phase!=phase)return 0;
    vh105_change_phase=0;
    int writer=open(name,O_RDWR|O_NOFOLLOW);
    if(writer<0)return -1;
    struct stat actual;
    unsigned char byte=0;
    int ok=0;
    if(fstat(writer,&actual)<0 || !S_ISREG(actual.st_mode) ||
       actual.st_dev!=original->st_dev || actual.st_ino!=original->st_ino ||
       actual.st_size<=0 || pread(writer,&byte,1,0)!=1)
        ok=-1;
    if(ok==0){
        byte^=0x5au;
        if(pwrite(writer,&byte,1,0)!=1 || fsync(writer)<0)ok=-1;
    }
    if(close(writer)<0)ok=-1;
    return ok;
}
#else
#define vh105_maybe_change(phase,name,original) (0)
#endif

/* v106: source paths in v98/v99 get the SAME rooted no-symlink
 * component walk as newly published paths. Always operate through the
 * anchored directory fd; reopening a pathname only verifies identity.
 * This is not an atomic defense against a hostile concurrent writer. */
static int vh106_open_source_parent(const char *path,char *parent,
                                    const char **leaf){
    if(!path || path[0]!='/')return -1;
    size_t n=strnlen(path,VH82_MAX_PATH);
    if(!n || n+5>=VH82_MAX_PATH)return -1;
    const char *slash=strrchr(path,'/');
    if(!slash || !slash[1] ||
       strcmp(slash+1,".")==0 || strcmp(slash+1,"..")==0)
        return -1;
    size_t length=(size_t)(slash-path);
    if(length==0){parent[0]='/';parent[1]='\0';}
    else {memcpy(parent,path,length);parent[length]='\0';}
    int dirfd=vh103_open_parent_safely(parent);
    if(dirfd<0)return -1;
    if(vh102_parent_matches(dirfd,parent)!=0){
        close(dirfd);return -1;
    }
    *leaf=slash+1;
    return dirfd;
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
    char old_parent[VH82_MAX_PATH];
    const char *old_leaf=NULL;
    int prev=-1,old_dirfd=-1,status=-1;
    if(!previous_path || !next_path || !bytes || !size ||
       previous_path[0]!='/' || next_path[0]!='/' ||
       strcmp(previous_path,next_path)==0 ||
       strstr(previous_path,"/../") || strstr(next_path,"/../") ||
       strstr(previous_path,"/./") || strstr(next_path,"/./"))
        return -1;
    if(strnlen(previous_path,VH82_MAX_PATH)>=VH82_MAX_PATH ||
       strnlen(next_path,VH82_MAX_PATH)>=VH82_MAX_PATH)
        return -1;
    old_dirfd=vh106_open_source_parent(previous_path,old_parent,&old_leaf);
    if(old_dirfd<0)return -1;
    prev=openat(old_dirfd,old_leaf,O_RDONLY|O_NOFOLLOW);
    if(prev<0)goto done;
    if(fstat(prev,&before)<0 ||
       fstatat(old_dirfd,old_leaf,&named,AT_SYMLINK_NOFOLLOW)<0 ||
       !S_ISREG(before.st_mode) || (before.st_mode&0777)!=0600 ||
       before.st_nlink!=1 || !vh105_same_metadata(&before,&named) ||
       vh102_parent_matches(old_dirfd,old_parent)!=0)
        goto done;
    /* Recovered target is never allowed to replace the previous file. */
    if(vh82_publish_private(next_path,bytes,size)!=0)goto done;
    /* The newly linked name can exist after refusal. Preserve both names. */
    if(vh105_maybe_change(1,previous_path,&before)<0 ||
       vh102_parent_matches(old_dirfd,old_parent)!=0 ||
       fstat(prev,&after)<0 ||
       fstatat(old_dirfd,old_leaf,&named,AT_SYMLINK_NOFOLLOW)<0 ||
       !vh105_same_metadata(&before,&after) ||
       !vh105_same_metadata(&before,&named) ||
       (named.st_mode&0777)!=0600 || !S_ISREG(named.st_mode))
        goto done;
    status=0;
done:
    if(prev>=0 && close(prev)<0)status=-1;
    if(old_dirfd>=0 && close(old_dirfd)<0)status=-1;
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
static int vh99_lstat_expected_at(int dirfd,const char *leaf,
                                 struct stat *s){
    if(fstatat(dirfd,leaf,s,AT_SYMLINK_NOFOLLOW)==0){
        if(!S_ISREG(s->st_mode) || (s->st_mode&0777)!=0600 ||
           s->st_nlink!=1)return -1;
        return 1;
    }
    return errno==ENOENT?0:-1;
}
int vh99_private_state(const char *final_path){
    char parent[VH82_MAX_PATH],stage[VH82_MAX_PATH];
    const char *leaf=NULL;
    struct stat final_stat,tmp_stat;
    if(!vh99_private_path_ok(final_path))return -1;
    int dirfd=vh106_open_source_parent(final_path,parent,&leaf);
    if(dirfd<0)return -1;
    size_t n=strlen(leaf);
    memcpy(stage,leaf,n);
    memcpy(stage+n,".tmp",5);
    int f=vh99_lstat_expected_at(dirfd,leaf,&final_stat);
    int t=vh99_lstat_expected_at(dirfd,stage,&tmp_stat);
    int status=(f<0 || t<0 ||
                vh102_parent_matches(dirfd,parent)!=0)?-1:f+(t*2);
    if(close(dirfd)<0)status=-1;
    return status;
}
int vh99_publish_after_interruption(const char *abandoned_final,
                                   const char *fresh_final,
                                   const char *bytes,size_t size){
    char abandoned_tmp[VH82_MAX_PATH],old_parent[VH82_MAX_PATH];
    char stage[VH82_MAX_PATH];
    const char *leaf=NULL;
    struct stat before,after;
    int old_dirfd=-1,status=-1;
    if(!vh99_private_path_ok(abandoned_final) ||
       !vh99_private_path_ok(fresh_final) || !bytes ||
       !size || size>VH82_MAX_BYTES ||
       strcmp(abandoned_final,fresh_final)==0)
        return -1;
    /* The submitted stage must be incomplete and the target truly unused. */
    if(vh99_private_state(abandoned_final)!=2 ||
       vh99_private_state(fresh_final)!=0)return -1;
    old_dirfd=vh106_open_source_parent(abandoned_final,old_parent,&leaf);
    if(old_dirfd<0)return -1;
    size_t n=strlen(abandoned_final),leaf_n=strlen(leaf);
    memcpy(abandoned_tmp,abandoned_final,n);
    memcpy(abandoned_tmp+n,".tmp",5);
    memcpy(stage,leaf,leaf_n);
    memcpy(stage+leaf_n,".tmp",5);
    if(fstatat(old_dirfd,stage,&before,AT_SYMLINK_NOFOLLOW)!=0 ||
       !S_ISREG(before.st_mode) ||
       (before.st_mode&0777)!=0600 || before.st_nlink!=1 ||
       vh102_parent_matches(old_dirfd,old_parent)!=0)goto done;
    if(vh82_publish_private(fresh_final,bytes,size)!=0)goto done;
    /* Preserve stage identity and timestamps through original dirfd;
     * the already published fresh name is NEVER rolled back on failure. */
    if(vh105_maybe_change(2,abandoned_tmp,&before)<0 ||
       vh102_parent_matches(old_dirfd,old_parent)!=0 ||
       fstatat(old_dirfd,stage,&after,AT_SYMLINK_NOFOLLOW)!=0 ||
       !vh105_same_metadata(&before,&after) ||
       vh99_private_state(abandoned_final)!=2 ||
       vh99_private_state(fresh_final)!=1)goto done;
    status=0;
done:
    if(close(old_dirfd)<0)status=-1;
    return status;
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


/* Full post-sync re-read detects content changed after the first read;
 * ctime/mtime additionally detect many changed-and-restored attempts.
 * No userspace protocol can prove immunity to malicious writers racing
 * AFTER the last observation. The directory is exclusively owned. */
static unsigned int vh104_second_reads;
unsigned int vh104_second_pass_reads(void){return vh104_second_reads;}
#ifdef VH100_FAULT_TEST
static char vh104_fault_path[VH82_MAX_PATH];
static int vh104_fault_phase;
int vh104_test_mutate_bytes(const char *path,int phase){
    if(!path || phase<1 || phase>3 ||
       strnlen(path,sizeof(vh104_fault_path))>=sizeof(vh104_fault_path))
        return -1;
    strcpy(vh104_fault_path,path);
    vh104_fault_phase=phase;
    return 0;
}
static int vh104_maybe_mutate(int phase,int verified_fd){
    if(vh104_fault_phase!=phase)return 0;
    vh104_fault_phase=0;
    int writable=open(vh104_fault_path,O_WRONLY|O_NOFOLLOW);
    if(writable<0)return -1;
    struct stat v,w;
    int ok=0;
    unsigned char first;
    if(fstat(verified_fd,&v)<0 || fstat(writable,&w)<0 ||
       v.st_dev!=w.st_dev || v.st_ino!=w.st_ino ||
       v.st_size<=0 || pread(verified_fd,&first,1,0)!=1)ok=-1;
    if(ok==0){
        first^=0x5au;
        if(pwrite(writable,&first,1,0)!=1 || fsync(writable)<0)ok=-1;
    }
    if(close(writable)<0)ok=-1;
    return ok;
}
#else
#define vh104_maybe_mutate(phase,verified_fd) (0)
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
    if(vh102_parent_matches(dirfd,parent)!=0)goto finish;
    const char *base=slash+1;
    char stage[VH82_MAX_PATH];
    size_t base_len=strlen(base);
    if(base_len+5>=sizeof(stage))goto finish;
    memcpy(stage,base,base_len);
    memcpy(stage+base_len,".tmp",5);
    struct stat stage_stat;
    if(fstatat(dirfd,stage,&stage_stat,AT_SYMLINK_NOFOLLOW)==0 ||
       errno!=ENOENT)goto finish;
    if(fstatat(dirfd,base,&named,AT_SYMLINK_NOFOLLOW)<0 ||
       !S_ISREG(named.st_mode) || (named.st_mode&0777)!=0600 ||
       named.st_nlink!=1)goto finish;
    struct stat original_named=named;
    if(vh103_maybe_swap_final(1)<0)goto finish;
    fd=openat(dirfd,base,O_RDONLY|O_NOFOLLOW);
    if(fd<0)goto finish;
    if(fstat(fd,&initial)<0 || !S_ISREG(initial.st_mode) ||
       (initial.st_mode&0777)!=0600 || initial.st_nlink!=1 ||
       initial.st_size<0 || (size_t)initial.st_size!=size ||
       initial.st_dev!=original_named.st_dev ||
       initial.st_ino!=original_named.st_ino)goto finish;
    size_t pos=0;
    while(pos<size){
        size_t want=size-pos<sizeof(scratch)?size-pos:sizeof(scratch);
        ssize_t got=read(fd,scratch,want);
        if(got<=0 || memcmp(bytes+pos,scratch,(size_t)got)!=0)
            goto finish;
        pos+=(size_t)got;
    }
    if(read(fd,scratch,1)!=0)goto finish;
    if(vh103_maybe_swap_final(2)<0 ||
       vh104_maybe_mutate(1,fd)<0)goto finish;
    if(VH101_FAIL(2) || fsync(fd)<0)goto finish;
    if(vh104_maybe_mutate(2,fd)<0 ||
       vh102_parent_matches(dirfd,parent)!=0 ||
       VH101_FAIL(3) || fsync(dirfd)<0)goto finish;
    vh101_parent_syncs++;
    if(vh104_maybe_mutate(3,fd)<0 ||
       vh102_parent_matches(dirfd,parent)!=0)goto finish;
    /* A second COMPLETE byte-by-byte read after file and directory fsync
     * binds success to the bytes observed AFTER durability operations,
     * not merely those observed before them. */
    if(lseek(fd,0,SEEK_SET)<0)goto finish;
    pos=0;
    while(pos<size){
        size_t want=size-pos<sizeof(scratch)?size-pos:sizeof(scratch);
        ssize_t got=read(fd,scratch,want);
        if(got<=0 || memcmp(bytes+pos,scratch,(size_t)got)!=0)
            goto finish;
        pos+=(size_t)got;
    }
    if(read(fd,scratch,1)!=0)goto finish;
    if(vh102_parent_matches(dirfd,parent)!=0 ||
       fstat(fd,&again)<0 ||
       fstatat(dirfd,base,&named,AT_SYMLINK_NOFOLLOW)<0 ||
       named.st_dev!=initial.st_dev || named.st_ino!=initial.st_ino ||
       again.st_dev!=initial.st_dev || again.st_ino!=initial.st_ino ||
       again.st_size!=initial.st_size ||
       again.st_mtim.tv_sec!=initial.st_mtim.tv_sec ||
       again.st_mtim.tv_nsec!=initial.st_mtim.tv_nsec ||
       again.st_ctim.tv_sec!=initial.st_ctim.tv_sec ||
       again.st_ctim.tv_nsec!=initial.st_ctim.tv_nsec ||
       named.st_size!=initial.st_size || named.st_nlink!=1 ||
       !S_ISREG(named.st_mode) || (named.st_mode&0777)!=0600)
        goto finish;
    if(fstatat(dirfd,stage,&stage_stat,AT_SYMLINK_NOFOLLOW)==0 ||
       errno!=ENOENT)goto finish;
    ok=0;
finish:
    if(fd>=0 && close(fd)<0)ok=-1;
    if(dirfd>=0 && close(dirfd)<0)ok=-1;
    if(ok==0){vh101_commits++;vh104_second_reads++;}
    return ok;
}
