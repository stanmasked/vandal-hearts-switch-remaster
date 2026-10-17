#include "vh80_native_timeline.h"
#define VH80_CAPACITY 4096u
#if VH80_CAPACITY != VH80_CAPACITY_DETAIL
#error "legacy v80 detailed lane must remain exactly 4096 entries"
#endif
static vh80_event ring[VH80_CAPACITY];
static vh80_event aggregate[VH80_CAPACITY_AGGREGATE];
/* Reconstruct globally ordered, contiguous seq at immutable export time. */
static vh80_event ordered[VH80_TOTAL_CAPACITY];
static unsigned int count, aggregate_count, dropped, sequence;
static int vh84_sampling;
static uint32_t vh86_stores[3],vh86_same[3],vh86_overflow;
void vh86_reset(void){
  for(unsigned int i=0;i<3;i++){vh86_stores[i]=0;vh86_same[i]=0;}
  vh86_overflow=0;
}
void vh86_note_store(uint32_t source,uint32_t old_value,uint32_t new_value){
  if(!vh84_sampling || vh86_overflow)return;
  if(source!=VH86_A0_UPLOAD && source!=VH86_VRAM_COPY){vh86_overflow=1;return;}
  if(vh86_stores[source]==UINT32_MAX ||
     (old_value==new_value && vh86_same[source]==UINT32_MAX)){
    vh86_overflow=1;return;
  }
  vh86_stores[source]++;
  if((uint16_t)old_value==(uint16_t)new_value)vh86_same[source]++;
}
uint32_t vh86_store_count(uint32_t source){return source<3?vh86_stores[source]:0;}
uint32_t vh86_same_store_count(uint32_t source){return source<3?vh86_same[source]:0;}
uint32_t vh86_write_overflow(void){return vh86_overflow;}

static unsigned int vh85_stores,vh85_same,vh85_overflow;
void vh85_reset_command(void) { vh85_stores=vh85_same=vh85_overflow=0; }
void vh85_note_store(uint32_t before,uint32_t after) {
    if(!vh84_sampling || vh85_overflow)return;
    if(vh85_stores==UINT32_MAX || (before==after && vh85_same==UINT32_MAX)) { vh85_overflow=1;return; }
    vh85_stores++;
    if(before==after)vh85_same++;
}
unsigned int vh85_store_count(void){return vh85_stores;}
unsigned int vh85_same_store_count(void){return vh85_same;}
unsigned int vh85_write_overflow(void){return vh85_overflow;}

void vh80_reset(void) { count=0;aggregate_count=0;dropped=0;sequence=0;vh84_sampling=0;vh85_reset_command();vh86_reset(); }
void vh84_set_sampling(int enabled) { vh84_sampling=!!enabled; }
int vh84_sampling_enabled(void) { return vh84_sampling; }
void vh80_record(uint32_t kind,uint32_t value,uint32_t cycle,uint32_t frame) {
    if(kind<VH80_VBLANK || kind>VH93_TOTAL_COUNT) { dropped++;return; }
    if(sequence==UINT32_MAX) { dropped++;return; }
    /* Real per-command evidence (types 1..7) and stage aggregates
     * (types 8..78) are physically independent bounded segments.
     * Overflow is always refused: neither lane may displace the other. */
    vh80_event *e;
    if(kind<VH86_A0_STORES){
        if(count>=VH80_CAPACITY) { dropped++;return; }
        e=&ring[count++];
    }else{
        if(aggregate_count>=VH80_CAPACITY_AGGREGATE) { dropped++;return; }
        e=&aggregate[aggregate_count++];
    }
    e->sequence=++sequence;e->kind=kind;e->value=value;
    e->cycle=cycle;e->frame=frame;
}
unsigned int vh80_count(void) { return count+aggregate_count; }
unsigned int vh80_detailed_count(void) { return count; }
unsigned int vh80_aggregate_count(void) { return aggregate_count; }
unsigned int vh80_dropped(void) { return dropped; }
const vh80_event *vh80_events(void) {
    /* No worker writes to these lanes; caller snapshots after GPUfreeze.
     * Two monotone substreams merge in O(n), preserving the original
     * global sequence, VBlank order and private JSONL verifier ABI. */
    unsigned int i=0,j=0,k=0;
    while(i<count && j<aggregate_count){
        if(ring[i].sequence<aggregate[j].sequence)
            ordered[k++]=ring[i++];
        else
            ordered[k++]=aggregate[j++];
    }
    while(i<count)ordered[k++]=ring[i++];
    while(j<aggregate_count)ordered[k++]=aggregate[j++];
    return ordered;
}
