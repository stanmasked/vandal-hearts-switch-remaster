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
