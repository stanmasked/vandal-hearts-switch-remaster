#include "map02_cd_read_probe.h"
#include "map02_capture_session.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Standalone SHA-256 for the bounded MAP02 user-data stream. No external
 * crypto/SDK dependency; no original game bytes leave the process. */
typedef struct {
    uint32_t h[8];
    uint64_t bytes;
    unsigned char block[64];
    size_t used;
} Map02Sha256;

static const uint32_t sha_k[64] = {
    0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
    0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
    0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
    0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
    0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
    0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
    0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
    0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u
};

static uint32_t sha_ror(uint32_t x, unsigned n) {
    return (x >> n) | (x << (32u - n));
}
static void sha_init(Map02Sha256 *s) {
    static const uint32_t init[8] = {
        0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,
        0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u
    };
    size_t i;
    for (i = 0; i < 8; ++i) s->h[i] = init[i];
    s->bytes = 0;
    s->used = 0;
}
static void sha_compress(Map02Sha256 *s) {
    uint32_t w[64], a,b,c,d,e,f,g,h;
    unsigned i;
    for (i=0; i<16; ++i) {
        const unsigned char *p = s->block + i*4;
        w[i] = ((uint32_t)p[0]<<24) | ((uint32_t)p[1]<<16) |
               ((uint32_t)p[2]<<8) | (uint32_t)p[3];
    }
    for (i=16; i<64; ++i) {
        uint32_t x=w[i-15], y=w[i-2];
        w[i] = w[i-16] + (sha_ror(x,7)^sha_ror(x,18)^(x>>3)) +
                w[i-7] + (sha_ror(y,17)^sha_ror(y,19)^(y>>10));
    }
    a=s->h[0]; b=s->h[1]; c=s->h[2]; d=s->h[3];
    e=s->h[4]; f=s->h[5]; g=s->h[6]; h=s->h[7];
    for (i=0; i<64; ++i) {
        uint32_t ch=(e&f)^(~e&g), maj=(a&b)^(a&c)^(b&c);
        uint32_t t1=h+(sha_ror(e,6)^sha_ror(e,11)^sha_ror(e,25))+
                    ch+sha_k[i]+w[i];
        uint32_t t2=(sha_ror(a,2)^sha_ror(a,13)^sha_ror(a,22))+maj;
        h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
    }
    s->h[0]+=a;s->h[1]+=b;s->h[2]+=c;s->h[3]+=d;
    s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;
}
static void sha_update(Map02Sha256 *s, const unsigned char *p, size_t n) {
    size_t i;
    s->bytes += n;
    for (i=0; i<n; ++i) {
        s->block[s->used++] = p[i];
        if (s->used == 64) { sha_compress(s); s->used=0; }
    }
}
static void sha_finish(Map02Sha256 *s, unsigned char out[32]) {
    unsigned char b=0x80u, zero=0;
    unsigned char length[8];
    uint64_t bits=s->bytes*8u;
    unsigned i;
    for (i=0; i<8; ++i) length[7-i]=(unsigned char)(bits>>(i*8));
    sha_update(s,&b,1);
    while (s->used != 56) sha_update(s,&zero,1);
    sha_update(s,length,8);
    for (i=0; i<8; ++i) {
        out[i*4]=(unsigned char)(s->h[i]>>24);
        out[i*4+1]=(unsigned char)(s->h[i]>>16);
        out[i*4+2]=(unsigned char)(s->h[i]>>8);
        out[i*4+3]=(unsigned char)s->h[i];
    }
}
static void sha_hex(const unsigned char digest[32], char out[65]) {
    static const char chars[]="0123456789abcdef";
    unsigned i;
    for (i=0; i<32; ++i) {
        out[2*i]=chars[digest[i]>>4];
        out[2*i+1]=chars[digest[i]&15u];
    }
    out[64]=0;
}

#define MAP02_LBA 0x1bcc
#define MAP02_SECTORS 12
#define USER_SECTOR 2048

/* Intentionally no raw game bytes or addresses in global storage. */
static struct {
    unsigned claimed, started, finished, completed, count, failed;
    unsigned raw_crc, transferred_crc;
    Map02Sha256 raw_sha_stream;
    unsigned char raw_sha256[32], transferred_sha256[32];
    int observing, hashes_ready;
} state;

static int overlaps_map02_extent(int lba, int sectors) {
    int64_t start = (int64_t)lba;
    int64_t end = start + (int64_t)sectors;
    return sectors > 0 && end > MAP02_LBA &&
           start < MAP02_LBA + MAP02_SECTORS;
}

static uint32_t crc32_append(uint32_t crc, const unsigned char *data,
                             size_t size) {
    size_t i;
    for (i = 0; i < size; i++) {
        unsigned bit;
        crc ^= data[i];
        for (bit = 0; bit < 8; bit++)
            crc = (crc >> 1) ^ ((crc & 1u) ? 0xedb88320u : 0u);
    }
    return crc;
}

void vh_map02_cd_loader_claim(int cdf, int target_cdf, int lba, int sectors) {
    if (cdf != target_cdf) return;
    if (state.claimed++ || lba != MAP02_LBA || sectors != MAP02_SECTORS)
        state.failed = 1;
}

