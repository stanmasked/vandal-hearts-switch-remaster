/* Standalone bounded native MAP02 observer; no disk/network output.
 * Compile/link ONLY in an opted-in private original-PC test harness.
 * Context setters must be invoked from directly observed DrawOTag traversal.
 * This file does NOT prove the supplied frame/ordinal context is genuine.
 */
#ifndef VH_MAP02_SCOPED_BLEND_SINK_H
#define VH_MAP02_SCOPED_BLEND_SINK_H

#define VH_MAP02_MAX_EVENTS 63u

typedef struct VHMap02BlendEvent {
    unsigned frame, ordinal, step, primitive_type;
    int x, y, abr, semi, textured, accurate;
    unsigned short before, front, after;
    int has_blend;
    unsigned short blend_fg, blend_bg, blend_result;
} VHMap02BlendEvent;

void vh_map02_scope_reset(void);
void vh_map02_scope_abort(void);
int vh_map02_scope_begin_frame(unsigned frame, int x, int y);
int vh_map02_scope_begin_primitive(unsigned ordinal, unsigned primitive_type);
int vh_map02_scope_end_primitive(void);
int vh_map02_scope_end_frame(void);
unsigned vh_map02_scope_count(void);
int vh_map02_scope_failed(void);
int vh_map02_scope_copy(unsigned index, VHMap02BlendEvent *out);
/* Formats one private, closed-frame JSONL event into caller memory only.
 * No file I/O; returns bytes or zero if invalid / buffer too small. */
int vh_map02_scope_format_putpixel(unsigned index, char *dst, unsigned capacity);
int vh_map02_scope_format_blendg1(unsigned index, char *dst, unsigned capacity);

void vh_map02_probe_begin(int x, int y, unsigned short before,
    unsigned short front, int abr, int semi, int textured, int accurate);
void vh_map02_probe_blendg1(int x, int y, unsigned short fg,
    unsigned short bg, unsigned short result, int abr, int textured);
void vh_map02_probe_end(int x, int y, unsigned short after);

#endif
