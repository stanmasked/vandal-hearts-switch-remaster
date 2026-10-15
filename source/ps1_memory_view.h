#ifndef VH_PS1_MEMORY_VIEW_H
#define VH_PS1_MEMORY_VIEW_H

/*
 * Host-owned PS1 memory address views for isolated tests.
 * No fixed virtual-address mappings and no original game data.
 * This is NOT yet wired into the upstream game.
 */
#include <stddef.h>
#include <stdint.h>

#define VH_PS1_RAM_BASE UINT32_C(0x80000000)
#define VH_PS1_RAM_SIZE ((size_t)2 * 1024 * 1024)
#define VH_PS1_SCRATCH_BASE UINT32_C(0x1f800000)
#define VH_PS1_SCRATCH_SIZE ((size_t)0x400)

typedef struct VhPs1MemoryView {
    uint8_t *ram;
    size_t ram_size;
    uint8_t *scratch;
    size_t scratch_size;
} VhPs1MemoryView;

/* Reject out-of-range, overflowing and cross-region spans. Zero length is
 * allowed only at an in-region address; it does not grant usable storage. */
static inline uint8_t *vh_ps1_memory_span(const VhPs1MemoryView *mem,
                                           uint32_t address, size_t length) {
    uint32_t base;
    size_t capacity;
    uint8_t *storage;
    size_t offset;

    if (mem == NULL) return NULL;
    if (address >= VH_PS1_RAM_BASE &&
        (uint64_t)address - VH_PS1_RAM_BASE < VH_PS1_RAM_SIZE) {
        base = VH_PS1_RAM_BASE;
        capacity = mem->ram_size;
        storage = mem->ram;
        if (capacity > VH_PS1_RAM_SIZE) capacity = VH_PS1_RAM_SIZE;
    } else if (address >= VH_PS1_SCRATCH_BASE &&
               (uint64_t)address - VH_PS1_SCRATCH_BASE < VH_PS1_SCRATCH_SIZE) {
        base = VH_PS1_SCRATCH_BASE;
        capacity = mem->scratch_size;
        storage = mem->scratch;
        if (capacity > VH_PS1_SCRATCH_SIZE) capacity = VH_PS1_SCRATCH_SIZE;
    } else {
        return NULL;
    }

    if (storage == NULL) return NULL;
    offset = (size_t)((uint64_t)address - base);
    if (offset > capacity || length > capacity - offset) return NULL;
    return storage + offset;
}

#endif
