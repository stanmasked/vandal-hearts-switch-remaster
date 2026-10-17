#define _POSIX_C_SOURCE 200809L
#include "vh_audio_scene_trace_export.h"

#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

typedef struct {
    int corrupt_readback;
    int fail_flush;
    int fail_rename;
    int create_racing_target;
    char racing_target[VH_SCENE_TRACE_EXPORT_PATH_CAP];
} Inject;

static int present(void *unused,const char *path) {
    (void)unused;
    struct stat st;
    if(stat(path,&st)==0) return 1;
    return errno==ENOENT ? 0 : -1;
}
static FILE *create_exclusive(void *unused,const char *path) {
    (void)unused;
    const int fd=open(path,O_CREAT|O_WRONLY|O_EXCL,0600);
    if(fd<0) return NULL;
    FILE *f=fdopen(fd,"wb");
    if(!f) (void)close(fd);
    return f;
}
static FILE *open_read(void *ctx,const char *path) {
    Inject *a=ctx;
    if(a->create_racing_target) {
        FILE *race=fopen(a->racing_target,"wb");
        assert(race);
        assert(fputs("RACING_OWNER\n",race)>=0);
        assert(fclose(race)==0);
    }
    if(a->corrupt_readback) {
        FILE *f=fopen(path,"r+b");
        assert(f);
        assert(fseek(f,58,SEEK_SET)==0);
        assert(fputc('X',f)!=EOF);
        assert(fflush(f)==0);
        assert(fclose(f)==0);
    }
    return fopen(path,"rb");
}
static int injected_flush(void *ctx,FILE *f) {
    Inject *a=ctx;
    if(a->fail_flush) return -1;
    return fflush(f);
}
static int standard_close(void *unused,FILE *f) {
    (void)unused;
    return fclose(f);
}
static int injected_rename(void *ctx,const char *from,const char *to) {
    Inject *a=ctx;
    return a->fail_rename ? -1 : rename(from,to);
}
static int standard_remove(void *unused,const char *path) {
    (void)unused;
    return remove(path);
}
static VhSceneTraceExportOps operations(Inject *a) {
    return (VhSceneTraceExportOps) {
        a,present,create_exclusive,open_read,
        injected_flush,standard_close,injected_rename,standard_remove
    };
}
static void file_path(char *buf,size_t cap,const char *dir,
                      unsigned slot,const char *ext) {
    const int n=snprintf(buf,cap,"%s/audio-scene-trace-%04u.%s",
                         dir,slot,ext);
    assert(n>0 && (size_t)n<cap);
}
static int file_bytes_equal(const char *path,const char *expected) {
    FILE *f=fopen(path,"rb"); assert(f);
    char buffer[1024];
    const size_t n=fread(buffer,1,sizeof buffer,f);
    assert(fclose(f)==0);
    return n==strlen(expected) && !memcmp(buffer,expected,n);
}
static VhAudioSceneTrace fixture(void) {
    VhAudioSceneTrace t;
    vh_audio_scene_trace_init(&t);
    assert(vh_audio_scene_trace_record(&t,VH_SCENE_TRACE_INPUT,1,2,100)==1);
    assert(vh_audio_scene_trace_record(&t,VH_SCENE_TRACE_POST,1,2,105)==1);
    assert(vh_audio_scene_trace_record(&t,VH_SCENE_TRACE_ACCEPT,1,2,140)==1);
    assert(vh_audio_scene_trace_record(&t,VH_SCENE_TRACE_SUBMIT_CALL,1,2,160)==1);
    assert(vh_audio_scene_trace_record(&t,VH_SCENE_TRACE_RELEASE_RETURN,1,2,250)==1);
    /* Returning this C11 atomic-containing value is safe here because
     * the producer has joined and no other thread accesses the copy. */
    return t;
}
int main(void) {
    char directory[]="/tmp/vh-scene-export-XXXXXX";
    assert(mkdtemp(directory));
    VhAudioSceneTrace t=fixture();
    char result[VH_SCENE_TRACE_EXPORT_PATH_CAP];
    char path[VH_SCENE_TRACE_EXPORT_PATH_CAP];
    assert(vh_audio_scene_trace_export(&t,directory,NULL,result,sizeof result)
           ==VH_SCENE_EXPORT_OK);
    file_path(path,sizeof path,directory,0,"csv");
    assert(!strcmp(result,path));
    assert(file_bytes_equal(path,
        "index,event,serial,scene,monotonic_ns,dropped_total\n"
        "0,INPUT,1,2,100,0\n"
        "1,POST,1,2,105,0\n"
        "2,ACCEPT,1,2,140,0\n"
        "3,SUBMIT_CALL,1,2,160,0\n"
        "4,RELEASE_RETURN,1,2,250,0\n"));

    assert(vh_audio_scene_trace_export(&t,directory,NULL,result,sizeof result)
           ==VH_SCENE_EXPORT_OK);
    file_path(path,sizeof path,directory,1,"csv");
    assert(!strcmp(result,path));
    file_path(path,sizeof path,directory,2,"csv");
    FILE *occupied=fopen(path,"wb");
    assert(occupied);
    assert(fputs("ORIGINAL\n",occupied)>=0);
    assert(fclose(occupied)==0);
    assert(vh_audio_scene_trace_export(&t,directory,NULL,result,sizeof result)
           ==VH_SCENE_EXPORT_OK);
    assert(file_bytes_equal(path,"ORIGINAL\n"));
    file_path(path,sizeof path,directory,3,"csv");
    assert(!strcmp(path,result));

    Inject inject={0};
    VhSceneTraceExportOps ops=operations(&inject);
    inject.corrupt_readback=1;
    assert(vh_audio_scene_trace_export(&t,directory,&ops,result,sizeof result)
           ==VH_SCENE_EXPORT_VERIFY);
    assert(result[0]=='\0');
    file_path(path,sizeof path,directory,4,"tmp");
    assert(present(NULL,path)==0);
    file_path(path,sizeof path,directory,4,"csv");
    assert(present(NULL,path)==0);

    inject.corrupt_readback=0;
    inject.fail_flush=1;
    assert(vh_audio_scene_trace_export(&t,directory,&ops,result,sizeof result)
           ==VH_SCENE_EXPORT_FLUSH);
    inject.fail_flush=0;
    inject.fail_rename=1;
    assert(vh_audio_scene_trace_export(&t,directory,&ops,result,sizeof result)
           ==VH_SCENE_EXPORT_RENAME);
    inject.fail_rename=0;

    inject.create_racing_target=1;
    file_path(inject.racing_target,sizeof inject.racing_target,
              directory,4,"csv");
    assert(vh_audio_scene_trace_export(&t,directory,&ops,result,sizeof result)
           ==VH_SCENE_EXPORT_SLOTS_FULL);
    assert(file_bytes_equal(inject.racing_target,"RACING_OWNER\n"));
    file_path(path,sizeof path,directory,4,"tmp");
    assert(present(NULL,path)==0);
    inject.create_racing_target=0;

    /* A dangling .tmp from an interrupted attempt is not overwritten.
     * A new capture selects the next free slot instead. */
    file_path(path,sizeof path,directory,5,"tmp");
    occupied=fopen(path,"wb");
    assert(occupied);
    assert(fputs("PREVIOUS_TEMP\n",occupied)>=0);
    assert(fclose(occupied)==0);
    assert(vh_audio_scene_trace_export(&t,directory,NULL,result,sizeof result)
           ==VH_SCENE_EXPORT_OK);
    file_path(path,sizeof path,directory,6,"csv");
    assert(!strcmp(result,path));
    file_path(path,sizeof path,directory,5,"tmp");
    assert(file_bytes_equal(path,"PREVIOUS_TEMP\n"));

    /* An overflow is stored in every CSV row, never silently accepted
     * as a complete timeline. */
    VhAudioSceneTrace full;
    vh_audio_scene_trace_init(&full);
    for(unsigned i=0;i<VH_AUDIO_SCENE_TRACE_CAPACITY;i++)
        assert(vh_audio_scene_trace_record(&full,
            VH_SCENE_TRACE_INPUT,i,1,i)==1);
    assert(vh_audio_scene_trace_record(&full,
        VH_SCENE_TRACE_INPUT,99,1,99)==0);
    assert(vh_audio_scene_trace_export(&full,directory,NULL,
                                       result,sizeof result)
           ==VH_SCENE_EXPORT_OK);
    FILE *f=fopen(result,"rb"); assert(f);
    char line[160]; int rows=0, dropped_found=0;
    while(fgets(line,sizeof line,f)) {
        if(rows++>0) {
            const size_t len=strlen(line);
            if(len>=3 && !strcmp(line+len-3,",1\n")) dropped_found++;
        }
    }
    assert(fclose(f)==0);
    assert(rows==65 && dropped_found==64);

    assert(vh_audio_scene_trace_export(&t,directory,NULL,result,1)
           ==VH_SCENE_EXPORT_PATH);
    assert(result[0]=='\0');
    assert(vh_audio_scene_trace_export(NULL,directory,NULL,result,
                                       sizeof result)==VH_SCENE_EXPORT_INVALID);

    /* Test-owned sandbox; all files created above are disposable. */
    for(unsigned slot=0;slot<VH_SCENE_TRACE_EXPORT_SLOTS;slot++) {
        for(unsigned i=0;i<2;i++) {
            file_path(path,sizeof path,directory,slot,i ? "tmp" : "csv");
            if(present(NULL,path)==1) assert(remove(path)==0);
        }
    }
    assert(rmdir(directory)==0);
    puts("PASS: SD scene CSV exclusive slots, byte readback, fault injection, overflow");
    return 0;
}
