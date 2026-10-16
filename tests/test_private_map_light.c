#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "PsyQ/libgte.h"
#include "../source/vh_private_map_light.h"

int main(void) {
    SVECTOR normals[VH_MAP_SIDE_NORMALS];
    CVECTOR colors[VH_MAP_SIDE_NORMALS], neutral[VH_MAP_SIDE_NORMALS];
    SVECTOR rotation = {0,0,0,0};
    CVECTOR light_base = {128,128,128,0};
    char root[]="/tmp/vh-side-light-XXXXXX";
    char path[256];
    unsigned char value=0xa5;
    unsigned i;
    FILE *fp;

    InitGeom();
    vh_map_init_side_normals(normals);
    assert(normals[0].vx==0 && normals[0].vy==4096);
    assert(normals[1].vy==-4096);
    assert(normals[2].vx==4096);
    assert(normals[4].vx==-4096);
    assert(normals[3].vz==4096);
    assert(normals[5].vz==-4096);
    assert(normals[25].vx<0 && normals[25].vy<0 && normals[25].vz<0);

    vh_map_update_light(neutral,normals,&rotation,&light_base,128,11);
    for(i=0;i<VH_MAP_SIDE_NORMALS;++i) {
        assert(neutral[i].r==128 && neutral[i].g==128 && neutral[i].b==128);
    }

    vh_map_update_light(colors,normals,&rotation,&light_base,32,11);
    /* Original UpdateLight illuminates along rotated negative X.
     * An exact -X normal receives full red NCCS; opposite +X has
     * only uniform ambient. Its G/B channels have ambient light. */
    assert(colors[4].r==128);
    assert(colors[4].g==32 && colors[4].b==32);
    assert(colors[2].r==32 && colors[2].g==32 && colors[2].b==32);
    assert(colors[4].r>colors[2].r);
    printf("Original 26-side GTE light demo: -X=(%u,%u,%u) "
           "+X=(%u,%u,%u)\n",
           colors[4].r,colors[4].g,colors[4].b,
           colors[2].r,colors[2].g,colors[2].b);

    assert(mkdtemp(root));
    assert(snprintf(path,sizeof(path),"%s/LIGHT_TEST_INTENSITY.BIN",root)
           < (int)sizeof(path));
    assert(vh_map_read_demo_intensity(path,&value)==0);
    assert(value==0xa5);
    fp=fopen(path,"wb");assert(fp);
    assert(fputc(32,fp)!=EOF);assert(fclose(fp)==0);
    assert(vh_map_read_demo_intensity(path,&value)==1 && value==32);
    fp=fopen(path,"wb");assert(fp);
    assert(fputc(129,fp)!=EOF);assert(fclose(fp)==0);
    assert(vh_map_read_demo_intensity(path,&value)==-1 && value==32);
    fp=fopen(path,"wb");assert(fp);
    assert(fputc(32,fp)!=EOF);assert(fputc(33,fp)!=EOF);
    assert(fclose(fp)==0);
    assert(vh_map_read_demo_intensity(path,&value)==-1 && value==32);
    assert(unlink(path)==0 && rmdir(root)==0);
    puts("PASS: original 26-normal GTE NCCS UpdateLight, neutral regression and SD opt-in");
    return 0;
}
