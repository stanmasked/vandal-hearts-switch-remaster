#ifndef VH80_NATIVE_TIMELINE_H
#define VH80_NATIVE_TIMELINE_H
#include <stdint.h>
/* Opt-in bounded observer: input submissions and emulator VBlank only.
 * NOT native GP0 consumption, GPU completion, VRAM writes, or retail MAP02. */
enum { VH80_VBLANK=1, VH80_GP1_MMIO=2, VH80_GPU_DMA2=3, VH83_GP0_UNAI_HANDLED=4, VH84_UNAI_SAMPLE_DELTA=5, VH85_UNAI_STORE_COUNT=6, VH85_UNAI_SAME_STORE_COUNT=7,
  VH86_A0_STORES=8, VH86_A0_SAME=9, VH86_COPY_STORES=10, VH86_COPY_SAME=11,
  VH87_OVERLAP_STORES=12, VH87_OVERLAP_SAME=13,
  VH87_MASK_UPLOAD_STORES=14, VH87_MASK_UPLOAD_SAME=15,
  VH87_WRAP_STORES=16, VH87_WRAP_SAME=17,
  VH88_ASYNC_QUEUED=18, VH88_ASYNC_COMPLETED=19,
  VH88_ASYNC_STORES=20, VH88_ASYNC_SAME=21 };
typedef struct {
    uint32_t sequence, kind, value, cycle, frame;
} vh80_event;
#ifdef __cplusplus
extern "C" {
#endif
void vh80_record(uint32_t kind,uint32_t value,uint32_t cycle,uint32_t frame);
void vh80_reset(void);
/* Enable only after authenticated synthetic fixture acceptance. */
void vh84_set_sampling(int enabled);
int vh84_sampling_enabled(void);
void vh85_reset_command(void);
void vh85_note_store(uint32_t before, uint32_t after);
unsigned int vh85_store_count(void);
unsigned int vh85_same_store_count(void);
unsigned int vh85_write_overflow(void);
/* Observes synchronous gpulib logical 16-bit stores on opt-in fixture. */
enum { VH86_A0_UPLOAD=1, VH86_VRAM_COPY=2 };
void vh86_reset(void);
void vh86_note_store(uint32_t source,uint32_t old_value,uint32_t new_value);
uint32_t vh86_store_count(uint32_t source);
uint32_t vh86_same_store_count(uint32_t source);
uint32_t vh86_write_overflow(void);
unsigned int vh80_count(void);
unsigned int vh80_dropped(void);
const vh80_event *vh80_events(void);
#ifdef __cplusplus
}
#endif
#endif