void vh_map02_cd_read_start(int lba, int sectors) {
    if (!overlaps_map02_extent(lba, sectors)) return;
    if (!state.claimed || state.started++ || lba != MAP02_LBA ||
            sectors != MAP02_SECTORS || state.finished)
        state.failed = 1;
    state.observing = 1;
    state.raw_crc = 0xffffffffu;
    state.hashes_ready = 0;
    sha_init(&state.raw_sha_stream);
}

void vh_map02_cd_read_sector(int lba, const unsigned char *user2048) {
    if (!state.observing) {
        /* A real MAP02 sector callback outside its one authorized read
         * cannot silently disappear from the source-process audit. Ordinary
         * unrelated CD sectors may still be observed and ignored. */
        if (lba >= MAP02_LBA && lba < MAP02_LBA + MAP02_SECTORS)
            state.failed = 1;
        return;
    }
    if (!user2048 || lba != MAP02_LBA + (int)state.count ||
            state.count >= MAP02_SECTORS) {
        state.failed = 1;
        return;
    }
    state.raw_crc = crc32_append(state.raw_crc, user2048, USER_SECTOR);
    sha_update(&state.raw_sha_stream, user2048, USER_SECTOR);
    state.count++;
}

void vh_map02_cd_read_finish(int lba, int sectors,
                             const unsigned char *transferred) {
    if (!state.observing) {
        /* Reject orphaned or duplicate MAP02 read completion events.
         * A later/earlier read for an unrelated extent remains irrelevant. */
        if (overlaps_map02_extent(lba, sectors))
            state.failed = 1;
        return;
    }
    /* Validate the original CdRead's full span BEFORE examining any bytes.
     * A malformed/short caller buffer must never be blindly treated as
     * 12 * 2048 accessible bytes. This observer is diagnostic, so a failed
     * read must not introduce an out-of-bounds access of its own. */
    if (lba != MAP02_LBA || sectors != MAP02_SECTORS ||
            state.count != MAP02_SECTORS || !transferred || state.finished++) {
        state.failed = 1;
        state.observing = 0;
        return;
    }
    state.transferred_crc = crc32_append(
        0xffffffffu, transferred, MAP02_SECTORS * USER_SECTOR);
    {
        Map02Sha256 copied;
        sha_finish(&state.raw_sha_stream, state.raw_sha256);
        sha_init(&copied);
        sha_update(&copied, transferred, MAP02_SECTORS * USER_SECTOR);
        sha_finish(&copied, state.transferred_sha256);
        state.hashes_ready = 1;
    }
    /* Original game material must not be silently modified by
     * PC_LangPatchRead or a translation pack for source comparison. */
    if (state.transferred_crc != state.raw_crc ||
            memcmp(state.transferred_sha256, state.raw_sha256, 32) != 0)
        state.failed = 1;
    state.observing = 0;
}

void vh_map02_cd_loader_complete(int cdf, int target_cdf, int state_after) {
    if (cdf != target_cdf) return;
    if (state_after != 99 || state.completed++ || state.claimed != 1 ||
            state.started != 1 || state.finished != 1 ||
            state.count != MAP02_SECTORS)
        state.failed = 1;
}

int vh_map02_cd_probe_failed(void) {
    return (int)state.failed;
}

int vh_map02_cd_probe_raw_crc32(unsigned *out) {
    if (!out || state.failed || state.claimed != 1 || state.started != 1 ||
        state.finished != 1 || state.completed != 1 ||
        state.count != MAP02_SECTORS || !state.hashes_ready ||
        state.raw_crc != state.transferred_crc ||
        memcmp(state.raw_sha256, state.transferred_sha256, 32) != 0)
        return 0;
    *out = state.raw_crc ^ 0xffffffffu;
    return 1;
}

int vh_map02_cd_probe_format_jsonl(char *out, size_t capacity) {
    const char *session;
    char raw_sha[65], copied_sha[65];
    int n;
    if (state.failed || state.claimed != 1 || state.started != 1 ||
            state.finished != 1 || state.completed != 1 ||
            state.count != MAP02_SECTORS || !state.hashes_ready ||
            !out || !capacity)
        return 0;
    session = vh_map02_capture_session_token();
    if (!session) return 0;
    sha_hex(state.raw_sha256, raw_sha);
    sha_hex(state.transferred_sha256, copied_sha);
    n = snprintf(out, capacity,
        "{\"schema\":\"vh.map02.original-cd-read.v2\","
        "\"capture_session\":\"%s\","
        "\"source\":\"original-CdRead-and-ContinueLoadingCdFile\","
        "\"cdf\":\"CDF_M_MAP02_PRS\","
        "\"lba\":%d,\"sectors\":%d,\"bytes\":%d,"
        "\"raw_user_crc32\":\"%08x\",\"returned_user_crc32\":\"%08x\","
        "\"raw_user_sha256\":\"%s\",\"returned_user_sha256\":\"%s\","
        "\"loader_completed\":true}\n",
        session, MAP02_LBA, MAP02_SECTORS,
        MAP02_SECTORS * USER_SECTOR,
        (unsigned)(state.raw_crc ^ 0xffffffffu),
        (unsigned)(state.transferred_crc ^ 0xffffffffu),
        raw_sha, copied_sha);
    if (n <= 0 || (size_t)n >= capacity) return 0;
    return n;
}
