/*
 * Read-only decoded M_MAP02.PRS OP0 geometry audit.
 * Input: exactly 616 * 304 bytes on stdin, never written to disk.
 * Output: aggregate JSON only, no vertex coordinates or texture data.
 * Geometry: 28-column backing storage, 24x12 active tile region,
 *           up to 18 faces per tile, vertices[22] SVECTOR(8 bytes).
 *
 * All three paths feed the PC-port Q12 direction classifier:
 *   wide: mathematical 64-bit edge cross (historical diagnostic);
 *   pc:   pinned PC libgte OP0 register behavior;
 *   ps1:  PS1 signed-16 input boundary and low-32 MAC model only.
 * PS1 hardware GTE, BIOS VectorNormalS and screen projection unverified.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../source/map02_face_direction.h"
#include "../source/map02_op0_reference.h"

#define MAP02_COLUMNS 28u
#define MAP02_ROWS 22u
#define MAP02_ACTIVE_X 24u
#define MAP02_ACTIVE_Z 12u
#define MAP02_DECODED_BYTES (MAP02_COLUMNS * MAP02_ROWS * VH_MAP02_TILE_BYTES)

typedef struct {
    unsigned z, x, present, full_direction, pc_direction, ps1_direction;
    unsigned full_valid, pc_valid, ps1_valid, full_pc_equal, pc_ps1_equal;
} Bridge;

typedef struct {
    unsigned tiles, occupied_tiles, faces, degenerate_wide, zero_pc, zero_ps1;
    unsigned pc_mac_vs_wide, ps1_mac_vs_pc, first_edge_signed16_loss;
    unsigned second_edge_signed16_loss;
    unsigned full_pc_compared, full_pc_different;
    unsigned pc_ps1_compared, pc_ps1_different;
    Bridge bridge[2];
} Summary;

static int32_t signed16_from_tile(const uint8_t *tile, unsigned v, unsigned axis) {
    size_t at = (size_t)v * 8u + (size_t)axis * 2u;
    uint16_t raw = (uint16_t)tile[at] | ((uint16_t)tile[at + 1u] << 8);
    return raw <= UINT16_C(0x7fff) ? (int32_t)raw : (int32_t)raw - 65536;
}

static int zero3(int64_t x, int64_t y, int64_t z) {
    return x == 0 && y == 0 && z == 0;
}

static int analyze_face(
    const uint8_t *tile, unsigned face, Summary *s, Bridge *bridge) {
    unsigned v[4], first, second, third, chosen[3], i, k;
    int32_t p[3][3], edge1[3], edge2[3];
    VhMap02Cross wide;
    VhMap02Op0Mac pc, ps1;
    uint8_t iw = 255, ip = 255, is = 255;
    unsigned vw, vp, vs;

    for (i = 0; i < 4u; ++i) {
        v[i] = tile[212u + face * 4u + i];
        if (v[i] >= VH_MAP02_VERTEX_COUNT) return 0;
    }
    /* Exact UpdateMapTileLighting repeated-corner precedence. */
    first = v[0]; second = v[1]; third = v[2];
    if (v[0] == v[1]) {
        first = v[2]; second = v[0]; third = v[3];
    } else if (v[0] == v[2]) {
        first = v[1]; second = v[0]; third = v[3];
    } else if (v[0] == v[3]) {
        first = v[1]; second = v[0]; third = v[2];
    } else if (v[1] == v[2]) {
        first = v[1]; second = v[0]; third = v[3];
    }
    chosen[0] = first; chosen[1] = second; chosen[2] = third;
    for (i = 0; i < 3u; ++i)
        for (k = 0; k < 3u; ++k)
            p[i][k] = signed16_from_tile(tile, chosen[i], k);
    for (k = 0; k < 3u; ++k) {
        edge1[k] = p[1][k] - p[0][k];
        edge2[k] = p[2][k] - p[0][k];
        if (vh_map02_op0_signed16(edge1[k]) != edge1[k])
            ++s->first_edge_signed16_loss;
        if (vh_map02_op0_signed16(edge2[k]) != edge2[k])
            ++s->second_edge_signed16_loss;
    }
    wide.x = (int64_t)edge1[1] * edge2[2] - (int64_t)edge1[2] * edge2[1];
    wide.y = (int64_t)edge1[2] * edge2[0] - (int64_t)edge1[0] * edge2[2];
    wide.z = (int64_t)edge1[0] * edge2[1] - (int64_t)edge1[1] * edge2[0];
    if (!vh_map02_op0_pc(edge1, edge2, &pc) ||
        !vh_map02_op0_ps1_registers(edge1, edge2, &ps1))
        return 0;
    vw = !zero3(wide.x, wide.y, wide.z);
    vp = !zero3(pc.x, pc.y, pc.z);
    vs = !zero3(ps1.x, ps1.y, ps1.z);
    if (vw && !vh_map02_best_q12_direction(wide, &iw)) return 0;
    if (vp && !vh_map02_best_q12_direction(
        (VhMap02Cross){pc.x,pc.y,pc.z}, &ip)) return 0;
    if (vs && !vh_map02_best_q12_direction(
        (VhMap02Cross){ps1.x,ps1.y,ps1.z}, &is)) return 0;
    ++s->faces;
    s->degenerate_wide += !vw;
    s->zero_pc += !vp;
    s->zero_ps1 += !vs;
    s->pc_mac_vs_wide += ((int64_t)pc.x != wide.x ||
                          (int64_t)pc.y != wide.y ||
                          (int64_t)pc.z != wide.z);
    s->ps1_mac_vs_pc += (pc.x != ps1.x || pc.y != ps1.y || pc.z != ps1.z);
    if (vw && vp) {
        ++s->full_pc_compared;
        s->full_pc_different += iw != ip;
    }
    if (vp && vs) {
        ++s->pc_ps1_compared;
        s->pc_ps1_different += ip != is;
    }
    if (bridge) {
        bridge->present = 1;
        bridge->full_valid = vw;
        bridge->pc_valid = vp;
        bridge->ps1_valid = vs;
        bridge->full_direction = iw;
        bridge->pc_direction = ip;
        bridge->ps1_direction = is;
        bridge->full_pc_equal = vw && vp && iw == ip;
        bridge->pc_ps1_equal = vp && vs && ip == is;
    }
    return 1;
}

