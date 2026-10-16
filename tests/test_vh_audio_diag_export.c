/* Normal/failed SD export of on-console audio journals.
 * Simulates FULL/DENIED/SHORT-WRITE/FLUSH/CLOSE/RENAME failures.
 * Uses only host temporary files with no Switch or game assets.
 */
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "vh_audio_diag_export.h"

typedef struct {
    int fail_exists,fail_open,fail_write,fail_flush,fail_close,fail_rename;
    unsigned opens,writes,flushes,closes,renames,removes,stats;
} FaultIO;

static int mock_exists(void *p,const char *path) {
    FaultIO *f=p;
    ++f->stats;
    if(f->fail_exists) return -1;
    struct stat st;
    if(!stat(path,&st)) return 1;
    return errno==ENOENT ? 0 : -1;
}
static FILE *mock_open(void *p,const char *path) {
    FaultIO *f=p;
    ++f->opens;
    return f->fail_open ? NULL : fopen(path,"wb");
}
static int mock_write(void *p,const VhAudioDiagJournal *j,FILE *file) {
    FaultIO *f=p;
    ++f->writes;
    if(f->fail_write) {
        /* A few bytes may already have reached the SD cache when
         * the actual CSV writer signals an I/O error. */
        (void)fputs("partial,not,valid\n",file);
        return -1;
    }
    return vh_audio_diag_journal_write_csv(j,file);
}
static int mock_flush(void *p,FILE *file) {
    FaultIO *f=p;
    ++f->flushes;
    const int rc=fflush(file);
    return f->fail_flush ? -1 : rc;
}
static int mock_close(void *p,FILE *file) {
    FaultIO *f=p;
    ++f->closes;
    const int rc=fclose(file);
    return f->fail_close ? -1 : rc;
}
static int mock_rename(void *p,const char *from,const char *to) {
    FaultIO *f=p;
    ++f->renames;
    return f->fail_rename ? -1 : rename(from,to);
}
static int mock_remove(void *p,const char *path) {
    FaultIO *f=p;
    ++f->removes;
    return remove(path);
}
static VhAudioDiagExportOps callbacks(FaultIO *f) {
    const VhAudioDiagExportOps o={
        f,mock_exists,mock_open,mock_write,mock_flush,mock_close,
        mock_rename,mock_remove
    };
    return o;
}
static VhAudioDiagJournal journal;

