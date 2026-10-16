#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "../source/map02_op0_reference.h"
#include "../source/map02_face_direction.h"

static void test_baseline_cross(void) {
    const int32_t a[] = {2, 3, 5}, b[] = {7, 11, 13};
    VhMap02Op0Mac pc, ps1;
    assert(vh_map02_op0_pc(a, b, &pc));
    assert(vh_map02_op0_ps1_registers(a, b, &ps1));
    assert(pc.x == -16 && pc.y == 9 && pc.z == 1);
    assert(ps1.x == pc.x && ps1.y == pc.y && ps1.z == pc.z);
}

static void test_truncation_of_both_inputs(void) {
    const int32_t a[] = {65535, 65535, 0};
    const int32_t b[] = {-65535, 0, 65535};
    VhMap02Op0Mac pc, ps1;
    assert(vh_map02_op0_pc(a, b, &pc));
    assert(vh_map02_op0_ps1_registers(a, b, &ps1));
    assert(pc.x == -65535 && pc.y == 65535 && pc.z == -65535);
    assert(ps1.x == 1 && ps1.y == -1 && ps1.z == 1);
    assert(vh_map02_op0_signed16(-65535) == 1);
    assert(vh_map02_op0_signed16(65535) == -1);
    assert(vh_map02_op0_signed16(-32768) == -32768);
    assert(vh_map02_op0_signed16(32768) == -32768);
}

static void test_overflow_and_mac_not_saturated_ir(void) {
    const int32_t a[] = {65535, 65535, 65535};
    const int32_t b[] = {32767, -32768, 32767};
    VhMap02Op0Mac pc, ps1;
    assert(vh_map02_op0_pc(a, b, &pc));
    assert(vh_map02_op0_ps1_registers(a, b, &ps1));
    assert(pc.x == -131071 && pc.y == 0 && pc.z == 131071);
    assert(ps1.x == -65535 && ps1.y == 0 && ps1.z == 65535);
    /* StoreLVNL exposes MAC even though OP0's IR saturates at 32767. */
    assert(pc.x < -32768 && pc.z > 32767);
    assert(vh_map02_op0_wrap32(INT64_C(4294967295)) == -1);
    assert(vh_map02_op0_wrap32(-INT64_C(4294967295)) == 1);
}

static void test_classification_compatibility_and_failure_atomicity(void) {
    const int32_t a[] = {100, 0, 0}, b[] = {0, 0, 100};
    VhMap02Op0Mac mac = {7, 8, 9};
    uint8_t direction = 255;
    assert(!vh_map02_op0_pc(NULL, b, &mac));
    assert(!vh_map02_op0_pc(a, NULL, &mac));
    assert(!vh_map02_op0_pc(a, b, NULL));
    assert(mac.x == 7 && mac.y == 8 && mac.z == 9);
    assert(vh_map02_op0_pc(a, b, &mac));
    assert(mac.y == -10000);
    assert(vh_map02_best_q12_direction(
        (VhMap02Cross){mac.x, mac.y, mac.z}, &direction));
    assert(direction == 1);
}

int main(void) {
    test_baseline_cross();
    test_truncation_of_both_inputs();
    test_overflow_and_mac_not_saturated_ir();
    test_classification_compatibility_and_failure_atomicity();
    puts("MAP02 PC OP0 and PS1 register-boundary model tests passed");
    return 0;
}
