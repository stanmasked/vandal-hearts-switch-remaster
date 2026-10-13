#ifndef VH_SWITCH_PSX_MEMORY_H
#define VH_SWITCH_PSX_MEMORY_H

#include <stddef.h>
#include <stdint.h>

#define PSX_MAIN_RAM_BASE       UINT32_C(0x80000000)
#define PSX_MAIN_RAM_SIZE       ((size_t)0x200000)
#define PSX_SCRATCHPAD_BASE     UINT32_C(0x1f800000)
#define PSX_SCRATCHPAD_SIZE     ((size_t)0x400)

/* Sound work allocation used by the pinned PC port: [0x80140000, 0x80200000). */
#define PSX_SOUND_WORK_BASE     UINT32_C(0x80140000)
#define PSX_SOUND_WORK_SIZE     ((size_t)0x0c0000)

/*
 * Caller-owned host buffers. This prototype intentionally maps only the two
 * explicitly allocated regions; it does not emulate MMIO, zero-address mirrors,
 * KSEG aliases, or any other PS1 address-space behavior.
 */
typedef struct PsxMemory {
    uint8_t *main_ram;
    size_t main_ram_size;
    uint8_t *scratchpad;
    size_t scratchpad_size;
} PsxMemory;

/* Return a host pointer for a fully-contained guest range, or NULL if unsupported. */
void *psx_memory_translate(PsxMemory *memory, uint32_t guest_address, size_t length);

/* Translate only spans inside the legacy sound-work window; preserves RAM aliasing. */
void *psx_sound_work_translate(PsxMemory *memory, uint32_t guest_address, size_t length);

#endif
