#!/usr/bin/env python3
"""Synthetic NeXium SD texture: four UV quadrants, original PS1 4bpp/CLUT.

The staged DAT resources are generated from scratch, never from game assets.
Four distinct colored quadrants catch swapped U/V, reversed axes, wrong
texture-page offsets, wrong 4bpp nibble order and incorrect local CLUT row.
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from inspect_vh_map_texture_bank import LAND_BYTES, MAP_RECORD_BYTES, TEXTURE_BYTES
from stage_vh_private_map_bank import stage_private_assets

MAP_NUMBER = 11
MAP_SLOT = 241
U0, V0, WIDTH, HEIGHT = 240, 192, 15, 15
CLUT_ID = 35
COLORS_BGR555 = (0, 0x001f, 0x03e0, 0x7c00, 0x03ff)

# Deep inside each rendered quadrant, away from raster edge interpolation.
SCREEN_SAMPLES = (
    ("upper-left red", (400, 205), (255, 0, 0)),
    ("upper-right green", (880, 205), (0, 255, 0)),
    ("lower-left blue", (400, 510), (0, 0, 255)),
    ("lower-right yellow", (880, 510), (255, 255, 0)),
)


def synthetic_source():
    """Construct a 256x256 4bpp source page and one 1797-byte map record."""
    tex = bytearray(TEXTURE_BYTES)
    land = bytearray(LAND_BYTES)
    record = MAP_NUMBER * MAP_RECORD_BYTES
    land[record + MAP_SLOT * 4:record + MAP_SLOT * 4 + 4] = bytes(
        (U0, V0, WIDTH, HEIGHT)
    )
    land[record + 257 * 4 + MAP_SLOT] = CLUT_ID
    palette = record + 257 * 5 + (CLUT_ID - 32) * 32
    for index, color in enumerate(COLORS_BGR555):
        land[palette + 2 * index:palette + 2 * index + 2] = color.to_bytes(
            2, "little"
        )
    # A second, independently authored face uses slot 242 / CLUT ID 36
    # in a DIFFERENT source page rectangle. The single-patch scene still
    # uses only slot 241, so its existing four-color proof is unchanged.
    land[record + 242 * 4:record + 242 * 4 + 4] = bytes((224,192,15,15))
    land[record + 257 * 4 + 242] = 36
    alternate = record + 257 * 5 + (36 - 32) * 32
    land[alternate + 2:alternate + 6] = bytes((0x1f,0x7c,0xe0,0x7f))
    for v in range(192, 208):
        for u in range(224, 240, 2):
            index = 1 if v < 200 else 2
            tex[v * 128 + u // 2] = index | (index << 4)
    # Each 16x16 UV patch has four 8x8 squares. The low 4 bits of
    # every byte are the LEFT pixel; upper nibble encodes the RIGHT.
    for v in range(V0, V0 + 16):
        for u in range(U0, U0 + 16, 2):
            top = v < V0 + 8
            left = u < U0 + 8
            color_id = (1 if left else 2) if top else (3 if left else 4)
            tex[v * 128 + u // 2] = color_id | (color_id << 4)
    return bytes(tex), bytes(land)


def synthetic_geometry_models():
    """336 exact 304-byte map tiles; tile (6,3) has TWO textured faces."""
    from inspect_vh_map_geometry import (
        MAP_11_BYTES, MAP_11_STRIDE, TILE_BYTES, VERTICES_BYTES,
        GFX_BYTES, FACE_BYTES,
    )
    models = bytearray(MAP_11_BYTES)
    tile_base = (3 * MAP_11_STRIDE + 6) * TILE_BYTES
    points = (
        (-32, 0, -16), (0, 0, -16), (-32, 0, 24), (0, 0, 24),
        (0, 0, -16), (32, 0, -16), (0, 0, 24), (32, 0, 24),
    )
    for i, (vx, vy, vz) in enumerate(points):
        models[tile_base + i * 8:tile_base + i * 8 + 8] = (
            int(vx).to_bytes(2, "little", signed=True) +
            int(vy).to_bytes(2, "little", signed=True) +
            int(vz).to_bytes(2, "little", signed=True) + bytes(2)
        )
    # FIRST a reversed backface over the left rectangle (slot 242
    # would tint it magenta/cyan if it slipped through NCLIP). Insert
    # it before the two visible faces so, without culling, head-linked
    # GPU primitives would draw it LAST and corrupt the red/blue probe.
    # RenderMapTile source vertex 2 maps to FT4 packet corner 3.
    for n, (gfx, ids) in enumerate((
        (242, (1,0,2,3)),       # backfacing, MUST be rejected
        (241, (0,1,3,2)),       # visible left red/blue
        (242, (4,5,7,6)),       # visible right magenta/cyan
    )):
        gfx_at = tile_base + VERTICES_BYTES + n * 2
        models[gfx_at:gfx_at + 2] = gfx.to_bytes(2, "little")
        faces_at = tile_base + VERTICES_BYTES + GFX_BYTES + n * 4
        models[faces_at:faces_at + 4] = bytes(ids)
        models[tile_base + VERTICES_BYTES + GFX_BYTES +
               FACE_BYTES + n] = n + 1
    models[tile_base + TILE_BYTES - 2] = 3
    models[tile_base + TILE_BYTES - 1] = 4
    return bytes(models)


def synthetic_depth_geometry_models():
    """Two overlapping source-format faces with intentionally reversed OT order.

    Face 0 is FAR (magenta/cyan, slot 242), face 1 is NEAR
    (red/blue, slot 241). Near is inserted LAST, so a one-bucket
    head-linked DrawOTag would paint the far face on TOP. The real
    OTZ-indexed buckets must instead draw FAR then NEAR.
    The far rectangle is scaled by 2 in camera space, using the
    inverse of the pinned -45-degree pitch plus translation (0,0,96):
    world far = 2*near + (0,-68,68). Its screen footprint nearly
    coincides with near, but its OTZ is about twice as large.
    """
    from inspect_vh_map_geometry import (
        MAP_11_BYTES, MAP_11_STRIDE, TILE_BYTES,
        VERTICES_BYTES, GFX_BYTES, FACE_BYTES,
    )
    models = bytearray(MAP_11_BYTES)
    base = (3 * MAP_11_STRIDE + 6) * TILE_BYTES
    near = (
        (-32,0,-16), (0,0,-16), (0,0,24), (-32,0,24),
    )
    far = tuple((2*x,2*y-68,2*z+68) for x,y,z in near)
    points = far + near
    for i, xyz in enumerate(points):
        for k, value in enumerate(xyz):
            offset = base + i*8 + 2*k
            models[offset:offset+2] = int(value).to_bytes(
                2, "little", signed=True
            )
    for n, (slot, indices) in enumerate((
        (242, (0,1,2,3)), # far first, should be behind
        (241, (4,5,6,7)), # near last, should be in front
    )):
        offset = base + VERTICES_BYTES + n*2
        models[offset:offset+2] = slot.to_bytes(2,"little")
        face_offset = base + VERTICES_BYTES + GFX_BYTES + n*4
        models[face_offset:face_offset+4] = bytes(indices)
        models[base + VERTICES_BYTES + GFX_BYTES +
               FACE_BYTES + n] = 1
    models[base + TILE_BYTES - 2] = 2
    return bytes(models)


def stage_depth(sd_root):
    """Keep depth-sort emulation independent from the legacy SD fixture."""
    from stage_vh_private_map_geometry import stage_map11_geometry
    bank = stage(sd_root)
    geometry = stage_map11_geometry(synthetic_depth_geometry_models(), sd_root)
    assert bank["local_clut_id"] == 35
    assert geometry["active_faces"] == 2
    print("Staged far-FIRST near-LAST map11 depth-occlusion test")
    return geometry


def synthetic_distant_shading_models():
    """One face deep enough to trigger source RenderMapTile OTZ fade.

    Scale the same near left quad 8x in camera space. The inverse test
    -45 degree pitch shifts source Y by -68*(8-1) and source Z by
    +68*(8-1). GTE OTZ becomes roughly 8*24 ~= 192, above the
    original game's distance fade threshold of 150.
    """
    from inspect_vh_map_geometry import (
        MAP_11_BYTES, MAP_11_STRIDE, TILE_BYTES,
        VERTICES_BYTES, GFX_BYTES,
    )
    models=bytearray(MAP_11_BYTES)
    base=(3*MAP_11_STRIDE+6)*TILE_BYTES
    near=((-32,0,-16),(0,0,-16),(0,0,24),(-32,0,24))
    distant=tuple((8*x,8*y-476,8*z+476) for x,y,z in near)
    for i,xyz in enumerate(distant):
        for k,value in enumerate(xyz):
            offset=base+8*i+2*k
            models[offset:offset+2]=int(value).to_bytes(
                2,"little",signed=True
            )
    models[base+VERTICES_BYTES:base+VERTICES_BYTES+2]=(242).to_bytes(2,"little")
    idx=base+VERTICES_BYTES+GFX_BYTES
    models[idx:idx+4]=bytes((0,1,2,3))
    models[base+TILE_BYTES-2]=1
    return bytes(models)


def stage_distance(sd_root):
    from stage_vh_private_map_geometry import stage_map11_geometry
    stage(sd_root)
    metadata=stage_map11_geometry(synthetic_distant_shading_models(),sd_root)
    assert metadata["active_faces"]==1
    print("Staged distant face: OTZ > 150 must dim magenta/cyan")
    return metadata


def synthetic_derived_shade_models():
    """Two visible sloping quads with opposite X-facing components.

    Original UpdateMapTileLighting must compute two DIFFERENT normal
    IDs from these vertices and override intentionally incorrect
    source shade bytes. The invisible third backface remains unchanged.
    """
    from inspect_vh_map_geometry import (
        MAP_11_STRIDE,TILE_BYTES,VERTICES_BYTES,GFX_BYTES,FACE_BYTES
    )
    models=bytearray(synthetic_geometry_models())
    base=(3*MAP_11_STRIDE+6)*TILE_BYTES
    # Left near-right vertices dip (negative X normal).
    # Right far-right vertices rise (positive X normal).
    for index, height in ((1,-16),(3,-16),(5,16),(7,16)):
        p=base+index*8+2
        models[p:p+2]=int(height).to_bytes(2,"little",signed=True)
    shade=base+VERTICES_BYTES+GFX_BYTES+FACE_BYTES
    models[shade+1]=2  # deliberately incorrect (+X)
    models[shade+2]=4  # deliberately incorrect (-X)
    return bytes(models)


def stage_derived_shades(sd_root):
    """Private fixture: dynamically derive shaders from terrain normals."""
    from stage_vh_private_map_geometry import stage_map11_geometry
    from stage_vh_private_map_bank import RELATIVE_DESTINATION
    stage(sd_root)
    metadata=stage_map11_geometry(synthetic_derived_shade_models(),sd_root)
    path=Path(sd_root)/RELATIVE_DESTINATION
    (path/"LIGHT_TEST_INTENSITY.BIN").write_bytes(bytes((32,)))
    (path/"LIGHT_RECOMPUTE_SHADES.BIN").write_bytes(bytes((1,)))
    assert metadata["active_faces"]==3
    print("Staged tilted source quads: dynamic OP0 side normal derivation")
    return metadata


def stage_side_lighting(sd_root):
    """Opt into real 26-normal GTE NCCS with a PRIVATE one-byte fixture.

    Same synthetic 3-face NCLIP scene; visible left face uses normal 4
    (-X, directional red brighter) and right normal 2 (+X, ambient only).
    No real map-light state is implied.
    """
    from inspect_vh_map_geometry import MAP_11_STRIDE,TILE_BYTES,VERTICES_BYTES,GFX_BYTES,FACE_BYTES
    from stage_vh_private_map_geometry import stage_map11_geometry
    from stage_vh_private_map_bank import RELATIVE_DESTINATION
    stage(sd_root)
    data=bytearray(synthetic_geometry_models())
    base=(3*MAP_11_STRIDE+6)*TILE_BYTES
    shade=base+VERTICES_BYTES+GFX_BYTES+FACE_BYTES
    data[shade+1]=4
    data[shade+2]=2
    report=stage_map11_geometry(bytes(data),sd_root)
    assert report["active_faces"]==3
    path=Path(sd_root)/RELATIVE_DESTINATION/"LIGHT_TEST_INTENSITY.BIN"
    if path.exists() or path.is_symlink():
        raise FileExistsError("private light intensity already exists")
    path.write_bytes(bytes((32,)))
    print("Staged original GTE NCCS 26-normal light: intensity 32, -X and +X")
    return report


def stage_geometry(sd_root):
    from stage_vh_private_map_geometry import stage_map11_geometry
    metadata = stage_map11_geometry(synthetic_geometry_models(), sd_root)
    assert metadata["active_faces"] == 3
    assert metadata["populated_tiles"] == 1
    print("Staged two FRONT faces and one REVERSED NCLIP regression face")
    return metadata

def stage(sd_root):
    texture, land = synthetic_source()
    report = stage_private_assets(texture, land, sd_root)
    assert report["uvwh"] == [U0, V0, WIDTH, HEIGHT]
    assert report["local_clut_id"] == CLUT_ID
    print("Synthetic four-quadrant map texture staged under:", sd_root)
    return report


def check(image_path):
    from PIL import Image

    frame = Image.open(image_path).convert("RGB")
    if frame.size != (1280, 720):
        raise ValueError("unexpected NeXium screenshot dimensions")
    # Baseline scene puts a RED tile at (210,90); private preview leaves
    # that area BLACK (the NRO sets a black tile first).
    border = frame.getpixel((210, 90))
    if max(border) > 45:
        raise ValueError(f"expected black private-preview border, got {border}")
    # All four samples are in the interior of the FT4 textured patch;
    # no screenshot-wide color histogram or generic colored UI can
    # satisfy these UV/CLUT-specific samples.
    for name, (x, y), expected in SCREEN_SAMPLES:
        observed = frame.getpixel((x, y))
        print(f"Original private SD FT4 {name}: {observed}")
        if max(abs(c - e) for c, e in zip(observed, expected)) > 36:
            raise ValueError(
                f"wrong private SD UV mapping/CLUT for {name}: "
                f"expected {expected}, got {observed}"
            )
    # Sample frame center separately to reject a stale baseline capture.
    center = frame.getpixel((640, 360))
    if max(center) < 175:
        raise ValueError(f"private preview center is not textured: {center}")
    print("Four-quadrant private SD FT4 screenshot verified")
    return True



def check_geometry(image_path):
    from PIL import Image
    frame = Image.open(image_path).convert("RGB")
    if frame.size != (1280, 720):
        raise ValueError("unexpected private geometry screenshot size")
    # Actual pinned GTE RTPT/RTPS perspective (not old orthographic
    # projection): with pitch -512, H=14, Z=96, the first face projects
    # TL=(0,1), TR=(6,1), BL=(2,6), BR=(6,6) in native 12x9 pixels.
    # The formerly checked (210,90) now LIES INSIDE the upper quad.
    border = frame.getpixel((50, 40))
    if max(border) > 45:
        raise ValueError("GTE geometry upper border is not black")
    probes = (
        ("left top red", (260,210), (255,0,0)),
        ("right top magenta", (850,210), (255,0,255)),
        ("left bottom blue", (400,400), (0,0,255)),
        ("right bottom cyan", (850,400), (0,255,255)),
        # Old orthographic geometry began at native (2,2), around
        # screen (320,160); genuine GTE projection puts a red top
        # edge at (300,125), which the former scene left black.
        ("perspective-only red upper edge", (300,125), (255,0,0)),
    )
    for title, (x,y), expected in probes:
        pixel = frame.getpixel((x,y))
        print("Original geometry FT4", title, pixel)
        if max(abs(a-b) for a,b in zip(pixel,expected)) > 36:
            raise ValueError(f"wrong {title} : {pixel}, expected {expected}")
    print("Private SD MapTileModel two-face geometry screenshot verified")
    return True


def check_depth(image_path):
    from PIL import Image

    frame = Image.open(image_path).convert("RGB")
    if frame.size != (1280,720):
        raise ValueError("unexpected OTZ depth screenshot dimensions")
    # Center samples lie in both overlapping source rectangles, unlike
    # the green/magenta standalone single-patch case. The NEAR face
    # must win despite being inserted last into the graph.
    samples = (
        ("near red covers far magenta", (260,210), (255,0,0)),
        ("near blue covers far cyan", (400,400), (0,0,255)),
        ("depth scene right remains empty", (850,210), (6,6,8)),
    )
    for title, (x,y), expected in samples:
        actual=frame.getpixel((x,y))
        print("OTZ overlap",title,actual)
        if max(abs(a-b) for a,b in zip(actual,expected))>28:
            raise ValueError(f"wrong OTZ occlusion for {title}: {actual}")
    print("Original GTE depth-sorted far/near overlap verified")
    return True


def check_distance(image_path):
    from PIL import Image

    frame=Image.open(image_path).convert("RGB")
    if frame.size!=(1280,720):
        raise ValueError("unexpected distance shading screenshot size")
    for label,(x,y),channels in (
        ("faded magenta",(260,210),(0,2)),
        ("faded cyan",(400,400),(1,2)),
    ):
        rgb=frame.getpixel((x,y))
        print("OTZ distance attenuation",label,rgb)
        if any(not (150<=rgb[c]<=245) for c in channels):
            raise ValueError(f"distance color channel not attenuated: {label} {rgb}")
        if any(rgb[c]>40 for c in range(3) if c not in channels):
            raise ValueError(f"distance color leaks unexpected channels: {label} {rgb}")
    print("Source RenderMapTile far-distance shading verified in NeXium")
    return True


def check_side_lighting(image_path):
    from PIL import Image
    frame=Image.open(image_path).convert("RGB")
    if frame.size!=(1280,720):
        raise ValueError("unexpected 26-normal lighting screenshot dimensions")
    samples=(
        ("-X direct-lit red", (260,210), (255,0,0)),
        ("-X ambient-only blue", (400,400), (0,0,64)),
        ("+X ambient magenta", (850,210), (64,0,64)),
        ("+X ambient cyan", (850,400), (0,64,64)),
    )
    for title,(x,y),expected in samples:
        pixel=frame.getpixel((x,y))
        print("Original 26-normal GTE NCCS",title,pixel)
        if max(abs(a-b) for a,b in zip(pixel,expected))>12:
            raise ValueError(f"wrong face lighting {title}: {pixel} expected {expected}")
    print("Pinned GTE NCCS per-side color lighting verified on synthetic map")
    return True


def check_derived_shades(image_path):
    from PIL import Image
    frame=Image.open(image_path).convert("RGB")
    if frame.size!=(1280,720):
        raise ValueError("incorrect dynamically-lit frame size")
    # A near-white or dark fake renderer cannot reproduce both values.
    # The left face's -X-facing normal must be brighter than the
    # right face's +X-facing normal, with both ABOVE pure background.
    left=frame.getpixel((260,210))
    right=frame.getpixel((850,210))
    print("Derived GTE OP0 normals left red / right magenta",left,right)
    if not (100<=left[0]<=245 and left[1]<=15 and left[2]<=15):
        raise ValueError(f"left auto-shaded face missing or wrong: {left}")
    if not (35<=right[0]<=95 and right[1]<=15 and 35<=right[2]<=95):
        raise ValueError(f"right auto-shaded face missing or wrong: {right}")
    if left[0]<right[0]+45:
        raise ValueError("dynamic normal orientation did not change NCCS light")
    print("Source OP0 MapTileModel auto shade-index rendering verified")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--stage-sd-root", type=Path)
    group.add_argument("--check-screenshot", type=Path)
    group.add_argument("--stage-geometry-sd-root", type=Path)
    group.add_argument("--check-geometry-screenshot", type=Path)
    group.add_argument("--stage-depth-sd-root", type=Path)
    group.add_argument("--check-depth-screenshot", type=Path)
    group.add_argument("--stage-distance-sd-root", type=Path)
    group.add_argument("--check-distance-screenshot", type=Path)
    group.add_argument("--stage-side-light-sd-root", type=Path)
    group.add_argument("--check-side-light-screenshot", type=Path)
    group.add_argument("--stage-derived-shades-sd-root", type=Path)
    group.add_argument("--check-derived-shades-screenshot", type=Path)
    args = parser.parse_args()
    if args.stage_sd_root is not None:
        stage(args.stage_sd_root)
    elif args.stage_geometry_sd_root is not None:
        stage_geometry(args.stage_geometry_sd_root)
    elif args.check_geometry_screenshot is not None:
        check_geometry(args.check_geometry_screenshot)
    elif args.stage_depth_sd_root is not None:
        stage_depth(args.stage_depth_sd_root)
    elif args.check_depth_screenshot is not None:
        check_depth(args.check_depth_screenshot)
    elif args.stage_distance_sd_root is not None:
        stage_distance(args.stage_distance_sd_root)
    elif args.check_distance_screenshot is not None:
        check_distance(args.check_distance_screenshot)
    elif args.stage_side_light_sd_root is not None:
        stage_side_lighting(args.stage_side_light_sd_root)
    elif args.check_side_light_screenshot is not None:
        check_side_lighting(args.check_side_light_screenshot)
    elif args.stage_derived_shades_sd_root is not None:
        stage_derived_shades(args.stage_derived_shades_sd_root)
    elif args.check_derived_shades_screenshot is not None:
        check_derived_shades(args.check_derived_shades_screenshot)
    else:
        check(args.check_screenshot)


if __name__ == "__main__":
    main()
