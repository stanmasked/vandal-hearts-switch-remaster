#include "psx_memory.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>

static uint8_t main_ram[PSX_MAIN_RAM_SIZE];
static uint8_t scratchpad[PSX_SCRATCHPAD_SIZE];

static PsxMemory make_memory(void) {
    PsxMemory memory = {
        .main_ram = main_ram,
        .main_ram_size = sizeof main_ram,
        .scratchpad = scratchpad,
        .scratchpad_size = sizeof scratchpad,
    };
    return memory;
}

static void test_main_ram_boundaries(void) {
    PsxMemory memory = make_memory();
    assert(psx_memory_translate(&memory, PSX_MAIN_RAM_BASE, 1) == &main_ram[0]);
    assert(psx_memory_translate(&memory, PSX_MAIN_RAM_BASE + (uint32_t)PSX_MAIN_RAM_SIZE - 1, 1)
           == &main_ram[PSX_MAIN_RAM_SIZE - 1]);
    assert(psx_memory_translate(&memory, PSX_MAIN_RAM_BASE, PSX_MAIN_RAM_SIZE) == main_ram);
    assert(psx_memory_translate(&memory, PSX_MAIN_RAM_BASE + (uint32_t)PSX_MAIN_RAM_SIZE, 1) == NULL);
    assert(psx_memory_translate(&memory, PSX_MAIN_RAM_BASE + (uint32_t)PSX_MAIN_RAM_SIZE - 1, 2) == NULL);
    assert(psx_memory_translate(&memory, PSX_MAIN_RAM_BASE - 1, 1) == NULL);
}

static void test_scratchpad_boundaries(void) {
    PsxMemory memory = make_memory();
    assert(psx_memory_translate(&memory, PSX_SCRATCHPAD_BASE, 1) == &scratchpad[0]);
    assert(psx_memory_translate(&memory, PSX_SCRATCHPAD_BASE + (uint32_t)PSX_SCRATCHPAD_SIZE - 1, 1)
           == &scratchpad[PSX_SCRATCHPAD_SIZE - 1]);
    assert(psx_memory_translate(&memory, PSX_SCRATCHPAD_BASE, PSX_SCRATCHPAD_SIZE) == scratchpad);
    assert(psx_memory_translate(&memory, PSX_SCRATCHPAD_BASE + (uint32_t)PSX_SCRATCHPAD_SIZE - 1, 2) == NULL);
}

static void test_unsupported_ranges_and_invalid_storage(void) {
    PsxMemory memory = make_memory();
    PsxMemory short_ram = memory;
    PsxMemory missing_scratch = memory;

    assert(psx_memory_translate(NULL, PSX_MAIN_RAM_BASE, 1) == NULL);
    assert(psx_memory_translate(&memory, 0, 1) == NULL);
    assert(psx_memory_translate(&memory, UINT32_C(0x1f801810), 4) == NULL);
    assert(psx_memory_translate(&memory, PSX_MAIN_RAM_BASE, 0) == NULL);

    short_ram.main_ram_size = PSX_MAIN_RAM_SIZE - 1;
    assert(psx_memory_translate(&short_ram, PSX_MAIN_RAM_BASE, 1) == NULL);

    missing_scratch.scratchpad = NULL;
    assert(psx_memory_translate(&missing_scratch, PSX_SCRATCHPAD_BASE, 1) == NULL);
}

int main(void) {
    test_main_ram_boundaries();
    test_scratchpad_boundaries();
    test_unsupported_ranges_and_invalid_storage();
    puts("PS1 memory translation tests passed");
    return 0;
}
