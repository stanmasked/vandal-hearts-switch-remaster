/* Optional same-process ordering gate, separate from CD/VRAM integrity audits.
 * This gate NEVER proves that original MAP02 artwork was rendered. */
#ifndef VH_MAP02_CYCLE_ORDER_H
#define VH_MAP02_CYCLE_ORDER_H
#include <stddef.h>
void vh_map02_cycle_load(int cdf, int target_cdf, int lba, int sectors);
void vh_map02_cycle_read_start(int lba, int sectors);
void vh_map02_cycle_read_finish(int lba, int sectors);
void vh_map02_cycle_loader_complete(int cdf, int target_cdf, int state);
void vh_map02_cycle_draw_start(unsigned frame);
void vh_map02_cycle_draw_primitive(unsigned frame);
void vh_map02_cycle_draw_finish(unsigned frame, int walk_complete);
int vh_map02_cycle_failed(void);
int vh_map02_cycle_format_jsonl(char *out, size_t capacity);
#endif