static void make_journal(void) {
    vh_audio_diag_journal_reset(&journal);
    VhAudioDiagnostics d={.status=1};
    assert(vh_audio_diag_journal_sample(&journal,0,&d)==1);
    d.pages_submitted=1200;
    d.frames_submitted=668400;
    d.submit_failures=9;
    d.resume_events=5;
    assert(vh_audio_diag_journal_sample(&journal,6000,&d)==1);
    d.status=0;
    assert(vh_audio_diag_journal_finish(&journal,6100,&d)==1);
    assert(journal.count==3);
}
static void read_valid(const char *path) {
    FILE *f=fopen(path,"rb");
    assert(f);
    char s[512];
    assert(fgets(s,sizeof s,f));
    assert(strstr(s,"elapsed_ms,event,status,home_resumes,"));
    assert(fgets(s,sizeof s,f));
    assert(strstr(s,",START,"));
    assert(fgets(s,sizeof s,f));
    assert(strstr(s,",ERROR,"));
    assert(fgets(s,sizeof s,f));
    assert(strstr(s,",EXIT,"));
    assert(!fgets(s,sizeof s,f));
    assert(fclose(f)==0);
}
static int present(const char *path) {
    struct stat st;
    return stat(path,&st)==0;
}
static void test_failure_matrix(const char *dir) {
    FaultIO flags={0};
    const VhAudioDiagExportOps ops=callbacks(&flags);
    char path[512],temp[512],expected[512];
    snprintf(temp,sizeof temp,"%s/audio-diagnostics.tmp",dir);
    snprintf(expected,sizeof expected,"%s/audio-diagnostics-0000.csv",dir);

    assert(vh_audio_diag_export(&journal,dir,NULL,NULL,0)==
           VH_AUDIO_EXPORT_INVALID);
    assert(vh_audio_diag_export(&journal,dir,NULL,path,1)==
           VH_AUDIO_EXPORT_PATH);
    assert(vh_audio_diag_export(&journal,"",NULL,path,sizeof path)==
           VH_AUDIO_EXPORT_INVALID);
    assert(vh_audio_diag_export(NULL,dir,NULL,path,sizeof path)==
           VH_AUDIO_EXPORT_INVALID);
    assert(vh_audio_diag_export(&journal,dir,&ops,NULL,0)==
           VH_AUDIO_EXPORT_INVALID);
    assert(!present(expected));

    for(unsigned mode=0;mode<6u;mode++) {
        memset(&flags,0,sizeof flags);
        flags.fail_exists=mode==0u;
        flags.fail_open=mode==1u;
        flags.fail_write=mode==2u;
        flags.fail_flush=mode==3u;
        flags.fail_close=mode==4u;
        flags.fail_rename=mode==5u;
        const VhAudioDiagExportResult want=(VhAudioDiagExportResult)
            (mode==0u ? VH_AUDIO_EXPORT_STAT:
             mode==1u ? VH_AUDIO_EXPORT_OPEN:
             mode==2u ? VH_AUDIO_EXPORT_WRITE:
             mode==3u ? VH_AUDIO_EXPORT_FLUSH:
             mode==4u ? VH_AUDIO_EXPORT_CLOSE:
                        VH_AUDIO_EXPORT_RENAME);
        snprintf(path,sizeof path,"dirty");
        assert(vh_audio_diag_export(&journal,dir,&ops,path,sizeof path)==want);
        assert(path[0]=='\0');
        assert(!present(expected));
        assert(!present(temp));
        if(mode>1u) {
            assert(flags.opens==1);
            assert(flags.closes==1);
            assert(flags.removes==1);
        }
        if(mode==0u) assert(flags.opens==0);
        if(mode==1u) assert(flags.closes==0);
        if(mode==5u) assert(flags.renames==1);
    }

    memset(&flags,0,sizeof flags);
    assert(vh_audio_diag_export(&journal,dir,&ops,path,sizeof path)==
           VH_AUDIO_EXPORT_OK);
    assert(!strcmp(path,expected));
    assert(flags.renames==1 && flags.closes==1);
    assert(!present(temp));
    read_valid(expected);

    /* A failed later session MUST NOT truncate an earlier valid CSV. */
    flags.fail_write=1;
    assert(vh_audio_diag_export(&journal,dir,&ops,path,sizeof path)==
           VH_AUDIO_EXPORT_WRITE);
    assert(path[0]=='\0');
    read_valid(expected);
    assert(!present(temp));
    flags.fail_write=0;
    assert(vh_audio_diag_export(&journal,dir,&ops,path,sizeof path)==
           VH_AUDIO_EXPORT_OK);
    assert(strstr(path,"audio-diagnostics-0001.csv"));
    read_valid(expected);
    read_valid(path);

    /* All 64 slots occupied: fail without writing a temporary file. */
    for(unsigned slot=2;slot<VH_AUDIO_DIAG_EXPORT_SLOTS;slot++) {
        char occupied[512];
        snprintf(occupied,sizeof occupied,
                 "%s/audio-diagnostics-%04u.csv",dir,slot);
        FILE *f=fopen(occupied,"wb");
        assert(f);
        assert(fputs("existing,do,not,overwrite\n",f)!=EOF);
        assert(fclose(f)==0);
    }
    memset(&flags,0,sizeof flags);
    assert(vh_audio_diag_export(&journal,dir,&ops,path,sizeof path)==
           VH_AUDIO_EXPORT_SLOTS_FULL);
    assert(flags.opens==0 && flags.removes==0);
    read_valid(expected);
    assert(!present(temp));
}
static void test_boundaries_and_counters(void) {
    make_journal();
    assert(journal.origin.elapsed_ms==0);
    assert(journal.entries[2].snapshot.submit_failures==9);
    /* Huge PCM counters are copied as numbers; no signed truncation
     * or unbounded runtime allocations on SD export. */
    journal.entries[2].snapshot.frames_submitted=UINT64_MAX;
    journal.entries[2].snapshot.pages_submitted=UINT64_MAX;
    journal.entries[2].snapshot.submit_failures=UINT32_MAX;
    journal.entries[2].snapshot.resume_events=UINT32_MAX;
    journal.total=UINT64_MAX;
    assert(journal.total==UINT64_MAX);
    assert(journal.count==3);
    journal.entries[2].snapshot.frames_submitted=668400;
    journal.entries[2].snapshot.pages_submitted=1200;
    journal.entries[2].snapshot.submit_failures=9;
    journal.entries[2].snapshot.resume_events=5;
    journal.total=3;
}
int main(void) {
    test_boundaries_and_counters();
    char dir[]="/tmp/vh-audio-sd-faults-XXXXXX";
    assert(mkdtemp(dir));
    test_failure_matrix(dir);
    /* Files remain committed and deliberately read before cleanup.
     * Delete only the test's unique temporary directory contents. */
    for(unsigned i=0;i<VH_AUDIO_DIAG_EXPORT_SLOTS;i++) {
        char path[512];
        snprintf(path,sizeof path,"%s/audio-diagnostics-%04u.csv",dir,i);
        assert(remove(path)==0);
    }
    assert(rmdir(dir)==0);
    puts("SD journal export: temp/rename, 6 injected failures, "
         "prior-file preservation, 64-slot bounds PASS");
    return 0;
}
