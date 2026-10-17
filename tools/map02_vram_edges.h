/* Independent, bounded native VRAM snapshots at actual DrawOTag draw boundaries.
 * No reliance on PutPixel callbacks, no disk/network output.
 * Use only in a synchronous, opted-in native-PC diagnostic build. */
#ifndef VH_MAP02_VRAM_EDGES_H
#define VH_MAP02_VRAM_EDGES_H
#define VH_MAP02_MAX_DRAW_EDGES 8192u
typedef struct VHMap02VramEdge {
    unsigned frame, ordinal, primitive_type;
    int x, y;
    unsigned short before, after;
} VHMap02VramEdge;
void vh_map02_edges_reset(void);
void vh_map02_edges_abort(void);
int vh_map02_edges_begin_frame(unsigned frame, int x, int y);
int vh_map02_edges_begin_primitive(unsigned ordinal, unsigned primitive_type,
                                   unsigned short before);
int vh_map02_edges_end_primitive(unsigned short after);
int vh_map02_edges_end_frame(void);
unsigned vh_map02_edges_count(void);
int vh_map02_edges_failed(void);
int vh_map02_edges_copy(unsigned index, VHMap02VramEdge *out);
/* Closed-frame, caller-owned JSONL; no disk I/O, zero on invalid/overflow. */
int vh_map02_edges_format_jsonl(unsigned index, char *dst, unsigned capacity);
#endif
