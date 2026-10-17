#include "vh80_native_timeline.h"
#define VH80_CAPACITY 4096u
static vh80_event ring[VH80_CAPACITY];
static unsigned int count, dropped, sequence;
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

void vh80_reset(void) { count=0;dropped=0;sequence=0;vh84_sampling=0;vh85_reset_command();vh86_reset(); }
void vh84_set_sampling(int enabled) { vh84_sampling=!!enabled; }
int vh84_sampling_enabled(void) { return vh84_sampling; }
void vh80_record(uint32_t kind,uint32_t value,uint32_t cycle,uint32_t frame) {
    if(kind<VH80_VBLANK || kind>VH92_SYNC_SAME) { dropped++;return; }
    if(count>=VH80_CAPACITY || sequence==UINT32_MAX) { dropped++;return; }
    vh80_event *e=&ring[count++];
    e->sequence=++sequence;e->kind=kind;e->value=value;
    e->cycle=cycle;e->frame=frame;
}
unsigned int vh80_count(void) { return count; }
unsigned int vh80_dropped(void) { return dropped; }
const vh80_event *vh80_events(void) { return ring; }
