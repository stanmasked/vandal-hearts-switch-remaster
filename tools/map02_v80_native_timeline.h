#ifndef VH80_NATIVE_TIMELINE_H
#define VH80_NATIVE_TIMELINE_H
#include <stdint.h>
/* Opt-in bounded observer: input submissions and emulator VBlank only.
 * NOT native GP0 consumption, GPU completion, VRAM writes, or retail MAP02. */
enum { VH80_VBLANK=1, VH80_GP1_MMIO=2, VH80_GPU_DMA2=3 };
typedef struct {
    uint32_t sequence, kind, value, cycle, frame;
} vh80_event;
void vh80_record(uint32_t kind,uint32_t value,uint32_t cycle,uint32_t frame);
void vh80_reset(void);
unsigned int vh80_count(void);
unsigned int vh80_dropped(void);
const vh80_event *vh80_events(void);
#endif
