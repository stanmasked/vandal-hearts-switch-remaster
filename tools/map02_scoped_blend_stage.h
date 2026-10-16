/* POSIX-only explicit export of a sealed private MAP02 BlendG1 witness.
 * No implicit logging, stdout output, overwrite, or public paths.
 */
#ifndef VH_MAP02_SCOPED_BLEND_STAGE_H
#define VH_MAP02_SCOPED_BLEND_STAGE_H
int vh_map02_stage_private_blendg1(const char *private_directory);
#endif
