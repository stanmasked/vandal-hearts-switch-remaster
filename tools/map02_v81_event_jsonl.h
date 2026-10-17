#ifndef VH81_EVENT_JSONL_H
#define VH81_EVENT_JSONL_H
#include <stddef.h>
/* Formats bounded observer events into caller-provided memory.
 * No private file creation, no heap allocation, no GPU modifications.
 * Return byte count, or -1 for any insufficient/inconsistent evidence. */
int vh81_format_jsonl(char *output,size_t capacity);
#endif
