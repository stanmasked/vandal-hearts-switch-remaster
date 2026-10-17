#include "vh_audio_scene_trace.h"
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>

typedef struct { VhAudioSceneTrace *trace; unsigned producer; } Task;
static void *writer(void *arg) {
    Task *t=arg;
    for (unsigned i=0;i<12;i++) {
        assert(vh_audio_scene_trace_record(t->trace,VH_SCENE_TRACE_POST,
                                           t->producer*100u+i,1u,
                                           t->producer*1000u+i)==1);
    }
    return NULL;
}
int main(void) {
    VhAudioSceneTrace trace;
    vh_audio_scene_trace_init(&trace);
    VhAudioSceneTraceSlot s;
    assert(vh_audio_scene_trace_snapshot(&trace,0,&s)==0);
    assert(vh_audio_scene_trace_record(NULL,VH_SCENE_TRACE_INPUT,0,1,0)==-1);
    assert(vh_audio_scene_trace_record(&trace,(VhAudioSceneTraceKind)0,0,1,0)==-1);
    assert(vh_audio_scene_trace_record(&trace,VH_SCENE_TRACE_INPUT,0,3,0)==-1);
    assert(vh_audio_scene_trace_record(&trace,VH_SCENE_TRACE_INPUT,1,2,1234)==1);
    assert(vh_audio_scene_trace_snapshot(&trace,0,&s)==1);
    assert(s.kind==VH_SCENE_TRACE_INPUT && s.serial==1 &&
           s.scene==2 && s.monotonic_ns==1234);
    assert(vh_audio_scene_trace_snapshot(&trace,1,&s)==0);
    pthread_t threads[4]; Task args[4];
    for (unsigned i=0;i<4;i++) {
        args[i]=(Task){&trace,i+1};
        assert(pthread_create(&threads[i],NULL,writer,&args[i])==0);
    }
    for (unsigned i=0;i<4;i++) assert(pthread_join(threads[i],NULL)==0);
    assert(vh_audio_scene_trace_dropped(&trace)==0);
    FILE *file=tmpfile(); assert(file);
    assert(vh_audio_scene_trace_write_csv(&trace,file)==49);
    rewind(file);
    char line[160]; unsigned lines=0;
    while (fgets(line,sizeof line,file)) {
        assert(strchr(line,'\n'));
        lines++;
    }
    assert(lines==50);
    fclose(file);
    for (unsigned i=49;i<VH_AUDIO_SCENE_TRACE_CAPACITY;i++)
        assert(vh_audio_scene_trace_record(&trace,VH_SCENE_TRACE_ACCEPT,i,2,i)==1);
    assert(vh_audio_scene_trace_record(&trace,VH_SCENE_TRACE_POST,99,1,999)==0);
    assert(vh_audio_scene_trace_record(&trace,VH_SCENE_TRACE_POST,99,1,999)==0);
    assert(vh_audio_scene_trace_dropped(&trace)==2);
    assert(vh_audio_scene_trace_snapshot(&trace,63,&s)==1);
    assert(vh_audio_scene_trace_snapshot(&trace,64,&s)==-1);
    puts("PASS: 64-entry bounded atomic scene-trace publication, CSV and overflow");
    return 0;
}
