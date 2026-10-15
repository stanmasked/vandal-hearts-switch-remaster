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


static void test_command_limits(void) {
    uint8_t raw[73] = {0x01, 0xff};
    uint8_t out[75];
    size_t n = 0;
    for (size_t i = 0; i < 71; ++i) raw[i + 2] = (uint8_t)(i + 1);
    memset(out, 0x5a, sizeof out);
    assert(vh_map_decode_checked(raw, sizeof raw, out, 71, &n)
           == VH_MAP_DECODE_OK);
    assert(n == 71 && memcmp(out, raw + 2, 71) == 0);
    assert(out[71] == 0x5a);
    assert(vh_map_decode_checked(raw, sizeof raw, out, 70, &n)
           == VH_MAP_DECODE_OUTPUT_FULL && n == 0);

    /* Maximum absolute copy: (0x7c >> 2) + 3 = 34 bytes. */
    {
        const uint8_t absolute[] = {0x01, 0x7c, 0x00};
        memset(out, 0x5a, sizeof out);
        assert(vh_map_decode_checked(absolute, sizeof absolute, out, 34, &n)
               == VH_MAP_DECODE_OK && n == 34);
        for (size_t i = 0; i < 34; ++i) assert(out[i] == 0);
        assert(out[34] == 0x5a);
        assert(vh_map_decode_checked(absolute, sizeof absolute, out, 33, &n)
               == VH_MAP_DECODE_OUTPUT_FULL && n == 0);
    }
    /* Maximum relative copy: ((0xb0 & 0x30) >> 4) + 2 = 5. */
    {
        const uint8_t relative[] = {0x01, 0xb0};
        memset(out, 0x5a, sizeof out);
        assert(vh_map_decode_checked(relative, sizeof relative, out, 5, &n)
               == VH_MAP_DECODE_OK && n == 5);
        for (size_t i = 0; i < 5; ++i) assert(out[i] == 0);
        assert(out[5] == 0x5a);
        assert(vh_map_decode_checked(relative, sizeof relative, out, 4, &n)
               == VH_MAP_DECODE_OUTPUT_FULL && n == 0);
    }
    /* A missing final byte of the longest raw run is an input error. */
    assert(vh_map_decode_checked(raw, sizeof raw - 1, out, sizeof out, &n)
           == VH_MAP_DECODE_TRUNCATED && n == 0);
}

static void test_dictionary_wrap(void) {
    uint8_t code[40], out[40];
    size_t ip = 0, n = 0;
    /* Initial dictionary cursor 990 + 32 literals = 1022. */
    for (unsigned group = 0; group < 4; ++group) {
        code[ip++] = 0x00;
        for (unsigned j = 0; j < 8; ++j)
            code[ip++] = (uint8_t)('a' + group);
    }
    /* Literal X -> index 1022, literal Y -> 1023, then wrap to 0.
     * The relative copy with distance 1 repeats Y over the boundary. */
    code[ip++] = 0x04;
    code[ip++] = 'X';
    code[ip++] = 'Y';
    code[ip++] = 0x81;
    assert(ip == sizeof code);
    memset(out, 0xcc, sizeof out);
    assert(vh_map_decode_checked(code, ip, out, 36, &n)
           == VH_MAP_DECODE_OK && n == 36);
    for (unsigned group = 0; group < 4; ++group)
        for (unsigned j = 0; j < 8; ++j)
            assert(out[group * 8 + j] == (uint8_t)('a' + group));
    assert(out[32] == 'X' && out[33] == 'Y');
    assert(out[34] == 'Y' && out[35] == 'Y' && out[36] == 0xcc);
    assert(vh_map_decode_checked(code, ip, out, 35, &n)
           == VH_MAP_DECODE_OUTPUT_FULL && n == 34);
}

int main(void) {
    test_literal();
    test_absolute();
    test_relative();
    test_raw_run_and_errors();
    test_multiple_control_groups();
    test_command_limits();
    test_dictionary_wrap();
    puts("Checked map decoder tests passed.");
    return 0;
}
