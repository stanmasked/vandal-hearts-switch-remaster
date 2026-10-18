#include "vh_audio_exit_output_witness.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void expect(FILE *file, const char *line) {
    char buf[160]={0};
    assert(fgets(buf,sizeof buf,file));
    assert(strcmp(buf,line)==0);
}
static void test_page_and_tail_success(void) {
    VhAudioExitOutputWitness w={0};
    vh_audio_exit_output_reset(&w);
    assert(vh_audio_exit_output_page_returned(NULL,100,128)==-1);
    assert(vh_audio_exit_output_page_returned(&w,0,128)==-1);
    assert(vh_audio_exit_output_page_returned(&w,100,0)==-1);
    assert(vh_audio_exit_output_page_returned(&w,100,4097)==-1);
    assert(vh_audio_exit_output_page_returned(&w,100,256)==1);
    assert(vh_audio_exit_output_page_returned(&w,99,256)==-1);
    assert(vh_audio_exit_output_page_returned(&w,110,200)==1);
    assert(vh_audio_exit_output_tail(&w,120,125,1)==1);
    assert(vh_audio_exit_output_tail(&w,130,135,1)==-1);
    FILE *file=tmpfile();
    assert(file);
    assert(vh_audio_exit_output_write_csv(&w,file)==5);
    rewind(file);
    expect(file,"event,value\n");
    expect(file,"page_return_count,2\n");
    expect(file,"last_page_return_guest_ns,110\n");
    expect(file,"last_page_frames,200\n");
    expect(file,"tail_attempt_guest_ns,120\n");
    expect(file,"tail_success_return_guest_ns,125\n");
    assert(fgetc(file)==EOF);
    assert(fclose(file)==0);
}
static void test_absence_failure_and_reset(void) {
    VhAudioExitOutputWitness w={0};
    vh_audio_exit_output_reset(&w);
    assert(vh_audio_exit_output_tail(&w,10,9,0)==-1);
    assert(vh_audio_exit_output_tail(&w,10,15,2)==-1);
    assert(vh_audio_exit_output_tail(&w,10,15,0)==1);
    FILE *file=tmpfile();
    assert(file);
    assert(vh_audio_exit_output_write_csv(&w,file)==5);
    rewind(file);
    expect(file,"event,value\n");
    expect(file,"page_return_count,0\n");
    expect(file,"last_page_return_guest_ns,0\n");
    expect(file,"last_page_frames,0\n");
    expect(file,"tail_attempt_guest_ns,10\n");
    expect(file,"tail_success_return_guest_ns,0\n");
    assert(fclose(file)==0);
    vh_audio_exit_output_reset(&w);
    assert(vh_audio_exit_output_read(&w.tail_attempt_guest_ns)==0);
    assert(vh_audio_exit_output_write_csv(NULL,stdout)<0);
    assert(vh_audio_exit_output_write_csv(&w,NULL)<0);
}
int main(void) {
    test_page_and_tail_success();
    test_absence_failure_and_reset();
    puts("Stage313 last audout page-return and optional taper witness passed");
    return 0;
}
