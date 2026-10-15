#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/map_decode_checked.h"

static void test_literal(void) {
    const uint8_t code[] = {0x00, 'A','B','C'};
    uint8_t out[5] = {0xaa,0xaa,0xaa,0xaa,0xaa};
    size_t n = 999;
    assert(vh_map_decode_checked(code,sizeof(code),out,4,&n)==VH_MAP_DECODE_OK);
    assert(n==3 && !memcmp(out,"ABC",3) && out[3]==0xaa);
    assert(vh_map_decode_checked(code,sizeof(code),out,2,&n)==VH_MAP_DECODE_OUTPUT_FULL);
    assert(n==2 && out[3]==0xaa);
}

static void test_absolute(void) {
    /* At dictionary position 990 a literal is stored; copy from 0x3de. */
    const uint8_t code[] = {0x02, 'A', 0x03, 0xde};
    uint8_t out[8] = {0}; size_t n = 0;
    assert(vh_map_decode_checked(code,sizeof(code),out,sizeof(out),&n)==VH_MAP_DECODE_OK);
    /* The dictionary is updated during copy: each overlapping byte repeats A. */
    assert(n==4 && out[0]=='A' && out[1]=='A' && out[2]=='A' && out[3]=='A');
}

static void test_relative(void) {
    const uint8_t code[] = {0x02, 'Z', 0x81};
    uint8_t out[8] = {0}; size_t n = 0;
    assert(vh_map_decode_checked(code,sizeof(code),out,sizeof(out),&n)==VH_MAP_DECODE_OK);
    assert(n==3 && out[0]=='Z' && out[1]=='Z' && out[2]=='Z');
}

static void test_raw_run_and_errors(void) {
    const uint8_t raw[] = {0x01,0xc0,1,2,3,4,5,6,7,8};
    const uint8_t short_run[] = {0x01,0xc0,1,2};
    const uint8_t short_absolute[] = {0x01,0x00};
    uint8_t out[10]; size_t n=0;
    memset(out,0xab,sizeof(out));
    assert(vh_map_decode_checked(raw,sizeof(raw),out,8,&n)==VH_MAP_DECODE_OK);
    assert(n==8 && out[0]==1 && out[7]==8 && out[8]==0xab);
    assert(vh_map_decode_checked(raw,sizeof(raw),out,7,&n)==VH_MAP_DECODE_OUTPUT_FULL);
    assert(n==0 && out[8]==0xab);
    assert(vh_map_decode_checked(short_run,sizeof(short_run),out,8,&n)==VH_MAP_DECODE_TRUNCATED);
    assert(vh_map_decode_checked(short_absolute,sizeof(short_absolute),out,8,&n)==VH_MAP_DECODE_TRUNCATED);
    assert(vh_map_decode_checked(NULL,4,out,8,&n)==VH_MAP_DECODE_INVALID_ARGUMENT && n==0);
    assert(vh_map_decode_checked(raw,sizeof(raw),out,8,NULL)==VH_MAP_DECODE_INVALID_ARGUMENT);
}
static void test_multiple_control_groups(void) {
    /* A full group of eight literal commands must consume a new control
     * byte before decoding the next group. */
    const uint8_t code[] = {
        0x00, 'a','b','c','d','e','f','g','h',
        0x02, 'Q', 0x81
    };
    uint8_t out[13] = {0};
    size_t n = 0;
    assert(vh_map_decode_checked(code, sizeof(code), out, 11, &n)
           == VH_MAP_DECODE_OK);
    assert(n == 11);
    assert(memcmp(out, "abcdefghQQQ", 11) == 0);
    /* No byte of the following guard position may be touched. */
    assert(out[11] == 0);
    assert(vh_map_decode_checked(code, sizeof(code), out, 10, &n)
           == VH_MAP_DECODE_OUTPUT_FULL);
    assert(n == 9);
}

int main(void) {
    test_literal();
    test_absolute();
    test_relative();
    test_raw_run_and_errors();
    test_multiple_control_groups();
    puts("Checked map decoder tests passed.");
    return 0;
}
