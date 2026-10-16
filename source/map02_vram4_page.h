#ifndef VH_MAP02_VRAM4_PAGE_H
#define VH_MAP02_VRAM4_PAGE_H

/*
 * Original PC-port PS1 GPU 4-bpp source VRAM -> local 256x256 index atlas.
 *
 * From pinned platform/pc/src/pc_raster.c SampleTexture and the v49
 * independently verified source-word formula:
 *   effective_u = (u & ~(maskx*8)) | ((offx & maskx)*8)
 *   effective_v = (v & ~(masky*8)) | ((offy & masky)*8)
 *   word_x = (tpage & 15)*64 + effective_u/4
 *   word_y = ((tpage >> 4)&1)*256 + effective_v
 *   nibble = (word >> ((effective_u&3)*4)) & 15
 *   palette_x = (clut&63)*16 + nibble
 *   palette_y = (clut>>6)&511
 *
 * This tool does not authenticate original game VRAM: the caller owns and
 * supplies one full 1024x512 little-endian BGR555 VRAM snapshot AND
 * independently established tpage, clut and texture-window registers.
 * It does not apply PS1 blending, shading, drawing-area masks or dithering.
 * The resulting atlas and palette can be passed to the already tested
 * vh_map02_ot_scene_draw FT4 compositor (CPU-affine diagnostic only).
 */
#include <stddef.h>
#include <stdint.h>

#define VH_MAP02_VRAM_WORD_WIDTH 1024u
#define VH_MAP02_VRAM_WORD_HEIGHT 512u
#define VH_MAP02_VRAM_BYTES (VH_MAP02_VRAM_WORD_WIDTH * VH_MAP02_VRAM_WORD_HEIGHT * 2u)
#define VH_MAP02_VRAM4_ATLAS_BYTES 32768u
#define VH_MAP02_VRAM4_CLUT_BYTES 32u

typedef struct {
    int tpage;
    int clut;
    int mask_x, mask_y; /* GP0 E2h texture window masks, 5 bits */
    int offset_x, offset_y; /* GP0 E2h texture window offsets, 5 bits */
} VhMap02Vram4Registers;

typedef struct {
    size_t decoded_texels;
    size_t zero_index_texels;
    size_t stp_palette_texels;
    int page_word_x;
    int page_word_y;
    int clut_word_x;
    int clut_word_y;
} VhMap02Vram4PageStats;

static inline uint16_t vh_map02_vram4_word(
    const uint8_t *vram_le, size_t index) {
    const size_t p = index * 2u;
    return (uint16_t)((uint16_t)vram_le[p] |
                       ((uint16_t)vram_le[p + 1u] << 8));
}

/* Fail closed before modifying output on invalid register/size metadata. */
static inline int vh_map02_vram4_registers_valid(
    const VhMap02Vram4Registers *registers) {
    if (!registers || registers->tpage < 0 || registers->tpage > 65535 ||
        registers->clut < 0 || registers->clut > 65535 ||
        ((registers->tpage >> 7) & 3) != 0 || /* only 4-bit page */
        registers->mask_x < 0 || registers->mask_x > 31 ||
        registers->mask_y < 0 || registers->mask_y > 31 ||
        registers->offset_x < 0 || registers->offset_x > 31 ||
        registers->offset_y < 0 || registers->offset_y > 31)
        return 0;
    return 1;
}

/*
 * Build a complete local texture atlas (256x256 4bpp, row stride 128)
 * and 16-entry BGR555 CLUT (32 bytes). Texture-window transformation is
 * baked into the atlas, so subsequent FT4 sampling uses unmodified UVWH.
 *
 * Returns 1 on success, 0 on any malformed input, with NO output writes
 * on failure. Destination buffers must not overlap VRAM or each other.
 * This is a documented non-aliasing contract, not an alias detector.
 * A changed VRAM snapshot between calls changes results; caller freezes
 * the source while materializing a page.
 */
static inline int vh_map02_vram4_materialize(
    const uint8_t *vram_le, size_t vram_bytes,
    const VhMap02Vram4Registers *registers,
    uint8_t *atlas4, size_t atlas_bytes,
    uint8_t *clut_le, size_t clut_bytes,
    VhMap02Vram4PageStats *stats) {
    size_t u, v, zeros = 0u, stp = 0u;
    unsigned page_x, page_y, clut_x, clut_y;
    uint16_t colors[16];
    if (!vram_le || !atlas4 || !clut_le ||
        vram_bytes != VH_MAP02_VRAM_BYTES ||
        atlas_bytes < VH_MAP02_VRAM4_ATLAS_BYTES ||
        clut_bytes < VH_MAP02_VRAM4_CLUT_BYTES ||
        !vh_map02_vram4_registers_valid(registers))
        return 0;
    page_x = ((unsigned)registers->tpage & 15u) * 64u;
    page_y = (((unsigned)registers->tpage >> 4) & 1u) * 256u;
    clut_x = ((unsigned)registers->clut & 63u) * 16u;
    clut_y = ((unsigned)registers->clut >> 6) & 511u;
    /* All valid four-bit pages and palettes lie inside VRAM, but keep
     * explicit boundary checks if the above register decoding changes. */
    if (page_x + 64u > VH_MAP02_VRAM_WORD_WIDTH ||
        page_y + 256u > VH_MAP02_VRAM_WORD_HEIGHT ||
        clut_x + 16u > VH_MAP02_VRAM_WORD_WIDTH ||
        clut_y >= VH_MAP02_VRAM_WORD_HEIGHT)
        return 0;
    for (u = 0u; u < 16u; ++u)
        colors[u] = vh_map02_vram4_word(
            vram_le, (size_t)clut_y * VH_MAP02_VRAM_WORD_WIDTH + clut_x + u);
    for (v=0u; v<256u; ++v) {
        unsigned effective_v = ((unsigned)v &
                ~((unsigned)registers->mask_y * 8u)) |
                (((unsigned)registers->offset_y &
                  (unsigned)registers->mask_y) * 8u);
        for (u=0u; u<256u; u+=2u) {
            uint8_t indices[2];
            unsigned i;
            for (i=0u; i<2u; ++i) {
                unsigned original_u=(unsigned)u+i;
                unsigned effective_u=(original_u &
                    ~((unsigned)registers->mask_x * 8u)) |
                    (((unsigned)registers->offset_x &
                      (unsigned)registers->mask_x) * 8u);
                unsigned tx=page_x+effective_u/4u;
                unsigned ty=page_y+effective_v;
                uint16_t raw=vh_map02_vram4_word(
                    vram_le, (size_t)ty*VH_MAP02_VRAM_WORD_WIDTH+tx);
                uint8_t ix=(uint8_t)((raw>>((effective_u&3u)*4u))&15u);
                indices[i]=ix;
                zeros += ix == 0u;
                stp += (colors[ix]&0x8000u)!=0u;
            }
            atlas4[v*128u+u/2u]=(uint8_t)(indices[0] |
                                             (uint8_t)(indices[1]<<4u));
        }
    }
    for (u=0u; u<16u; ++u) {
        clut_le[u*2u]=(uint8_t)colors[u];
        clut_le[u*2u+1u]=(uint8_t)(colors[u]>>8);
    }
    if (stats) {
        *stats=(VhMap02Vram4PageStats){
            65536u,zeros,stp,
            (int)page_x,(int)page_y,(int)clut_x,(int)clut_y
        };
    }
    return 1;
}
#endif
