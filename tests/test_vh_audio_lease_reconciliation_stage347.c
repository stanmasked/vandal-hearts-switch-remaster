#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_lease_reconciliation.h"
static VhAudioDiagnostics source(void) {
    VhAudioDiagnostics s={0};
    s.lease_pages_acquired=513;
    s.lease_pages_released=512;
    s.abandoned_sessions=1;
    s.lease_busy_begin_rejections=170;
    s.lease_mismatches=171;
    s.pages_submitted=510;
    s.submit_failures=5;
    return s;
}
int main(void) {
    VhAudioDiagnostics s=source();
    assert(vh_audio_lease_reconciliation_valid(&s)==0);
    FILE *f=tmpfile();
    assert(f && vh_audio_lease_reconciliation_write(&s,f)==8);
    rewind(f);
    const char *rows[]={
        "scope,value\n","software_lease_only,1\n",
        "lease_pages_acquired,513\n","lease_pages_released,512\n",
        "abandoned_sessions,1\n","busy_begin_rejections,170\n",
        "mismatched_releases,171\n","accepted_pages_submitted,510\n",
        "submit_failures,5\n"
    };
    char line[128];
    for(size_t i=0;i<sizeof rows/sizeof *rows;i++) {
        assert(fgets(line,sizeof line,f) && !strcmp(line,rows[i]));
    }
    assert(fgetc(f)==EOF && !ferror(f));
    fclose(f);
    assert(vh_audio_lease_reconciliation_valid(NULL)==-1);
    assert(vh_audio_lease_reconciliation_write(&s,NULL)==-1);
    s=source();s.lease_pages_acquired=0;
    assert(vh_audio_lease_reconciliation_valid(&s)==-1);
    s=source();s.lease_pages_released=514;
    assert(vh_audio_lease_reconciliation_valid(&s)==-1);
    s=source();s.abandoned_sessions=0;
    assert(vh_audio_lease_reconciliation_valid(&s)==-1);
    s=source();s.abandoned_sessions=2;
    assert(vh_audio_lease_reconciliation_valid(&s)==-1);
    s=source();s.pages_submitted=513;
    assert(vh_audio_lease_reconciliation_valid(&s)==-1);
    s=source();s.lease_pages_acquired=UINT64_MAX;
    assert(vh_audio_lease_reconciliation_valid(&s)==-1);
    s=source();s.lease_pages_released=UINT64_MAX;
    assert(vh_audio_lease_reconciliation_valid(&s)==-1);
    s=source();s.abandoned_sessions=UINT32_MAX;
    assert(vh_audio_lease_reconciliation_valid(&s)==-1);
    s=source();s.lease_pages_acquired=512;s.abandoned_sessions=0;
    assert(vh_audio_lease_reconciliation_valid(&s)==0);
    puts("Stage347 software-only original after-join lease accounting PASS");
    return 0;
}
