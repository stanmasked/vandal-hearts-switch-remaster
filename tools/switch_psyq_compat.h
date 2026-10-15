#ifndef VH_SWITCH_PSYQ_COMPAT_H
#define VH_SWITCH_PSYQ_COMPAT_H
/*
 * Cross-compiler preinclude for the pinned PC-port's PsyQ-compatible headers.
 * Its clean-room libgpu.h uses BSD u_char/u_short from sys/types.h, while
 * devkitA64/newlib does not expose these aliases in strict C11 mode.
 * The aliases have the same widths as the pinned clean-room packet fields.
 * Do not apply to original PSX build sources or the Windows/macOS build.
 */
typedef unsigned char u_char;
typedef unsigned short u_short;
#endif
