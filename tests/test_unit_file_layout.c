#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/unit_file_layout.h"

static void write32(uint8_t *p, uint32_t n) {
    p[0] = (uint8_t)n; p[1] = (uint8_t)(n >> 8);
    p[2] = (uint8_t)(n >> 16); p[3] = (uint8_t)(n >> 24);
}
int main(void) {
    uint8_t data[80] = {0};
    VhUnitFileLayout layout, saved;
    data[2] = 1; data[3] = 1;  /* two sheets */
    write32(data + 4, 8);
    write32(data + 8, 12);
    write32(data + 12, 8);
    write32(data + 20, 12);
    assert(vh_unit_file_layout(data, sizeof data, &layout));
    assert(layout.sheet_count == 2);
    assert(layout.sheet_offsets[0] == 12 && layout.sheet_lengths[0] == 8);
    assert(layout.sheet_offsets[1] == 20 && layout.sheet_lengths[1] == 12);
    assert(layout.strips_offset == 32);
    saved = layout;

    assert(!vh_unit_file_layout(NULL, sizeof data, &layout));
    assert(!vh_unit_file_layout(data, sizeof data, NULL));
    assert(!vh_unit_file_layout(data, 3, &layout));
    assert(!vh_unit_file_layout(data, 31, &layout));
    assert(!vh_unit_file_layout(data, 8, &layout));
    assert(memcmp(&layout, &saved, sizeof saved) == 0);

    data[3] = 6; /* seven exceeds the fixed six-entry sheet pointer table */
    assert(!vh_unit_file_layout(data, sizeof data, &layout));
    data[3] = 1;
    data[2] = 0; data[3] = 0;
    assert(!vh_unit_file_layout(data, sizeof data, &layout));
    data[2] = 1; data[3] = 1;
    write32(data + 4, UINT32_MAX);
    assert(!vh_unit_file_layout(data, sizeof data, &layout));
    write32(data + 4, 8);
    write32(data + 8, 9); /* unaligned */
    assert(!vh_unit_file_layout(data, sizeof data, &layout));
    write32(data + 8, 12);
    write32(data + 20, 16); /* sheet's internal copy size exceeds table */
    assert(!vh_unit_file_layout(data, sizeof data, &layout));
    write32(data + 20, 8); /* inner copied size need not equal outer span */
    assert(vh_unit_file_layout(data, 32, &layout));
    assert(layout.sheet_lengths[1] == 12);
    write32(data + 20, 12);
    assert(layout.strips_offset == 32);
    puts("Unit file layout checks passed.");
    return 0;
}
