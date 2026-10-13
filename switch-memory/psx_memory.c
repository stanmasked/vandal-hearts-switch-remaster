#include "psx_memory.h"

static void *translate_region(uint8_t *storage, size_t storage_size,
                              uint32_t guest_address, uint32_t guest_base,
                              size_t region_size, size_t length) {
    size_t offset;

    if (storage == NULL || length == 0 || storage_size < region_size) {
        return NULL;
    }
    if (guest_address < guest_base) {
        return NULL;
    }

    offset = (size_t)(guest_address - guest_base);
    if (offset >= region_size || length > region_size - offset) {
        return NULL;
    }

    return storage + offset;
}

void *psx_memory_translate(PsxMemory *memory, uint32_t guest_address, size_t length) {
    void *translated;

    if (memory == NULL) {
        return NULL;
    }

    translated = translate_region(memory->main_ram, memory->main_ram_size,
                                  guest_address, PSX_MAIN_RAM_BASE,
                                  PSX_MAIN_RAM_SIZE, length);
    if (translated != NULL) {
        return translated;
    }

    return translate_region(memory->scratchpad, memory->scratchpad_size,
                            guest_address, PSX_SCRATCHPAD_BASE,
                            PSX_SCRATCHPAD_SIZE, length);
}
