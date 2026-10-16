#include "vh_private_map_light.h"

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "inline_gte.h"
#include "PsyQ/gtemac.h"

/* Exact source-vector order from SetupLightNormals. */
static const signed char k_side_xyz[VH_MAP_SIDE_NORMALS][3] = {
    {0,1,0}, {0,-1,0}, {1,0,0}, {0,0,1}, {-1,0,0}, {0,0,-1},
    {1,0,-1}, {1,0,1}, {-1,0,1}, {-1,0,-1},
    {1,1,0}, {0,1,1}, {-1,1,0}, {0,1,-1},
    {1,1,-1}, {1,1,1}, {-1,1,1}, {-1,1,-1},
    {1,-1,0}, {0,-1,1}, {-1,-1,0}, {0,-1,-1},
    {1,-1,-1}, {1,-1,1}, {-1,-1,1}, {-1,-1,-1},
};

void vh_map_init_side_normals(SVECTOR output[VH_MAP_SIDE_NORMALS]) {
    unsigned i;
    for (i=0;i<VH_MAP_SIDE_NORMALS;i++) {
        VECTOR input = {0};
        input.vx = k_side_xyz[i][0];
        input.vy = k_side_xyz[i][1];
        input.vz = k_side_xyz[i][2];
        VectorNormalS(&input, &output[i]);
    }
}

/* Reproduces original UpdateLight's actual GTE NCCS operation and
 * integer RGB equation. Explicit caller-owned lighting parameters
 * avoid assuming real gState or global light settings. */
void vh_map_update_light(CVECTOR output[VH_MAP_SIDE_NORMALS],
                         const SVECTOR normals[VH_MAP_SIDE_NORMALS],
                         const SVECTOR *rotation, const CVECTOR *light_color,
                         int intensity, unsigned map_number) {
    static const unsigned char mirrored[][2] = {
        {3,5},{7,6},{8,9},{11,13},{15,14},
        {16,17},{19,21},{23,22},{24,25},
    };
    MATRIX mtx = {0};
    VECTOR direction;
    SVECTOR unit = {4096,0,0,0};
    CVECTOR mid = {128,128,128,0};
    CVECTOR response;
    int flag = 0;
    unsigned i;

    if (intensity < 0) intensity = 0;
    if (intensity > 128) intensity = 128;
    PushMatrix();
    RotMatrix((SVECTOR *)rotation, &mtx);
    mtx.t[0] = mtx.t[1] = mtx.t[2] = 0;
    SetRotMatrix(&mtx);
    SetTransMatrix(&mtx);
    RotTrans(&unit, &direction, &flag);
    mtx.m[0][0] = (short)-direction.vx;
    mtx.m[0][1] = (short)-direction.vy;
    mtx.m[0][2] = (short)-direction.vz;
    mtx.m[1][0] = mtx.m[1][1] = mtx.m[1][2] = 0;
    mtx.m[2][0] = mtx.m[2][1] = mtx.m[2][2] = 0;
    mtx.t[0] = mtx.t[1] = mtx.t[2] = 0;
    SetLightMatrix(&mtx);
    for (i=0;i<VH_MAP_SIDE_NORMALS;i++) {
        gte_NormalColorCol(&normals[i], &mid, &response);
        output[i].r=(unsigned char)(((int)light_color->r *
             (intensity + (((int)response.r * (128-intensity)) >> 7))) >> 7);
        output[i].g=(unsigned char)(((int)light_color->g *
             (intensity + (((int)response.g * (128-intensity)) >> 7))) >> 7);
        output[i].b=(unsigned char)(((int)light_color->b *
             (intensity + (((int)response.b * (128-intensity)) >> 7))) >> 7);
        output[i].cd=0;
    }
    PopMatrix();
    /* Original map 32 special case only, NOT applied to map 11. */
    if (map_number == 32u) {
        for(i=0;i<sizeof(mirrored)/sizeof(mirrored[0]);i++) {
            output[mirrored[i][1]]=output[mirrored[i][0]];
        }
    }
}

int vh_map_read_demo_intensity(const char *path, unsigned char *out) {
    FILE *f;
    int value, after, read_error;
    if (!path || !out) return -1;
    f=fopen(path,"rb");
    if (!f) return errno == ENOENT ? 0 : -1;
    value=fgetc(f);
    after=fgetc(f);
    read_error=ferror(f);
    fclose(f);
    if (read_error || value < 0 || value > 128 || after != EOF)
        return -1;
    *out=(unsigned char)value;
    return 1;
}
