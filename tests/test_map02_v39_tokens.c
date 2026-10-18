#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "vh_map02_v39_tokens.h"
int main(void) {
    VhMap02V39Tag tags[8];
    VhMap02V39Tag hit;
    int terrain = 11, sprite = 22, other = 33, bucket = 44;
    memset(tags, 0, sizeof(tags));
    vh_map02_v39_clear(tags, 8, 1);
    assert(!vh_map02_v39_get(tags, 8, 1, 0, &hit));
    assert(vh_map02_v39_mark(tags, 8, 1, &terrain, 0, 1,
                            &terrain, 11, 641, VH_MAP02_V39_NORMAL));
    assert(vh_map02_v39_get(tags, 8, 1, 0, &hit));
    assert(hit.gfx == 641 && hit.route == VH_MAP02_V39_NORMAL);
    assert(!vh_map02_v39_get(tags, 8, 1, 1, &hit)); /* OT bucket */
    vh_map02_v39_clear(tags, 8, 1);
    assert(!vh_map02_v39_get(tags, 8, 1, 0, &hit)); /* next frame */
    assert(!vh_map02_v39_mark(tags, 8, 2, &sprite, 0, 2,
                             &terrain, 11, 641, 1)); /* pointer mismatch */
    assert(!vh_map02_v39_mark(tags, 8, 2, &sprite, 0, 1,
                             &sprite, 11, 641, 1)); /* bucket token mismatch */
    assert(!vh_map02_v39_mark(tags, 8, 2, &sprite, 1, 2,
                             &sprite, 11, 641, 1)); /* minted bucket */
    assert(!vh_map02_v39_mark(tags, 8, 2, &sprite, 0, 2,
                             &sprite, 2, 641, 1)); /* wrong map */
    assert(!vh_map02_v39_mark(tags, 8, 2, &sprite, 0, 2,
                             &sprite, 11, 0, 1)); /* missing GFX */
    assert(!vh_map02_v39_mark(tags, 8, 2, &sprite, 0, 2,
                             &sprite, 11, 641, 0)); /* invalid route */
    assert(!vh_map02_v39_mark(tags, 8, 2, &sprite, 0, 2,
                             &sprite, 11, 641, 4)); /* invalid route */
    assert(!vh_map02_v39_mark(tags, 8, 2, &sprite, 0, 2,
                             &sprite, 11, 65536, 2)); /* range */
    assert(!vh_map02_v39_mark(tags, 8, 0, &sprite, 0, 0,
                             &sprite, 11, 641, 2)); /* terminator */
    assert(!vh_map02_v39_mark(tags, 8, 8, &sprite, 0, 8,
                             &sprite, 11, 641, 2)); /* outside table */
    assert(!vh_map02_v39_get(tags, 8, 2, 0, &hit));
    assert(vh_map02_v39_mark(tags, 8, 2, &terrain, 0, 2,
                            &terrain, 11, 643, VH_MAP02_V39_EDGE));
    assert(vh_map02_v39_get(tags, 8, 2, 0, &hit) && hit.gfx==643
           && hit.route==VH_MAP02_V39_EDGE);
    vh_map02_v39_clear(tags, 8, 2);
    assert(vh_map02_v39_mark(tags, 8, 3, &other, 0, 3,
                            &other, 11, 498, VH_MAP02_V39_OVERHEAD));
    assert(vh_map02_v39_get(tags, 8, 3, 0, &hit) && hit.gfx==498);
    assert(!vh_map02_v39_mark(0, 8, 3, &other, 0, 3,
                             &other, 11, 498, 3));
    assert(!vh_map02_v39_get(tags, 8, 0, 0, &hit));
    assert(!vh_map02_v39_get(tags, 8, 3, 0, 0));
    assert(!vh_map02_v39_get(tags, 8, 8, 0, &hit));
    assert(bucket != terrain);
    puts("PASS v39 OT token tag: 24 assertions");
    return 0;
}
