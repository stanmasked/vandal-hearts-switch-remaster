/* Generated-only host regression: same exact source as libnx NeXium guest. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_guest_sync_studio_c.h"
#include "vh_audio_stream.h"
static uint32_t crc32(const uint8_t *buf,unsigned count) {
    uint32_t crc=UINT32_C(0xffffffff);
    for(unsigned i=0;i<count;i++) {
        crc^=buf[i];
        for(unsigned j=0;j<8;j++)
            crc=(crc>>1)^((crc&1u)?UINT32_C(0xedb88320):0u);
    }
    return crc^UINT32_C(0xffffffff);
}
static uint32_t le32(const uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|
           ((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
int main(void) {
    VhGuestSyncStudioC a,b;
    uint8_t packet[924];
    assert(vh_guest_sync_studio_c_run(&a)==0);
    assert(vh_guest_sync_studio_c_run(&b)==0);
    assert(a.failure_line==0 && b.failure_line==0);
    assert(a.verified_roundtrips==2 && b.verified_roundtrips==2);
    assert(a.pre_blocks==64 && a.post_blocks==48);
    assert(a.different_blocks==48 && a.wet_nonzero>0 && a.reset_nonzero==0);
    assert(a.pre_note_ons==1 && a.next_note_ons==0);
    assert(a.initial_hash==b.initial_hash && a.wet_hash==b.wet_hash &&
           a.reset_hash==b.reset_hash && a.wet_nonzero==b.wet_nonzero);
    assert(a.wet_hash!=a.reset_hash);
    assert(a.native48.different_pages==48);
    assert(a.native48.prefix_frames==35665u);
    assert(a.native48.tail_frames==26750u);
    assert(a.native48.wet_nonzero>0u);
    assert(a.native48.reset_first_page_nonzero<=2u);
    assert(a.native48.reset_later_nonzero==0u);
    assert(a.native48.verified_roundtrips==2u);
    assert(a.native48.prefix_hash==b.native48.prefix_hash);
    assert(a.native48.wet_hash==b.native48.wet_hash);
    assert(a.native48.reset_hash==b.native48.reset_hash);
    assert(a.native48.wet_hash!=a.native48.reset_hash);
    assert(vh_guest_native_48k_encode(&a,packet)==0);
    assert(!memcmp(packet,"VH48K001",8));
    assert(packet[8]==1u && packet[9]==0u && packet[10]==15u);
    assert(le32(packet+20)==48u);
    assert(le32(packet+32)==0u);
    assert(le32(packet+909)==crc32(packet,909u));
    assert(vh_guest_sync_studio_c_encode(&a,packet)==0);
    assert(memcmp(packet,"VHSYNC01",8)==0);
    assert(packet[8]==1u && packet[9]==0u && packet[10]==15u);
    assert(le32(packet+12)==64u && le32(packet+16)==48u);
    assert(le32(packet+20)==48u && le32(packet+24)==a.wet_nonzero);
    assert(le32(packet+28)==0u && le32(packet+64)==2u);
    assert(le32(packet+909)==crc32(packet,909u));
    /* Negative sequential-page cases use generated silence only. The
     * recorder must fail before consuming resampler state on invalid order. */
    {
        static const int16_t quiet[VH_AUDIO_BLOCK_FRAMES*2u]={0};
        VhGuestNative48k probe;
        vh_guest_native_48k_init(&probe);
        assert(vh_guest_native_48k_observe(&probe,quiet,quiet,0u,1u)==-1);
        assert(vh_guest_native_48k_observe(&probe,quiet,quiet,1u,0u)==-1);
        assert(vh_guest_native_48k_observe(&probe,quiet,quiet,0u,64u)==-1);
        assert(vh_guest_native_48k_observe(&probe,quiet,quiet,1u,48u)==-1);
        assert(vh_guest_native_48k_observe(&probe,quiet,quiet,0u,0u)==0);
        assert(probe.prefix_frames==557u);
        assert(vh_guest_native_48k_observe(&probe,quiet,quiet,0u,0u)==-1);
        assert(vh_guest_native_48k_observe(&probe,quiet,quiet,0u,2u)==-1);
        assert(vh_guest_native_48k_observe(&probe,quiet,quiet,0u,1u)==0);
        assert(probe.prefix_frames==1114u);
    }
    puts("PASS: sequential native 48k pages reject skipped, duplicated and early tail indices");
    puts("PASS: synchronized guest DSP replay: 64 identical prefix, 48/48 different tail blocks, 0 reset samples");
    printf("initial=%016llx wet=%016llx reset=%016llx wet_nonzero=%u\n",
           (unsigned long long)a.initial_hash,
           (unsigned long long)a.wet_hash,
           (unsigned long long)a.reset_hash,a.wet_nonzero);
    printf("native48 pre=%016llx wet=%016llx reset=%016llx prefix_frames=%u tail_frames=%u different_pages=%u wet_nonzero=%u reset_first=%u reset_later=%u\n",
           (unsigned long long)a.native48.prefix_hash,
           (unsigned long long)a.native48.wet_hash,
           (unsigned long long)a.native48.reset_hash,
           a.native48.prefix_frames,a.native48.tail_frames,
           a.native48.different_pages,a.native48.wet_nonzero,
           a.native48.reset_first_page_nonzero,
           a.native48.reset_later_nonzero);
    return 0;
}
