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
static unsigned int vh94_snapshot_valid,vh94_snapshot_seq;
static unsigned int vh94_merges,vh94_hits,vh94_checks;
static unsigned int vh97_epoch=1;
/* Volatile byte writes erase former private event words from resident storage. */
static void vh97_scrub(void *p,unsigned int n){
  volatile unsigned char *b=(volatile unsigned char *)p;
  while(n--)*b++=0;
}
unsigned int vh97_reset_epoch(void){return vh97_epoch;}
int vh97_buffers_erased(void){
  const unsigned char *blocks[]={
      (const unsigned char *)ring,(const unsigned char *)aggregate,
      (const unsigned char *)ordered};
  const unsigned int sizes[]={sizeof(ring),sizeof(aggregate),sizeof(ordered)};
  for(unsigned int k=0;k<3;k++)
    for(unsigned int i=0;i<sizes[k];i++)
      if(blocks[k][i]!=0)return 0;
  return 1;
}
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

void vh80_reset(void) {
  /* Only safe after draining GPU writers; refuse if epoch saturates. */
  unsigned int exhausted=(vh97_epoch==UINT32_MAX);
  if(!exhausted)vh97_epoch++;
  vh97_scrub(ring,sizeof(ring));
  vh97_scrub(aggregate,sizeof(aggregate));
  vh97_scrub(ordered,sizeof(ordered));
  count=aggregate_count=sequence=0;
  dropped=exhausted;
  vh94_snapshot_valid=vh94_snapshot_seq=vh94_merges=vh94_hits=vh94_checks=0;
  vh84_sampling=0;vh85_reset_command();vh86_reset();
}
void vh84_set_sampling(int enabled) { vh84_sampling=!!enabled; }
int vh84_sampling_enabled(void) { return vh84_sampling; }
void vh80_record(uint32_t kind,uint32_t value,uint32_t cycle,uint32_t frame) {
    if(kind<VH80_VBLANK || kind>VH98_REPLAY_REFUSED) { dropped++;return; }
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
    /* Invalidate snapshot only on a successful event append. An
     * invalid/over-capacity append sets dropped and fails publication. */
    vh94_snapshot_valid=0;
    e->sequence=++sequence;e->kind=kind;e->value=value;
    e->cycle=cycle;e->frame=frame;
}
unsigned int vh80_count(void) { return count+aggregate_count; }
unsigned int vh80_detailed_count(void) { return count; }
unsigned int vh80_aggregate_count(void) { return aggregate_count; }
unsigned int vh80_dropped(void) { return dropped; }
const vh80_event *vh80_events(void) {
    /* No worker writes to these lanes; caller snapshots after GPUfreeze.
     * Read cache hits O(1); first read after each mutation merges O(n). */
    if(vh94_snapshot_valid && vh94_snapshot_seq==sequence){
        vh94_hits++;
        return ordered;
    }
    unsigned int i=0,j=0,k=0;
    while(i<count && j<aggregate_count){
        if(ring[i].sequence<aggregate[j].sequence)
            ordered[k++]=ring[i++];
        else
            ordered[k++]=aggregate[j++];
    }
    while(i<count)ordered[k++]=ring[i++];
    while(j<aggregate_count)ordered[k++]=aggregate[j++];
    vh94_snapshot_seq=sequence;
    vh94_snapshot_valid=1;
    vh94_merges++;
    return ordered;
}

/* Intentionally separate from vh80_events(): validating every read would
 * scan O(n), undoing the constant-time cache benefit. Explicit verification
 * is performed at privacy-export boundaries and opt-in smoke tests. */
unsigned int vh94_merge_runs(void){return vh94_merges;}
unsigned int vh94_cache_hits(void){return vh94_hits;}
unsigned int vh94_verify_runs(void){return vh94_checks;}
int vh94_snapshot_check(void){
    if(!vh94_snapshot_valid || vh94_snapshot_seq!=sequence || dropped!=0)
        return -1;
    unsigned int i=0,j=0,k=0,n=count+aggregate_count;
    while(k<n){
        const vh80_event *source;
        if(i<count && (j>=aggregate_count ||
                        ring[i].sequence<aggregate[j].sequence))
            source=&ring[i++];
        else if(j<aggregate_count)
            source=&aggregate[j++];
        else return -1;
        const vh80_event *cached=&ordered[k];
        /* All five fixed ABI words are checked; snapshot tampering and
         * changes in either source lane are both detected. */
        if(cached->sequence!=source->sequence ||
           cached->kind!=source->kind || cached->value!=source->value ||
           cached->cycle!=source->cycle || cached->frame!=source->frame ||
           cached->sequence!=k+1u) return -1;
        k++;
    }
    if(i!=count || j!=aggregate_count)return -1;
    vh94_checks++;
    return 0;
}
