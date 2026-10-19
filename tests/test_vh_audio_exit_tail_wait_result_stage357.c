/* Stage357: C11 source-only service Result emission invariant tests.
 * Genuine libnx service Result must still be observed in real NeXium.
 */
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "vh_audio_exit_tail_wait_result_stage357.h"

static void expect_csv(unsigned code,int called,uint32_t result) {
    VhAudioTailWaitResult357 wait={0};
    VhAudioExitTailReason reason={0};
    vh_tail357_reset(&wait);
    vh_audio_tail_reason_reset(&reason);
    vh_audio_tail_reason_record(&reason,(VhAudioTailReasonCode)code);
    if(called) vh_tail357_record(&wait,result);
    FILE *f=tmpfile();
    assert(f);
    assert(vh_tail357_write_csv(&wait,&reason,f)==4);
    rewind(f);
    char line[96],expected[96];
    assert(fgets(line,sizeof line,f) && !strcmp(line,"scope,value\n"));
    assert(fgets(line,sizeof line,f) &&
           !strcmp(line,"software_wait_result_only,1\n"));
    assert(fgets(line,sizeof line,f));
    assert(snprintf(expected,sizeof expected,"wait_result_observed,%u\n",
                    (unsigned)called)>0);
    assert(!strcmp(line,expected));
    assert(fgets(line,sizeof line,f));
    assert(snprintf(expected,sizeof expected,"audout_wait_result_raw,%u\n",
                    (unsigned)result)>0);
    assert(!strcmp(line,expected));
    assert(fgets(line,sizeof line,f));
    assert(snprintf(expected,sizeof expected,"stage351_tail_reason_code,%u\n",
                    code)>0);
    assert(!strcmp(line,expected));
    assert(fgetc(f)==EOF && !ferror(f));
    fclose(f);
}
static void reject(unsigned code,int called,uint32_t result) {
    VhAudioTailWaitResult357 wait={0};
    VhAudioExitTailReason reason={0};
    vh_tail357_reset(&wait);vh_audio_tail_reason_reset(&reason);
    vh_audio_tail_reason_record(&reason,(VhAudioTailReasonCode)code);
    if(called) vh_tail357_record(&wait,result);
    FILE *f=tmpfile();assert(f);
    assert(vh_tail357_write_csv(&wait,&reason,f)==-1);
    fclose(f);
}
int main(void) {
    for(unsigned code=0;code<=3;code++)expect_csv(code,0,0);
    for(unsigned code=5;code<=7;code++)expect_csv(code,1,0);
    expect_csv(4,1,UINT32_C(0x2001));
    expect_csv(4,1,UINT32_MAX);
    reject(4,0,0);
    reject(4,1,0);
    reject(7,1,123);
    reject(6,0,0);
    reject(3,1,5);
    reject(2,1,0);
    reject(8,1,0);
    puts("Stage357: original wait Result raw software snapshot source guards PASS");
    return 0;
}
