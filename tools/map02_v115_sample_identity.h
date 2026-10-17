#ifndef VH115_SAMPLE_IDENTITY_H
#define VH115_SAMPLE_IDENTITY_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define VH115_SAMPLED_POINTS 24u
#define VH116_MAX_VBLANK_GAP 4u
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
/* Independent 0..4 VBlank-gap bins; preserves the original v115 ABI. */
typedef struct {
    uint32_t equal_count_identical[VH116_MAX_VBLANK_GAP+1u];
    uint32_t equal_count_different[VH116_MAX_VBLANK_GAP+1u];
    uint32_t different_count[VH116_MAX_VBLANK_GAP+1u];
} vh116_gap_metrics;
int vh116_get_gap_metrics(vh116_gap_metrics *out);
/* Three consecutive observed Unai callbacks, exact sampled post-values only.
   Gap is the number of VBlank events between oldest and newest callback. */
typedef struct {
    uint32_t consecutive_triplets;
    uint32_t same_as_previous[VH116_MAX_VBLANK_GAP+1u];
    uint32_t returned_to_two_back[VH116_MAX_VBLANK_GAP+1u];
    uint32_t different_from_both[VH116_MAX_VBLANK_GAP+1u];
} vh117_triplet_metrics;
int vh117_get_triplet_metrics(vh117_triplet_metrics *out);
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
