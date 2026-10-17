#include "vh80_native_timeline.h"
#define VH80_CAPACITY 4096u
static vh80_event ring[VH80_CAPACITY];
static unsigned int count, dropped, sequence;
static int vh84_sampling;
void vh80_reset(void) { count=0;dropped=0;sequence=0;vh84_sampling=0; }
void vh84_set_sampling(int enabled) { vh84_sampling=!!enabled; }
int vh84_sampling_enabled(void) { return vh84_sampling; }
void vh80_record(uint32_t kind,uint32_t value,uint32_t cycle,uint32_t frame) {
    if(kind<VH80_VBLANK || kind>VH84_UNAI_SAMPLE_DELTA) { dropped++;return; }
    if(count>=VH80_CAPACITY || sequence==UINT32_MAX) { dropped++;return; }
    vh80_event *e=&ring[count++];
    e->sequence=++sequence;e->kind=kind;e->value=value;
    e->cycle=cycle;e->frame=frame;
}
unsigned int vh80_count(void) { return count; }
unsigned int vh80_dropped(void) { return dropped; }
const vh80_event *vh80_events(void) { return ring; }