int main(void) {
    uint8_t *map = (uint8_t *)malloc(MAP02_DECODED_BYTES);
    Summary sum = {0};
    unsigned z, x, face;
    if (!map) {
        fputs("unable to allocate bounded map buffer\n", stderr);
        return 2;
    }
    sum.bridge[0].z = 8; sum.bridge[0].x = 19;
    sum.bridge[1].z = 11; sum.bridge[1].x = 11;
    if (fread(map, 1, MAP02_DECODED_BYTES, stdin) != MAP02_DECODED_BYTES ||
        fgetc(stdin) != EOF) {
        fputs("decoded MAP02 input must be exactly 187264 bytes\n", stderr);
        free(map);
        return 2;
    }
    for (z = 0; z < MAP02_ACTIVE_Z; ++z) {
        for (x = 0; x < MAP02_ACTIVE_X; ++x) {
            unsigned count;
            const uint8_t *tile = map +
                ((size_t)z * MAP02_COLUMNS + x) * VH_MAP02_TILE_BYTES;
            ++sum.tiles;
            count = tile[302];
            if (count > VH_MAP02_FACE_COUNT) {
                fprintf(stderr,"invalid faceCt at z=%u x=%u: %u\n",z,x,count);
                free(map);
                return 3;
            }
            if (count) ++sum.occupied_tiles;
            for (face = 0; face < count; ++face) {
                Bridge *bridge = NULL;
                if (face == 0u && z == 8u && x == 19u)
                    bridge = &sum.bridge[0];
                if (face == 0u && z == 11u && x == 11u)
                    bridge = &sum.bridge[1];
                if (!analyze_face(tile, face, &sum, bridge)) {
                    fprintf(stderr,"invalid face geometry at z=%u x=%u face=%u\n",
                            z,x,face);
                    free(map);
                    return 3;
                }
            }
        }
    }
    printf("{\"active_tiles\":%u,\"occupied_tiles\":%u,"
           "\"faces\":%u,\"degenerate_wide\":%u,\"zero_pc_mac\":%u,"
           "\"zero_ps1_mac_model\":%u,"
           "\"pc_mac_differs_from_full_cross\":%u,"
           "\"ps1_input_mac_differs_from_pc_mac\":%u,"
           "\"first_edge_components_truncated_by_ps1\":%u,"
           "\"second_edge_components_truncated_by_both\":%u,"
           "\"wide_pc_classifications_compared\":%u,"
           "\"wide_pc_classification_differences\":%u,"
           "\"pc_ps1_classifications_compared\":%u,"
           "\"pc_ps1_classification_differences\":%u,",
           sum.tiles,sum.occupied_tiles,sum.faces,sum.degenerate_wide,
           sum.zero_pc,sum.zero_ps1,sum.pc_mac_vs_wide,sum.ps1_mac_vs_pc,
           sum.first_edge_signed16_loss,sum.second_edge_signed16_loss,
           sum.full_pc_compared,sum.full_pc_different,sum.pc_ps1_compared,
           sum.pc_ps1_different);
    printf("\"bridge_faces\":[");
    for (face = 0; face < 2u; ++face) {
        const Bridge *b = &sum.bridge[face];
        printf("%s{\"z\":%u,\"x\":%u,\"face\":0,"
               "\"present\":%s,\"wide_valid\":%s,"
               "\"pc_valid\":%s,\"ps1_model_valid\":%s,"
               "\"wide_direction\":%u,\"pc_direction\":%u,"
               "\"ps1_model_direction\":%u,"
               "\"wide_pc_equal\":%s,\"pc_ps1_equal\":%s}",
               face ? "," : "",b->z,b->x,b->present?"true":"false",
               b->full_valid?"true":"false",b->pc_valid?"true":"false",
               b->ps1_valid?"true":"false",
               b->full_direction,b->pc_direction,b->ps1_direction,
               b->full_pc_equal?"true":"false",
               b->pc_ps1_equal?"true":"false");
    }
    puts("],\"ps1_hardware_gte_verified\":false,"
         "\"camera_projection_verified\":false,"
         "\"raw_game_bytes_emitted\":false}");
    free(map);
    return 0;
}
