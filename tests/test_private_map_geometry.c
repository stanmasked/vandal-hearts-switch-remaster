#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "../source/vh_private_map_geometry.h"

static void put16(uint8_t *data, size_t offset, int n) {
    unsigned word = (unsigned)(uint16_t)n;
    data[offset] = (uint8_t)(word & 255u);
    data[offset + 1] = (uint8_t)(word >> 8);
}
static void write_data(const char *path, const void *data, size_t n) {
    FILE *f = fopen(path, "wb");
    assert(f);
    assert(fwrite(data, 1, n, f) == n);
    assert(fclose(f) == 0);
}
int main(void) {
    char dir[] = "/tmp/vh-geometry-XXXXXX";
    char path[256];
    uint8_t *src = (uint8_t *)calloc(VH_MAP_MODEL_TOTAL, 1);
    VhPreviewGeometry *out = (VhPreviewGeometry *)malloc(sizeof(*out));
    const int xyz[8][3] = {
        {-32,0,-16},{0,0,-16},{-32,0,24},{0,0,24},
        {0,0,-16},{32,0,-16},{0,0,24},{32,0,24}
    };
    size_t base = ((3u * VH_MAP_MODEL_COLS) + 6u) * VH_MAP_MODEL_BYTES;
    unsigned i,j;
    assert(mkdtemp(dir) && src && out);
    assert(snprintf(path, sizeof(path), "%s/MAP11_MODELS_28X12.BIN", dir)
           < (int)sizeof(path));
    memset(out, 0xa5, sizeof(*out));
    assert(vh_private_map_geometry_load(path,6,3,out)==0);
    assert(out->face_count==0xa5);
    for (i=0;i<8;++i) {
        for (j=0;j<3;++j)
            put16(src, base+i*8+j*2, xyz[i][j]);
    }
    put16(src,base+176,241);
    put16(src,base+178,242);
    { const uint8_t source_order[8] = {0,1,3,2,4,5,7,6};
      for (i=0;i<8;++i) src[base+212+i]=source_order[i]; }
    src[base+284]=1;
    src[base+285]=2;
    src[base+302]=2;
    src[base+303]=4;
    write_data(path,src,VH_MAP_MODEL_TOTAL);
    assert(vh_private_map_geometry_load(path,6,3,out)==1);
    assert(out->face_count==2);
    assert(out->tile_height==4);
    assert(out->faces[0].local_gfx==241 && out->faces[1].local_gfx==242);
    assert(out->faces[0].vertex[0][0]==-32);
    assert(out->faces[0].vertex[0][2]==-16);
    assert(out->faces[1].vertex[2][0]==32);
    assert(out->faces[1].vertex[3][0]==0);
    assert(out->faces[1].vertex[3][2]==24);
    assert(out->faces[0].shade_index==1);
    assert(out->faces[1].shade_index==2);

    memset(out,0xa5,sizeof(*out));
    assert(vh_private_map_geometry_load(path,28,3,out)==-1);
    assert(vh_private_map_geometry_load(path,6,12,out)==-1);
    assert(vh_private_map_geometry_load(path,6,3,NULL)==-1);
    assert(vh_private_map_geometry_load(NULL,6,3,out)==-1);
    assert(out->face_count==0xa5);
    write_data(path,src,VH_MAP_MODEL_TOTAL-1);
    assert(vh_private_map_geometry_load(path,6,3,out)==-1);
    assert(out->face_count==0xa5);
    /* Fail closed even if an UNUSED tile elsewhere has bad topology. */
    src[302]=19;
    write_data(path,src,VH_MAP_MODEL_TOTAL);
    assert(vh_private_map_geometry_load(path,6,3,out)==-1);
    src[302]=0;
    src[base+212]=22;
    write_data(path,src,VH_MAP_MODEL_TOTAL);
    assert(vh_private_map_geometry_load(path,6,3,out)==-1);
    src[base+212]=0;
    write_data(path,src,VH_MAP_MODEL_TOTAL);
    assert(vh_private_map_geometry_load(path,6,3,out)==1);
    assert(unlink(path)==0 && rmdir(dir)==0);
    free(src);
    free(out);
    puts("PASS: original 304-byte MapTileModel two-face SD loader, all topology corruption gates");
    return 0;
}
