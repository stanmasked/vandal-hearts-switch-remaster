/*
 * V45 differential against real src/maps/unpack.c::UnpackMapFileData.
 * NEVER call upstream's unchecked decoder on untrusted data: these are
 * fixed compile-time, verified-short, padded synthetic fixtures ONLY.
 * Standalone executable links only real upstream unpack.o and this driver.
 */
#include <stdio.h>
#include <string.h>
#include <stddef.h>

extern int UnpackMapFileData(unsigned char *input, unsigned char *output, int len);

typedef struct {
    const char *name;
    const unsigned char *payload;
    unsigned int compressed;
    const unsigned char *expected;
    unsigned int decoded;
} V45Case;

static unsigned long long fnv64(const unsigned char *p, unsigned int n) {
    unsigned long long h = 1469598103934665603ull;
    unsigned int i;
    for (i=0; i<n; i++) {
        h ^= p[i];
        h *= 1099511628211ull;
    }
    return h;
}

static const unsigned char literal[] = {0x00, 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'};
static const unsigned char literal_out[] = {'A','B','C','D','E','F','G','H'};
static const unsigned char absolute[] = {0x01, 0x00, 0x00};
static const unsigned char relative[] = {0x01, 0x80};
static const unsigned char zeros3[] = {0,0,0};
static const unsigned char zeros2[] = {0,0};
static const unsigned char run8[] = {0x01, 0xc0, 'a','b','c','d','e','f','g','h'};
static const unsigned char run8_out[] = {'a','b','c','d','e','f','g','h'};
static const unsigned char rel_overlap[] = {0x02, 'A', 0x81};
static const unsigned char rel_overlap_out[] = {'A','A','A'};
static const unsigned char abs_overlap[] = {0x02, 'X', 0x03, 0xde};
static const unsigned char abs_overlap_out[] = {'X','X','X','X'};

static const V45Case cases[] = {
    {"literal", literal, sizeof(literal), literal_out, sizeof(literal_out)},
    {"absolute", absolute, sizeof(absolute), zeros3, sizeof(zeros3)},
    {"relative", relative, sizeof(relative), zeros2, sizeof(zeros2)},
    {"literal_run", run8, sizeof(run8), run8_out, sizeof(run8_out)},
    {"relative_overlap", rel_overlap, sizeof(rel_overlap), rel_overlap_out, sizeof(rel_overlap_out)},
    {"absolute_overlap", abs_overlap, sizeof(abs_overlap), abs_overlap_out, sizeof(abs_overlap_out)}
};

int main(void) {
    unsigned int n;
    for (n = 0; n < sizeof(cases)/sizeof(cases[0]); n++) {
        const V45Case *t = &cases[n];
        unsigned char input[256], out[256];
        int got, i;
        /* Production decoder performs one last read past declared compressed
         * length, so the synthetic fixture is padded with safe zero memory. */
        memset(input, 0, sizeof(input));
        memset(out, 0x5a, sizeof(out));
        memcpy(input, t->payload, t->compressed);
        got = UnpackMapFileData(input, out, (int)t->compressed);
        if (got != (int)t->decoded ||
            memcmp(out, t->expected, t->decoded) != 0) {
            fprintf(stderr, "[v45-native] FAIL %s got=%d expected=%u\n",
                    t->name, got, t->decoded);
            return 1;
        }
        for (i=(int)t->decoded; i<(int)sizeof(out); i++)
            if (out[i] != 0x5a) {
                fprintf(stderr, "[v45-native] FAIL output-canary %s\n", t->name);
                return 1;
            }
        printf("NATIVE_TOKEN %s %u %016llx\n",
               t->name, t->decoded, fnv64(out, t->decoded));
    }
    puts("PASS upstream original decompressor six independent token families");
    return 0;
}
