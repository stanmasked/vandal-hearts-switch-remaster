#ifndef VH115_SAMPLE_IDENTITY_H
#define VH115_SAMPLE_IDENTITY_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define VH115_SAMPLED_POINTS 24u
typedef struct {
    uint32_t handlers;
    uint32_t vblank_edges;
    uint32_t equal_delta_identical_24_values;
    uint32_t equal_delta_different_24_values;
    uint32_t different_delta_counts;
    uint32_t cross_vblank_equal_delta_identical;
    uint32_t cross_vblank_equal_delta_different;
    uint32_t cross_vblank_different_delta;
} vh115_metrics;
void vh115_reset(void);
void vh115_enable(int enabled);
void vh115_vblank(void);
void vh115_note(const uint16_t *post_values,uint32_t count,uint32_t changed_sample_count);
int vh115_get_metrics(vh115_metrics *out);
int vh115_sample_cache_erased(void);
#ifdef __cplusplus
}
#endif
#endif
