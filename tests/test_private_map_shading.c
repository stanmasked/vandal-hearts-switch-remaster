/* Source-exact RenderMapTile distance attenuation, no game bytes. */
#include <assert.h>
#include <stdio.h>
#include "../source/vh_private_map_shading.h"

static int reference(unsigned side,int otz) {
    int shade=otz-150;
    if(shade<0)shade=0;
    if(shade>256)shade=256;
    return (int)side-((int)side*shade>>8);
}
int main(void) {
    static const int depths[] = {-50,0,24,49,149,150,151,192,255,405,406,800};
    static const unsigned bases[] = {0,1,20,64,128,200,255};
    unsigned i,j;
    for(i=0;i<sizeof(depths)/sizeof(depths[0]);++i){
        for(j=0;j<sizeof(bases)/sizeof(bases[0]);++j){
            unsigned char output=vh_map_distance_component(
                (unsigned char)bases[j],depths[i]);
            assert(output==(unsigned)reference(bases[j],depths[i]));
            assert(output<=bases[j]);
        }
    }
    assert(vh_map_distance_component(128,24)==128);
    assert(vh_map_distance_component(128,49)==128);
    assert(vh_map_distance_component(128,150)==128);
    assert(vh_map_distance_component(128,406)==0);
    assert(vh_map_distance_component(255,278)==128);
    printf("PASS: exact RenderMapTile OTZ distance attenuation over %zu cases\n",
           (sizeof(depths)/sizeof(depths[0]))*(sizeof(bases)/sizeof(bases[0])));
    return 0;
}
