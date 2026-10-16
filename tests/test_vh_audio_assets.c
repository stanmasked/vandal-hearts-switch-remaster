/* Read-only local SEQ/VH/VB loader regression, synthetic resources only. */
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "vh_audio_assets.h"

static uint8_t vh[32u + 128u * 16u + 512u + 512u];
static uint8_t vb[48];
static const uint8_t seq[] = {
    'p','Q','E','S',0,0,0,0, 0x01,0xe0,0x07,0xa1,0x20,0,0,
    0,0xc0,7, 0,0xb0,7,127, 0,0xb0,10,64,
    0,0x90,60,110, 0x81,0x70,0x80,60,0,
    0x81,0x70,0xff,0x2f
};
static char dir_template[] = "/tmp/vh-audio-assets-XXXXXX";
static char path[512];

static void w16(uint8_t *dst, size_t off, unsigned x) {
    dst[off] = (uint8_t)x;
    dst[off + 1u] = (uint8_t)(x >> 8);
}

static void fixture(void) {
    memset(vh, 0, sizeof vh);
    memset(vb, 0, sizeof vb);
    memcpy(vh, "pBAV", 4);
    w16(vh, 18, 8);
    w16(vh, 20, 1);
    w16(vh, 22, 1);
    vh[24] = 127;
    const size_t program = 32u + 7u * 16u;
    vh[program] = 1;
    vh[program + 1] = 127;
    vh[program + 4] = 64;
    const size_t tone = 32u + 128u * 16u;
    vh[tone + 2] = 127;
    vh[tone + 3] = 64;
    vh[tone + 4] = 60;
    vh[tone + 6] = 40;
    vh[tone + 7] = 100;
    w16(vh, tone + 16, 15);
    w16(vh, tone + 20, 7);
    w16(vh, tone + 22, 1);
    const size_t sizes = tone + 512u;
    w16(vh, sizes, 2); /* leading 16 bytes of VB */
    w16(vh, sizes + 2, 4); /* 2 ADPCM blocks */
    vb[16] = 2; vb[17] = 4;
    vb[32] = 2; vb[33] = 3;
    for (size_t i = 18; i < 32; ++i) vb[i] = 0x22;
    for (size_t i = 34; i < 48; ++i) vb[i] = 0xee;
}

static void save(const char *filename, const uint8_t *bytes, size_t size) {
    assert(snprintf(path, sizeof path, "%s/%s",
                    dir_template, filename) > 0);
    FILE *f = fopen(path, "wb");
    assert(f);
    assert(fwrite(bytes, 1, size, f) == size);
    assert(fclose(f) == 0);
}
static void delete_file(const char *filename) {
    assert(snprintf(path, sizeof path, "%s/%s",
                    dir_template, filename) > 0);
    assert(unlink(path) == 0);
}
static void put_sources(void) {
    save(VH_AUDIO_ASSET_SEQ_FILENAME, seq, sizeof seq);
    save(VH_AUDIO_ASSET_VH_FILENAME, vh, sizeof vh);
    save(VH_AUDIO_ASSET_VB_FILENAME, vb, sizeof vb);
}
static void remove_sources(void) {
    delete_file(VH_AUDIO_ASSET_SEQ_FILENAME);
    delete_file(VH_AUDIO_ASSET_VH_FILENAME);
    delete_file(VH_AUDIO_ASSET_VB_FILENAME);
}
static void check_file(const char *filename, const uint8_t *expected,
                       size_t size) {
    assert(snprintf(path, sizeof path, "%s/%s",
                    dir_template, filename) > 0);
    FILE *f = fopen(path, "rb");
    assert(f);
    uint8_t *copy = malloc(size);
    assert(copy);
    assert(fread(copy, 1, size, f) == size);
    assert(fgetc(f) == EOF);
    assert(!memcmp(copy, expected, size));
    assert(fclose(f) == 0);
    free(copy);
}

