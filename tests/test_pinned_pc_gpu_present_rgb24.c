/* Host-only resource-free test of the pinned upstream PC_GpuPresent conversion.
 * Built from the original pinned translation unit with opt-in exclusive observer.
 */
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

void PC_GpuPresent(unsigned short *vram, int vramW, int vramH,
                   int x, int y, int w, int h);

static int observed;
static int incorrect;
void VH_ObserveCompletedRGB24(const unsigned char *pixels,
                              size_t capacity, int width, int height) {
    /* Source is 3x2 BGR555. Last input row comes first in bottom-up RGB24. */
    const unsigned char expected[] = {
        255,255,255, 0,0,0, 132,132,132,
        255,0,0, 0,255,0, 0,0,255
    };
    ++observed;
    if (!pixels || width != 3 || height != 2 ||
        capacity < sizeof(expected) ||
        memcmp(pixels, expected, sizeof(expected)) != 0) incorrect = 1;
}

/* Test-only functions replacing game/configuration services, not proprietary
 * game data. The pinned CPU conversion and observer call remain unchanged.
 */
int PC_MovieSubsLoaded(void) { return 0; }
int PC_OverlayIsOpen(void) { return 0; }
int PC_BattleSpeedGet(void) { return 1; }

int main(void) {
    unsigned short vram[6] = {
        0x001f, 0x03e0, 0x7c00,
        0x7fff, 0x0000, 0x4210
    };
    PC_GpuPresent(vram, 3, 2, 0, 0, 3, 2);
    if (observed != 1 || incorrect) {
        fprintf(stderr, "PC_GpuPresent BGR555 to bottom-up RGB24 mismatch: observed=%d bad=%d\n",
                observed, incorrect);
        return 1;
    }
    puts("Pinned PC_GpuPresent delivered exact RGB24 colors and bottom-up row order.");
    return 0;
}
