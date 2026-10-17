#include "vh115_sample_identity.h"
#include <limits.h>
#include <stddef.h>
#include <string.h>

/* Opt-in, process-local equality witness: no values or hashes are exported. */
static struct {
    uint16_t previous[VH115_SAMPLED_POINTS];
    uint32_t previous_delta,previous_epoch,epoch,have_previous;
    uint32_t enabled,invalid;
    vh115_metrics counts;
    vh116_gap_metrics gap_counts;
} state;

static void erase(void *ptr,size_t length){
    volatile unsigned char *p=(volatile unsigned char *)ptr;
    while(length--)*p++=0;
}
void vh115_reset(void){erase(&state,sizeof(state));}
void vh115_enable(int enabled){
    /* Never enable on a dirty or already observed sample cache. */
    if(enabled && (state.have_previous || state.counts.handlers))
        {state.invalid=1;return;}
    state.enabled=!!enabled;
}
void vh115_vblank(void){
    if(!state.enabled || state.invalid)return;
    if(state.epoch==VH116_MAX_VBLANK_GAP ||
       state.counts.vblank_edges==UINT32_MAX){
        state.invalid=1;return;
    }
    state.epoch++;
    state.counts.vblank_edges++;
}
void vh115_note(const uint16_t *post,uint32_t count,uint32_t delta){
    if(!state.enabled || state.invalid)return;
    if(!post || count!=VH115_SAMPLED_POINTS || delta>VH115_SAMPLED_POINTS ||
       state.counts.handlers==UINT32_MAX){
        state.invalid=1;return;
    }
    if(state.have_previous){
        if(state.epoch<state.previous_epoch ||
           state.epoch-state.previous_epoch>VH116_MAX_VBLANK_GAP){
            state.invalid=1;return;
        }
        const uint32_t gap=state.epoch-state.previous_epoch;
        uint32_t crossed=gap!=0;
        uint32_t identical=1;
        for(uint32_t i=0;i<VH115_SAMPLED_POINTS;i++){
            identical&=(uint32_t)(state.previous[i]==post[i]);
        }
        uint32_t *counter;
        uint32_t *cross_counter;
        uint32_t *gap_counter;
        if(state.previous_delta!=delta){
            counter=&state.counts.different_delta_counts;
            cross_counter=&state.counts.cross_vblank_different_delta;
            gap_counter=&state.gap_counts.different_count[gap];
        }else if(identical){
            counter=&state.counts.equal_delta_identical_24_values;
            cross_counter=&state.counts.cross_vblank_equal_delta_identical;
            gap_counter=&state.gap_counts.equal_count_identical[gap];
        }else{
            counter=&state.counts.equal_delta_different_24_values;
            cross_counter=&state.counts.cross_vblank_equal_delta_different;
            gap_counter=&state.gap_counts.equal_count_different[gap];
        }
        if(*counter==UINT32_MAX || *gap_counter==UINT32_MAX ||
           (crossed && *cross_counter==UINT32_MAX)){
            state.invalid=1;return;
        }
        ++*counter;
        ++*gap_counter;
        if(crossed)++*cross_counter;
    }
    memcpy(state.previous,post,sizeof(state.previous));
    state.previous_delta=delta;
    state.previous_epoch=state.epoch;
    state.have_previous=1;
    state.counts.handlers++;
}
int vh115_get_metrics(vh115_metrics *out){
    if(!out || !state.enabled || state.invalid || !state.have_previous ||
       state.counts.handlers==0)return -1;
    const vh115_metrics *m=&state.counts;
    if(m->equal_delta_identical_24_values+
       m->equal_delta_different_24_values+
       m->different_delta_counts != m->handlers-1 ||
       m->cross_vblank_equal_delta_identical>m->equal_delta_identical_24_values ||
       m->cross_vblank_equal_delta_different>m->equal_delta_different_24_values ||
       m->cross_vblank_different_delta>m->different_delta_counts)return -1;
    *out=*m;
    return 0;
}
int vh116_get_gap_metrics(vh116_gap_metrics *out){
    vh115_metrics old;
    if(!out || vh115_get_metrics(&old)!=0 ||
       old.vblank_edges>VH116_MAX_VBLANK_GAP)return -1;
    uint64_t exact=0,different=0,changed=0;
    uint64_t cross_exact=0,cross_different=0,cross_changed=0;
    for(unsigned int gap=0;gap<=VH116_MAX_VBLANK_GAP;gap++){
        const uint32_t a=state.gap_counts.equal_count_identical[gap];
        const uint32_t b=state.gap_counts.equal_count_different[gap];
        const uint32_t c=state.gap_counts.different_count[gap];
        exact+=a;different+=b;changed+=c;
        if(gap){
            cross_exact+=a;cross_different+=b;cross_changed+=c;
        }
    }
    if(exact!=old.equal_delta_identical_24_values ||
       different!=old.equal_delta_different_24_values ||
       changed!=old.different_delta_counts ||
       cross_exact!=old.cross_vblank_equal_delta_identical ||
       cross_different!=old.cross_vblank_equal_delta_different ||
       cross_changed!=old.cross_vblank_different_delta ||
       exact+different+changed!=old.handlers-1u)return -1;
    *out=state.gap_counts;
    return 0;
}
int vh115_sample_cache_erased(void){
    const unsigned char *p=(const unsigned char *)state.previous;
    for(size_t i=0;i<sizeof(state.previous);i++)if(p[i])return 0;
    return 1;
}
