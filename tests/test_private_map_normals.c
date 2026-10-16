#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "PsyQ/libgte.h"
#include "../source/vh_private_map_normals.h"

static void face_set(VhPreviewFace *f,
                     const short xyz[4][3],
                     const unsigned char ids[4]) {
    unsigned j,k;
    memset(f,0,sizeof(*f));
    for(j=0;j<4;++j){
        f->vertex_index[j]=ids[j];
        for(k=0;k<3;++k) f->vertex[j][k]=xyz[j][k];
    }
    f->shade_index=25; /* deliberately incorrect until recompute */
}

int main(void) {
    SVECTOR normals[VH_MAP_SIDE_NORMALS];
    VhPreviewGeometry model={0},copy;
    static const unsigned char ids[4]={0,1,2,3};
    static const short up[4][3]={{0,0,0},{0,0,16},{16,0,16},{16,0,0}};
    static const short down[4][3]={{0,0,0},{16,0,0},{16,0,16},{0,0,16}};
    static const short plus_x[4][3]={{0,0,0},{0,16,0},{0,16,16},{0,0,16}};
    static const short minus_x[4][3]={{0,0,0},{0,0,16},{0,16,16},{0,16,0}};
    static const short repeated[4][3]={{0,0,0},{0,0,0},{16,0,0},{16,16,0}};
    static const unsigned char repeated_ids[4]={0,0,1,2};

    InitGeom();
    vh_map_init_side_normals(normals);
    model.face_count=5;
    face_set(&model.faces[0],up,ids);
    face_set(&model.faces[1],down,ids);
    face_set(&model.faces[2],plus_x,ids);
    face_set(&model.faces[3],minus_x,ids);
    face_set(&model.faces[4],repeated,repeated_ids);
    assert(vh_map_recompute_shade_indices(&model,normals)==1);
    assert(model.faces[0].shade_index==0); /* +Y */
    assert(model.faces[1].shade_index==1); /* -Y */
    assert(model.faces[2].shade_index==2); /* +X */
    assert(model.faces[3].shade_index==4); /* -X */
    assert(model.faces[4].shade_index==5); /* -Z, repeated ID fallback */
    assert(model.faces[4].vertex_index[1]==0);
    /* Every source SetupLightNormals direction is represented by one
     * distinct lattice-facing triangle, including all 20 diagonals.
     * Generate their winding geometrically (and verify classification),
     * instead of hand-picking an expected shade index in model data. */
    {
        static const signed char dirs[26][3]={
            {0,1,0},{0,-1,0},{1,0,0},{0,0,1},{-1,0,0},{0,0,-1},
            {1,0,-1},{1,0,1},{-1,0,1},{-1,0,-1},
            {1,1,0},{0,1,1},{-1,1,0},{0,1,-1},
            {1,1,-1},{1,1,1},{-1,1,1},{-1,1,-1},
            {1,-1,0},{0,-1,1},{-1,-1,0},{0,-1,-1},
            {1,-1,-1},{1,-1,1},{-1,-1,1},{-1,-1,-1},
        };
        unsigned direction;
        for(direction=0;direction<26;++direction) {
            short p[4][3]={{0}};
            unsigned axis=dirs[direction][0] ? 0u : 1u;
            unsigned other=(axis+1u)%3u;
            unsigned third=(axis+2u)%3u;
            const unsigned char ids2[4]={0,1,2,3};
            VhPreviewGeometry candidate={0};
            int cross_sign;
            /* Choose two perpendicular tangents where
             * tangent0 x tangent1 aligns with target lattice vector.
             * For lattice vector n, tangent0=(n_other,-n_axis,0)
             * on the selected axes, tangent1=n x tangent0.
             */
            int n[3]={dirs[direction][0],dirs[direction][1],dirs[direction][2]};
            int t0[3]={0},t1[3];
            t0[axis]=n[other];
            t0[other]=-n[axis];
            if(!t0[axis] && !t0[other]) {
                t0[other]=n[third];
                t0[third]=-n[other];
            }
            t1[0]=n[1]*t0[2]-n[2]*t0[1];
            t1[1]=n[2]*t0[0]-n[0]*t0[2];
            t1[2]=n[0]*t0[1]-n[1]*t0[0];
            for(cross_sign=0;cross_sign<3;++cross_sign) {
                p[1][cross_sign]=(short)(t1[cross_sign]*16);
                p[2][cross_sign]=(short)((t1[cross_sign]+t0[cross_sign])*16);
                p[3][cross_sign]=(short)(t0[cross_sign]*16);
            }
            candidate.face_count=1;
            face_set(&candidate.faces[0],
                     (const short (*)[3])p,ids2);
            assert(vh_map_recompute_shade_indices(&candidate,normals)==1);
            assert(candidate.faces[0].shade_index==direction);
        }
        puts("PASS: all 26 source vector directions classify identically");
    }
    /* A geometrically zero-area polygon has the source's zero-normal
     * Q12 vector and must select the earliest equal-dot winner: 0.
     * Repeated original indices select a fallback but cannot invent
     * a normal when all four vertex coordinates coincide. */
    {
        VhPreviewGeometry degenerate={0};
        short zeros[4][3]={{0}};
        unsigned char indices[4]={0,0,0,0};
        degenerate.face_count=1;
        face_set(&degenerate.faces[0],(const short (*)[3])zeros,indices);
        assert(vh_map_recompute_shade_indices(&degenerate,normals)==1);
        assert(degenerate.faces[0].shade_index==0);
    }

    copy=model;
    copy.faces[3].vertex_index[2]=22;
    {
        VhPreviewGeometry bad=copy;
        assert(vh_map_recompute_shade_indices(&copy,normals)==-1);
        assert(memcmp(&copy,&bad,sizeof(copy))==0);
    }
    assert(vh_map_recompute_shade_indices(NULL,normals)==-1);
    assert(vh_map_recompute_shade_indices(&model,NULL)==-1);
    copy=model; copy.face_count=19;
    assert(vh_map_recompute_shade_indices(&copy,normals)==-1);

    puts("PASS: original UpdateMapTileLighting GTE OP0, 26-way dot, repeated IDs and transactional invalid handling");
    return 0;
}
