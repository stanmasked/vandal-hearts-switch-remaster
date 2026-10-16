#!/usr/bin/env python3
"""V47: capture all map-11 faces at their EXACT freshly minted OT token.

Apply after v39, v40 and v41 in a disposable pinned PC-port checkout.
Sidecar has (z,x,face), not a texture-only guess; rasterizer is unchanged.
"""
from pathlib import Path
import argparse
import subprocess

PIN="14552fffa0e0b47e02b57592e274fc6e7a649923"
GRAPHICS="src/core/graphics.c"
GPU="platform/pc/src/libgpu.c"

def once(src, old, new, label):
    count=src.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one exact anchor, got {count}")
    return src.replace(old,new,1)

def patch_graphics(src):
    if "PC_Map02V47MarkSubmitted" in src:
        raise ValueError("v47 already installed")
    declaration = String = (
        '#if defined(PC_FEAT) && defined(VH_MAP02_V39_TRACE)\n'
        'extern void PC_Map02V47MarkSubmitted(void *, void *, int, int, int);\n'
        '/* One exact decoded MapTileModel pointer, including duplicate GFX. */\n'
        'static void VhMap02V47TagFace(void *ot, void *poly, const MapTileModel *tile, int face) {\n'
        '    int z, x;\n'
        '    if (gState.mapNum != 11 || !tile || face < 0 || face >= 18) return;\n'
        '    for (z = 0; z < 12; ++z) {\n'
        '        if (!gMapRowPointers[z]) continue;\n'
        '        for (x = 0; x < 28; ++x) {\n'
        '            if (tile == &gMapRowPointers[z][x]) {\n'
        '                PC_Map02V47MarkSubmitted(ot, poly, z, x, face);\n'
        '                return;\n'
        '            }\n'
        '        }\n'
        '    }\n'
        '}\n'
        '#endif\n'
    )
    src=once(src,
        'extern void PC_Map02V39MarkSubmitted(void *, void *, int, int, int);\n',
        'extern void PC_Map02V39MarkSubmitted(void *, void *, int, int, int);\n'
        + declaration, "graphics helper declaration")
    sections=[
        ("RenderMapTile","RenderEdgeMapTile",1),
        ("RenderEdgeMapTile","RenderOverheadMapTile",2),
        ("RenderOverheadMapTile","GetBestViewOfTarget",3),
    ]
    for name,next_name,route in sections:
        begin=src.find("void "+name+"(")
        end=src.find(("\ns32 " if route==3 else "\nvoid ")+next_name+"(",begin)
        if begin < 0 or end < begin:
            raise ValueError("missing terrain function bounds: "+name)
        body=src[begin:end]
        old=(f"            PC_Map02V39MarkSubmitted(ot + OT_SIZE - otz, poly, gfx, (int)gState.mapNum, {route});")
        if body.count(old)!=1:
            raise ValueError("expected one original MarkSubmitted call in "+name)
        body=body.replace(old,old+"\n"
             "         if (gState.mapNum == 11)\n"
             "            VhMap02V47TagFace(ot + OT_SIZE - otz, poly, tileModel, faceIdx);",1)
        src=src[:begin]+body+src[end:]
    return src

def patch_gpu(src):
    if "PC_Map02V47MarkSubmitted" in src:
        raise ValueError("v47 already installed")
    if "s_v39Tags[PC_OT_MAX_TOKENS]" not in src:
        raise ValueError("v39 OT provenance must be installed first")
    src=once(src,
        'static VhMap02V39Tag s_v39Tags[PC_OT_MAX_TOKENS];',
        'static VhMap02V39Tag s_v39Tags[PC_OT_MAX_TOKENS];\n'
        'typedef struct { unsigned short z,x,face; unsigned char valid; } VhMap02V47Face;\n'
        'static VhMap02V47Face s_v47Faces[PC_OT_MAX_TOKENS];',
        "v47 separate OT-token sidecar")
    src=once(src,
        '    vh_map02_v39_clear(s_v39Tags, PC_OT_MAX_TOKENS, s_otTokens);',
        '    vh_map02_v39_clear(s_v39Tags, PC_OT_MAX_TOKENS, s_otTokens);\n'
        '    s_v47Faces[s_otTokens].valid = 0;',
        "clear v47 provenance whenever token is reused")
    caller=(
        '\n/* Map-11 decoded tile identity, bound ONLY to the latest AddPrim token. */\n'
        'void PC_Map02V47MarkSubmitted(void *ot, void *prim, int z, int x, int face) {\n'
        '    unsigned int token;\n'
        '    if (!ot || !prim || z < 0 || z >= 12 || x < 0 || x >= 28 ||\n'
        '        face < 0 || face >= 18 || !s_otTokens || s_otTokens >= PC_OT_MAX_TOKENS)\n'
        '        return;\n'
        '    token = ((P_TAG *)ot)->tag;\n'
        '    if (token != s_otTokens || s_otPtr[token] != prim ||\n'
        '        s_otIsBucket[token] || !s_v39Tags[token].valid) return;\n'
        '    s_v47Faces[token].z = (unsigned short)z;\n'
        '    s_v47Faces[token].x = (unsigned short)x;\n'
        '    s_v47Faces[token].face = (unsigned short)face;\n'
        '    s_v47Faces[token].valid = 1;\n'
        '}\n'
    )
    src=once(src,
        '/* Tag precisely the token most recently emitted by AddPrim, not UV/CLUT. */',
        caller+"\n/* Tag precisely the token most recently emitted by AddPrim, not UV/CLUT. */",
        "v47 producer binding API")
    target=(
        '                    VH_Map02V39Active = 1;\n'
        '                    fprintf(stderr,'
    )
    enhanced=(
        '                    VH_Map02V39Active = 1;\n'
        '                    if (s_v47Faces[nextTok].valid) {\n'
        '                        const VhMap02V47Face *faceInfo = &s_v47Faces[nextTok];\n'
        '                        fprintf(stderr,\n'
        '                            "[v47-terrain-face-ot] f=%u token=%u z=%u x=%u face=%u gfx=%u route=%u tpage=%u clut=%u u=%u v=%u\\n",\n'
        '                            s_drawFrame, nextTok,\n'
        '                            (unsigned)faceInfo->z, (unsigned)faceInfo->x,\n'
        '                            (unsigned)faceInfo->face,\n'
        '                            v39Tag.gfx, v39Tag.route,\n'
        '                            (unsigned)q->tpage, (unsigned)q->clut,\n'
        '                            (unsigned)q->u0, (unsigned)q->v0);\n'
        '                    }\n'
        '                    fprintf(stderr,'
    )
    src=once(src,target,enhanced,"read actual FT4 and frame when DrawOTag reaches token")
    return src

def apply(root):
    rev=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if rev!=PIN:
        raise ValueError(f"need pinned public PC source {PIN}; got {rev}")
    changes={GRAPHICS:patch_graphics((root/GRAPHICS).read_text()),
             GPU:patch_gpu((root/GPU).read_text())}
    for path,content in changes.items():
        (root/path).write_text(content)
    print("v47 enabled: all map-11 producer faces uniquely bound to OT token")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("upstream",type=Path)
    p.add_argument("--apply",action="store_true")
    a=p.parse_args()
    if not a.apply:
        p.error("will not modify source checkout without --apply")
    apply(a.upstream.resolve(strict=True))

if __name__=="__main__":
    main()
