#ifndef VH_PRIVATE_MAP_SHADING_H
#define VH_PRIVATE_MAP_SHADING_H

#include <stdint.h>

/* EXACT src/core/graphics.c::RenderMapTile distance attenuation:
 * shading=CLAMP(otz-150,0,256)
 * output=side_light - ((side_light*shading)>>8).
 * The side-light RGB supplied by a caller is an input. A neutral
 * (128,128,128) probe value is NOT the original gSideLightColor table,
 * which depends on the game's mutable light rotation/intensity.
 */
static inline unsigned char vh_map_distance_component(unsigned char side,
                                                       int otz) {
    int shading = otz - 150;
    if (shading < 0) shading = 0;
    if (shading > 256) shading = 256;
    return (unsigned char)(side - ((side * shading) >> 8));
}
#endif
