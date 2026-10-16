#include "vh_private_map_normals.h"

#include <string.h>
#include "inline_gte.h"
#include "PsyQ/gtemac.h"

/* Count matching signs and EXACT component equality. The original
 * UpdateMapTileLighting tie branch uses this six-item score, not
 * a nearest-angle or floating-point tolerance. */
static int source_tie_score(const SVECTOR *face,
                            const SVECTOR *candidate) {
    const short f[3] = {face->vx,face->vy,face->vz};
    const short n[3] = {candidate->vx,candidate->vy,candidate->vz};
    int score = 0;
    unsigned k;
    for (k=0;k<3;++k) {
        if ((f[k]>0 && n[k]>0) || (f[k]<0 && n[k]<0))
            ++score;
        if (f[k]==n[k])
            ++score;
    }
    return score;
}

int vh_map_recompute_shade_indices(
    VhPreviewGeometry *geometry,
    const SVECTOR side_normals[VH_MAP_SIDE_NORMALS]) {
    VhPreviewGeometry updated;
    unsigned f, j, k;
    if (!geometry || !side_normals ||
        geometry->face_count > VH_MAP_MODEL_MAX_FACES)
        return -1;
    updated = *geometry;
    for (f=0;f<updated.face_count;++f) {
        VhPreviewFace *face=&updated.faces[f];
        VECTOR vec1={0},vec2={0},cross={0};
        SVECTOR face_normal={0};
        unsigned a=0,b=1,c=2;
        int best_dot=-0x1000000;
        int best_index=0;
        for(k=0;k<4;++k) {
            if(face->vertex_index[k]>=VH_MAP_MODEL_VERTICES)
                return -1;
        }

        /* Exactly the four fallback branches from the pinned
         * UpdateMapTileLighting source. The tests include repeated
         * original vertex IDs and zero-area cases. */
        if (face->vertex_index[0]==face->vertex_index[1]) {
            a=2; b=0; c=3;
        } else if (face->vertex_index[0]==face->vertex_index[2]) {
            a=1; b=0; c=3;
        } else if (face->vertex_index[0]==face->vertex_index[3]) {
            a=1; b=0; c=2;
        } else if (face->vertex_index[1]==face->vertex_index[2]) {
            a=1; b=0; c=3;
        }
        vec1.vx=(int)face->vertex[b][0]-(int)face->vertex[a][0];
        vec1.vy=(int)face->vertex[b][1]-(int)face->vertex[a][1];
        vec1.vz=(int)face->vertex[b][2]-(int)face->vertex[a][2];
        vec2.vx=(int)face->vertex[c][0]-(int)face->vertex[a][0];
        vec2.vy=(int)face->vertex[c][1]-(int)face->vertex[a][1];
        vec2.vz=(int)face->vertex[c][2]-(int)face->vertex[a][2];

        gte_OuterProduct0(&vec1,&vec2,&cross);
        VectorNormalS(&cross,&face_normal);

        for(j=0;j<VH_MAP_SIDE_NORMALS;++j) {
            int dot=(int)side_normals[j].vx*(int)face_normal.vx +
                    (int)side_normals[j].vy*(int)face_normal.vy +
                    (int)side_normals[j].vz*(int)face_normal.vz;
            if(dot>best_dot) {
                best_index=(int)j;
                best_dot=dot;
            } else if(dot==best_dot &&
                source_tie_score(&face_normal,&side_normals[j])>
                source_tie_score(&face_normal,
                                 &side_normals[best_index])) {
                best_index=(int)j;
            }
        }
        face->shade_index=(unsigned char)best_index;
    }
    memcpy(geometry,&updated,sizeof(updated));
    return 1;
}
