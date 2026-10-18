#ifndef VH_MAP02_V39_TOKENS_H
#define VH_MAP02_V39_TOKENS_H

/* Diagnostic provenance for the pinned US PC-port OT token registry.
 * No game data, pixels, or primitive layout is modified.
 * C89: all decisions are fail-closed and bound to one minted OT token.
 */
#include <stddef.h>

#define VH_MAP02_V39_MAPNUM 11
#define VH_MAP02_V39_NORMAL 1
#define VH_MAP02_V39_EDGE 2
#define VH_MAP02_V39_OVERHEAD 3

typedef struct {
    unsigned int gfx;
    unsigned char route;
    unsigned char valid;
} VhMap02V39Tag;

static void vh_map02_v39_clear(VhMap02V39Tag *tags, size_t capacity,
                               unsigned int token)
{
    if (!tags || token >= capacity) return;
    tags[token].valid = 0;
    tags[token].gfx = 0;
    tags[token].route = 0;
}

/* Called directly AFTER AddPrim. Each argument independently prevents stale
 * token reuse, OT bucket confusion or a false positive on another map. */
static int vh_map02_v39_mark(VhMap02V39Tag *tags, size_t capacity,
                             unsigned int latest_token, const void *latest_ptr,
                             int latest_is_bucket, unsigned int bucket_token,
                             const void *primitive, int mapnum, int gfx,
                             unsigned int route)
{
    if (!tags || !latest_token || latest_token >= capacity ||
        !primitive || latest_ptr != primitive || latest_is_bucket ||
        bucket_token != latest_token || mapnum != VH_MAP02_V39_MAPNUM ||
        gfx <= 0 || gfx > 65535 ||
        route < VH_MAP02_V39_NORMAL || route > VH_MAP02_V39_OVERHEAD)
        return 0;
    tags[latest_token].gfx = (unsigned int)gfx;
    tags[latest_token].route = (unsigned char)route;
    tags[latest_token].valid = 1;
    return 1;
}

static int vh_map02_v39_get(const VhMap02V39Tag *tags, size_t capacity,
                            unsigned int token, int is_bucket,
                            VhMap02V39Tag *out)
{
    if (!tags || !out || !token || token >= capacity || is_bucket ||
        !tags[token].valid)
        return 0;
    *out = tags[token];
    return 1;
}
#endif
