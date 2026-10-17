#include "vh80_native_timeline.h"
#define VH80_CAPACITY 4096u
static vh80_event ring[VH80_CAPACITY];
static unsigned int count, dropped, sequence;
static int vh84_sampling;
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

void vh80_reset(void) { count=0;dropped=0;sequence=0;vh84_sampling=0;vh85_reset_command(); }
void vh84_set_sampling(int enabled) { vh84_sampling=!!enabled; }
int vh84_sampling_enabled(void) { return vh84_sampling; }
void vh80_record(uint32_t kind,uint32_t value,uint32_t cycle,uint32_t frame) {
    if(kind<VH80_VBLANK || kind>VH85_UNAI_SAME_STORE_COUNT) { dropped++;return; }
    if(count>=VH80_CAPACITY || sequence==UINT32_MAX) { dropped++;return; }
    vh80_event *e=&ring[count++];
    e->sequence=++sequence;e->kind=kind;e->value=value;
    e->cycle=cycle;e->frame=frame;
}
unsigned int vh80_count(void) { return count; }
unsigned int vh80_dropped(void) { return dropped; }
const vh80_event *vh80_events(void) { return ring; }
