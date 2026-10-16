/* Asset-free host reference for the optional Switch audio hardware
 * diagnostic overlay. No libnx, PCM audio, threads, I/O or GUI calls.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "vh_audio_diagnostics.h"

static void expect_supported_glyphs(const VhAudioDiagText *panel) {
    for (unsigned l=0;l<VH_AUDIO_DIAG_LINES;++l) {
        const size_t n=strlen(panel->line[l]);
        assert(n>0u && n<VH_AUDIO_DIAG_LINE_CAP);
        for(size_t c=0;c<n;++c) {
            const char ch=panel->line[l][c];
            assert((ch>='A' && ch<='Z') ||
                   (ch>='0' && ch<='9') ||
                   ch==' ' || ch=='-');
        }
    }
}

static void test_snapshot_format(void) {
    VhAudioDiagnostics d={0};
    VhAudioDiagText text={0};
    assert(vh_audio_diag_format(NULL,&text)==-1);
    assert(vh_audio_diag_format(&d,NULL)==-1);
    assert(vh_audio_diag_format(&d,&text)==0);
    assert(!strcmp(text.line[0],"AUDIO DIAGNOSTICS"));
    assert(!strcmp(text.line[1],"STATE START"));
    assert(!strcmp(text.line[4],"LAST PCM US 0"));
    expect_supported_glyphs(&text);

    d.status=1;
    d.bank_warnings=3;
    d.resume_events=12;
    d.confirmed_resumes=13;
    d.last_confirmed_us=11680;
    d.worst_confirmed_us=68900;
    d.pages_submitted=54901;
    d.frames_submitted=30520000;
    d.submit_failures=7;
    d.restart_attempts=5;
    d.recoveries=4;
    d.resume_failures=6;
    d.resume_restarts=8;
    d.resume_recoveries=2;
    d.lease_mismatches=1;
    d.abandoned_sessions=3;
    assert(!vh_audio_diag_format(&d,&text));
    assert(!strcmp(text.line[1],"STATE PLAYING"));
    assert(!strcmp(text.line[2],"HOME RESUMES 12"));
    assert(!strcmp(text.line[3],"FIRST PCM COUNT 13"));
    assert(!strcmp(text.line[4],"LAST PCM US 11680"));
    assert(!strcmp(text.line[5],"WORST PCM US 68900"));
    assert(!strcmp(text.line[6],"OUTPUT PAGES 54901"));
    assert(!strcmp(text.line[7],"PCM FAIL 7 RESTART 5"));
    assert(!strcmp(text.line[8],"HOME FAIL 6 REOPEN 8"));
    assert(!strcmp(text.line[9],"LEASE FAIL 1 RESET 3"));
    assert(!strcmp(text.line[10],"VAB WARN 3 RECOVERED 6"));
    expect_supported_glyphs(&text);
    d.status=2;
    assert(!vh_audio_diag_format(&d,&text));
    assert(!strcmp(text.line[1],"STATE PAUSED"));
    d.status=-9;
    assert(!vh_audio_diag_format(&d,&text));
    assert(!strcmp(text.line[1],"STATE ERROR"));
}

static void test_extreme_counters_and_saturation(void) {
    VhAudioDiagnostics d={0};
    VhAudioDiagText text={0};
    d.status=1;
    d.bank_warnings=UINT32_MAX;
    d.resume_events=UINT32_MAX;
    d.confirmed_resumes=UINT32_MAX;
    d.last_confirmed_us=UINT64_MAX;
    d.worst_confirmed_us=UINT64_MAX;
    d.pages_submitted=UINT64_MAX;
    d.frames_submitted=UINT64_MAX;
    d.submit_failures=UINT32_MAX;
    d.restart_attempts=UINT32_MAX;
    d.recoveries=UINT32_MAX;
    d.resume_failures=UINT32_MAX;
    d.resume_restarts=UINT32_MAX;
    d.resume_recoveries=UINT32_MAX;
    d.lease_mismatches=UINT32_MAX;
    d.abandoned_sessions=UINT32_MAX;
    assert(!vh_audio_diag_format(&d,&text));
    expect_supported_glyphs(&text);
    assert(!strcmp(text.line[5],"WORST PCM US 18446744073709551615"));
    assert(!strcmp(text.line[6],"OUTPUT PAGES 18446744073709551615"));
    assert(!strcmp(text.line[10],
                   "VAB WARN 4294967295 RECOVERED 4294967295"));
    /* Formatter never writes outside the supplied structure. */
    struct {
        unsigned char before[8];
        VhAudioDiagText panel;
        unsigned char after[8];
    } guarded={0};
    memset(guarded.before,0xA6,sizeof guarded.before);
    memset(guarded.after,0x5B,sizeof guarded.after);
    assert(!vh_audio_diag_format(&d,&guarded.panel));
    for(size_t i=0;i<sizeof guarded.before;i++)
        assert(guarded.before[i]==0xA6);
    for(size_t i=0;i<sizeof guarded.after;i++)
        assert(guarded.after[i]==0x5B);
}

int main(void) {
    test_snapshot_format();
    test_extreme_counters_and_saturation();
    puts("Switch audio diagnostic HUD: asset-free bounded ASCII telemetry PASS");
    return 0;
}