static void test_all_or_nothing_and_readonly(void) {
    VhAudioAssets assets = {0};
    assert(vh_audio_assets_load(&assets, dir_template) ==
           VH_AUDIO_ASSET_MISSING);
    assert(!assets.seq && !assets.pcm);
    save(VH_AUDIO_ASSET_SEQ_FILENAME, seq, sizeof seq);
    assert(vh_audio_assets_load(&assets, dir_template) ==
           VH_AUDIO_ASSET_ERROR); /* partial files may not be ignored */
    assert(!assets.seq && !assets.pcm);
    delete_file(VH_AUDIO_ASSET_SEQ_FILENAME);
    fixture();
    put_sources();
    assert(vh_audio_assets_load(&assets, dir_template) ==
           VH_AUDIO_ASSET_OK);
    assert(assets.seq_size == sizeof seq && assets.vh_size == sizeof vh);
    assert(assets.vb_size == sizeof vb);
    assert(assets.bank.active && assets.bank.vag_count == 1);
    assert(assets.bank.samples[1].frames == 56);
    assert(assets.bank.samples[1].loop_end == 56);
    assert(assets.bank.samples[1].pcm == assets.pcm);
    assert(assets.bank.samples[1].pcm[0] == 2048);
    assert(assets.bank.samples[1].pcm[28] == -2048);
    assert(assets.bank.required_pcm_frames == 56);
    assert(assets.pcm_capacity == 84); /* 48 VB bytes / 16 * 28 */
    check_file(VH_AUDIO_ASSET_SEQ_FILENAME, seq, sizeof seq);
    check_file(VH_AUDIO_ASSET_VH_FILENAME, vh, sizeof vh);
    check_file(VH_AUDIO_ASSET_VB_FILENAME, vb, sizeof vb);
    assert(vh_audio_assets_load(&assets, dir_template) ==
           VH_AUDIO_ASSET_ERROR); /* don't overwrite active playback */
    vh_audio_assets_close(&assets);
    vh_audio_assets_close(&assets);
    assert(!assets.seq && !assets.pcm);
    remove_sources();
}

static void test_reject_bad_seq_and_vh_vb(void) {
    VhAudioAssets assets = {0};
    fixture();
    put_sources();
    uint8_t broken_seq[sizeof seq];
    memcpy(broken_seq, seq, sizeof seq);
    broken_seq[0] = 'X';
    save(VH_AUDIO_ASSET_SEQ_FILENAME, broken_seq, sizeof broken_seq);
    assert(vh_audio_assets_load(&assets, dir_template) ==
           VH_AUDIO_ASSET_ERROR);
    assert(!assets.seq && !assets.pcm);
    save(VH_AUDIO_ASSET_SEQ_FILENAME, seq, sizeof seq);
    uint8_t copy_vh[sizeof vh];
    memcpy(copy_vh, vh, sizeof vh);
    copy_vh[0] = 'X';
    save(VH_AUDIO_ASSET_VH_FILENAME, copy_vh, sizeof copy_vh);
    assert(vh_audio_assets_load(&assets, dir_template) ==
           VH_AUDIO_ASSET_ERROR);
    save(VH_AUDIO_ASSET_VH_FILENAME, vh, sizeof vh);
    uint8_t copy_vb[sizeof vb];
    memcpy(copy_vb, vb, sizeof vb);
    copy_vb[16] = 0x50; /* invalid ADPCM filter */
    save(VH_AUDIO_ASSET_VB_FILENAME, copy_vb, sizeof copy_vb);
    assert(vh_audio_assets_load(&assets, dir_template) ==
           VH_AUDIO_ASSET_ERROR);
    assert(!assets.seq && !assets.pcm);
    save(VH_AUDIO_ASSET_VB_FILENAME, vb, sizeof vb);
    remove_sources();
}

static void test_size_limits_and_path_guard(void) {
    VhAudioAssets assets = {0};
    fixture();
    put_sources();
    assert(snprintf(path, sizeof path, "%s/%s", dir_template,
                    VH_AUDIO_ASSET_SEQ_FILENAME) > 0);
    FILE *f = fopen(path, "wb");
    assert(f);
    assert(fseek(f, (long)VH_AUDIO_ASSET_MAX_SEQ_BYTES, SEEK_SET) == 0);
    assert(fputc(0, f) != EOF);
    assert(fclose(f) == 0);
    assert(vh_audio_assets_load(&assets, dir_template) ==
           VH_AUDIO_ASSET_ERROR);
    save(VH_AUDIO_ASSET_SEQ_FILENAME, seq, sizeof seq);
    char too_long[VH_AUDIO_ASSET_MAX_PATH + 100u];
    memset(too_long, 'x', sizeof too_long - 1u);
    too_long[sizeof too_long - 1u] = '\0';
    assert(vh_audio_assets_load(&assets, too_long) ==
           VH_AUDIO_ASSET_ERROR);
    assert(!assets.seq && !assets.pcm);
    remove_sources();
}

int main(void) {
    assert(mkdtemp(dir_template) != NULL);
    test_all_or_nothing_and_readonly();
    test_reject_bad_seq_and_vh_vb();
    test_size_limits_and_path_guard();
    assert(rmdir(dir_template) == 0);
    puts("read-only local SEQ/VH/VB assets: PASS (synthetic)");
    return 0;
}
