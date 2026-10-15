#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "../source/ps1_memory_view.h"

int main(void) {
    uint8_t *ram = calloc(VH_PS1_RAM_SIZE, 1);
    uint8_t scratch[VH_PS1_SCRATCH_SIZE] = {0};
    VhPs1MemoryView memory = {ram, VH_PS1_RAM_SIZE,
                              scratch, VH_PS1_SCRATCH_SIZE};
    uint8_t *map;
    uint8_t *units;
    uint8_t *special_units;
    uint8_t *file_data;
    uint8_t *save_regular;
    uint8_t *save_battle;
    uint8_t *card_listing;
    uint8_t *card_buffer;
    uint8_t *card_verify;

    assert(ram != NULL);
    /* Symbol address offsets from the pinned US PS1 symbol map. */
    map = vh_ps1_memory_span(&memory, UINT32_C(0x80180210), 1);
    units = vh_ps1_memory_span(&memory, UINT32_C(0x80180210) + 0x2db80, 1);
    special_units = vh_ps1_memory_span(&memory,
                                      UINT32_C(0x80180210) + 0x3a300, 1);
    file_data = vh_ps1_memory_span(&memory, UINT32_C(0x801317c0), 1);
    assert(map == ram + 0x180210);
    assert(units == map + 0x2db80);
    assert(special_units == map + 0x3a300);
    assert(file_data == ram + 0x1317c0);
    /* Scratch1 aliases appear across main.c and card.c. They must share RAM. */
    save_regular = vh_ps1_memory_span(&memory, UINT32_C(0x801317c0) + 0x5000, 1);
    save_battle = vh_ps1_memory_span(&memory, UINT32_C(0x801317c0) + 0x6000, 1);
    card_listing = vh_ps1_memory_span(&memory, UINT32_C(0x801317c0) + 0xa000, 1);
    card_buffer = vh_ps1_memory_span(&memory, UINT32_C(0x801317c0) + 64, 1);
    card_verify = vh_ps1_memory_span(&memory, UINT32_C(0x801317c0) + 8256, 1);
    assert(save_regular == file_data + 0x5000);
    assert(save_battle == file_data + 0x6000);
    assert(card_listing == file_data + 0xa000);
    assert(card_buffer == file_data + 64);
    assert(card_verify == file_data + 8256);
    card_verify[0] = 0x3b;
    assert(file_data[8256] == 0x3b);
    /* Offset relationships alone cannot prove the caller owns these bytes. */
    assert(units > map && special_units > units);

    /* Two independently requested views of the same PS1 bytes must alias. */
    map[12] = 0x5a;
    assert(vh_ps1_memory_span(&memory, UINT32_C(0x8018021c), 1)[0] == 0x5a);
    units[0] = 0x7c;
    assert(map[0x2db80] == 0x7c);
    assert(vh_ps1_memory_span(&memory, UINT32_C(0x80180210) + 0x2db80, 1)
           == units);

    assert(vh_ps1_memory_span(&memory, VH_PS1_RAM_BASE, 1) == ram);
    assert(vh_ps1_memory_span(&memory, UINT32_C(0x801fffff), 1)
           == ram + VH_PS1_RAM_SIZE - 1);
    assert(vh_ps1_memory_span(&memory, UINT32_C(0x801fffff), 2) == NULL);
    assert(vh_ps1_memory_span(&memory, UINT32_C(0x80200000), 1) == NULL);
    assert(vh_ps1_memory_span(&memory, UINT32_C(0xffffffff), 2) == NULL);
    /* Deliberately do not emulate KUSEG/KSEG1 or low-address mirrors. */
    assert(vh_ps1_memory_span(&memory, UINT32_C(0x00000000), 1) == NULL);
    assert(vh_ps1_memory_span(&memory, UINT32_C(0xa0000000), 1) == NULL);
    /* An enormous length must not overflow a size_t subtraction. */
    assert(vh_ps1_memory_span(&memory, VH_PS1_RAM_BASE, SIZE_MAX) == NULL);
    assert(vh_ps1_memory_span(&memory, VH_PS1_SCRATCH_BASE, 0x400)
           == scratch);
    assert(vh_ps1_memory_span(&memory, UINT32_C(0x1f8003ff), 1)
           == scratch + 0x3ff);
    assert(vh_ps1_memory_span(&memory, UINT32_C(0x1f8003ff), 2) == NULL);
    assert(vh_ps1_memory_span(&memory, UINT32_C(0x1f800400), 1) == NULL);
    assert(vh_ps1_memory_span(NULL, VH_PS1_RAM_BASE, 1) == NULL);

    /* Caller-provided capacity is enforced even within nominal PS1 address space. */
    memory.ram_size = 10;
    assert(vh_ps1_memory_span(&memory, VH_PS1_RAM_BASE + 9, 2) == NULL);
    memory.ram_size = VH_PS1_RAM_SIZE + 10;
    assert(vh_ps1_memory_span(&memory, UINT32_C(0x801fffff), 2) == NULL);
    memory.ram = NULL;
    assert(vh_ps1_memory_span(&memory, VH_PS1_RAM_BASE, 1) == NULL);

    free(ram);
    puts("PS1 host-backed memory view tests passed.");
    return 0;
}
