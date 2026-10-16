/* POSIX-only explicit export of a sealed private MAP02 BlendG1 witness.
 * No implicit logging, stdout output, overwrite, or public paths.
 */
#ifndef VH_MAP02_SCOPED_BLEND_STAGE_H
#define VH_MAP02_SCOPED_BLEND_STAGE_H
int vh_map02_stage_private_blendg1(const char *private_directory);
/* Stage both independently observed PutPixel and BlendG1 rows from ONE sealed
 * frame. Neither stream is a completed SHA-verified witness at this stage. */
int vh_map02_stage_private_pair(const char *private_directory);
#endif
