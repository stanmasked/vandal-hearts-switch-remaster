/* Real pinned PC-port libgte.c perspective projection regression.
 * It runs directly against the exact source used in the Switch NRO.
 * All vertices and camera parameters are synthetic, not original map11. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "PsyQ/libgte.h"
#include "inline_gte.h"

static int x_of(int xy) { return (short)(xy & 0xffff); }
static int y_of(int xy) { return (short)((unsigned)xy >> 16); }

int main(void) {
    SVECTOR rot = {-512, 0, 0, 0}; /* 45-degree pitch from map plane */
    SVECTOR model[4] = {
        {-32,0,-16,0}, {0,0,-16,0}, {0,0,24,0}, {-32,0,24,0},
    };
    MATRIX mat;
    VECTOR zoom = {0,0,96,0};
    int xy[4], p, flags, otz;
    memset(&mat,0,sizeof(mat));
    InitGeom();
    SetGeomOffset(6,4);
    SetGeomScreen(14);
    RotMatrix(&rot,&mat);
    TransMatrix(&mat,&zoom);
    SetRotMatrix(&mat);
    SetTransMatrix(&mat);
    otz = RotTransPers4(
        &model[0],&model[1],&model[2],&model[3],
        &xy[0],&xy[1],&xy[2],&xy[3],&p,&flags);
    printf("Original pinned GTE perspective: TL=(%d,%d) TR=(%d,%d) "
           "BL=(%d,%d) BR=(%d,%d), otz=%d flags=%x\n",
           x_of(xy[0]),y_of(xy[0]),x_of(xy[1]),y_of(xy[1]),
           x_of(xy[2]),y_of(xy[2]),x_of(xy[3]),y_of(xy[3]),otz,flags);
    assert(otz>0);
    assert(x_of(xy[0])>=0 && x_of(xy[0])<6);
    assert(x_of(xy[1])>=5 && x_of(xy[1])<=7);
    assert(y_of(xy[0])>=1 && y_of(xy[0])<=3);
    assert(y_of(xy[2])>=5 && y_of(xy[2])<=8);
    assert(x_of(xy[3])>x_of(xy[0])); /* perspective foreshortening */
    assert(y_of(xy[0])<y_of(xy[3]));
    assert(y_of(xy[1])<y_of(xy[2]));
    /* Repeating the same exact camera/matrix must be stable. */
    {
        int again[4], p2, flags2;
        int otz2 = RotTransPers4(
            &model[0],&model[1],&model[2],&model[3],
            &again[0],&again[1],&again[2],&again[3],&p2,&flags2);
        assert(otz2==otz);
        assert(memcmp(xy,again,sizeof(xy))==0);
        assert(p2==p && flags2==flags);
    }
    /* Original RenderMapTile culls signed GTE NCLIP area <= 0.
     * Reversing the two outer vertices reverses winding and sign.
     * This test uses the ORIGINAL pinned PC_GTE_NCLIP implementation. */
    {
        int front, back, depth;
        gte_ldv3(&model[0], &model[1], &model[2]);
        gte_rtpt();
        gte_nclip();
        gte_stopz(&front);
        assert(front > 0);
        gte_ldv3(&model[2], &model[1], &model[0]);
        gte_rtpt();
        gte_nclip();
        gte_stopz(&back);
        assert(back < 0);
        assert(back == -front);
        /* A fresh four-vertex RTPT + RTPS must retain AVSZ4 OTZ. */
        gte_ldv3(&model[0], &model[1], &model[2]);
        gte_rtpt();
        gte_ldv0(&model[3]);
        gte_rtps();
        gte_avsz4();
        gte_stotz(&depth);
        assert(depth == otz);
        printf("Original pinned GTE NCLIP front=%d reverse=%d AVSZ4=%d\\n",
               front,back,depth);
    }
    puts("PASS: pinned PS1 GTE perspective, signed NCLIP culling and AVSZ4 depth");
    return 0;
}
