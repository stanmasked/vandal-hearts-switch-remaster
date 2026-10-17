#!/usr/bin/env python3
"""Stress the REAL original DrawOTag with overlapping draw-mode/STP cases.

No original game bytes. This test uses original PC libgpu + rasterizer
on deterministic handmade BGR555 texels, not a fabricated GPU model.
"""
import argparse
from pathlib import Path

from tools.check_map02_original_drawotag_runtime import HARNESS, run_original_ot

# Reuse the same isolated HD/language/presentation stubs as the baseline.
# Only the in-memory test program changes; all original GPU TUs are compiled.
COMPLEX_HARNESS = HARNESS[:HARNESS.index("int main(void) {")] + r"""
int main(void) {
    unsigned int ot[2];
    DRAWENV env;
    DISPENV disp;
    DR_MODE mode1, mode3;
    POLY_F4 first, third;
    POLY_FT4 stp_on, transparent, stp_off;
    unsigned short (*vram)[1024] = PC_GpuVram();
    unsigned short before = 1u, after;
    int u, v;
#ifdef VH_MAP02_SCOPED_BLEND_PROBE
    VHMap02BlendEvent event;
    unsigned i, seen[5] = {0, 0, 0, 0, 0};
    unsigned short last_after = 0;
    int last_ordinal = -1;
#endif
    ResetGraph(0);
    SetDefDrawEnv(&env, 0, 0, 320, 240);
    SetDefDispEnv(&disp, 0, 0, 320, 240);
    PutDrawEnv(&env);
    PutDispEnv(&disp);

    for (v = 0; v < 8; v++) for (u = 0; u < 8; u++) {
        vram[v][640 + u] = 0x8010; /* STP=1, invokes BlendG1 */
        vram[v][704 + u] = 0x0000; /* full texel transparency, NO PutPixel */
        vram[v][768 + u] = 0x0010; /* STP=0, opaque copy despite semi flag */
    }
    vram[10][10] = before;

    SetPolyF4(&first);
    setRGB0(&first, 200, 0, 0);
    setXYWH(&first, 9, 9, 6, 6);
    SetSemiTrans(&first, 1);

    SetPolyFT4(&stp_on);
    setRGB0(&stp_on, 128, 128, 128);
    setXYWH(&stp_on, 9, 9, 6, 6);
    setUVWH(&stp_on, 0, 0, 6, 6);
    stp_on.tpage = GetTPage(2, 2, 640, 0);
    stp_on.clut = 0;
    SetSemiTrans(&stp_on, 1);

    SetPolyF4(&third);
    setRGB0(&third, 88, 0, 0);
    setXYWH(&third, 9, 9, 6, 6);
    SetSemiTrans(&third, 1);

    SetPolyFT4(&transparent);
    setRGB0(&transparent, 128, 128, 128);
    setXYWH(&transparent, 9, 9, 6, 6);
    setUVWH(&transparent, 0, 0, 6, 6);
    transparent.tpage = GetTPage(2, 1, 704, 0);
    transparent.clut = 0;
    SetSemiTrans(&transparent, 1);

    SetPolyFT4(&stp_off);
    setRGB0(&stp_off, 128, 128, 128);
    setXYWH(&stp_off, 9, 9, 6, 6);
    setUVWH(&stp_off, 0, 0, 6, 6);
    stp_off.tpage = GetTPage(2, 0, 768, 0);
    stp_off.clut = 0;
    SetSemiTrans(&stp_off, 1);

    SetDrawMode(&mode1, 0, 0, GetTPage(2, 1, 640, 0), NULL);
    SetDrawMode(&mode3, 0, 0, GetTPage(2, 3, 640, 0), NULL);

    /* LIFO: mode1 -> first F4 -> mode3 -> textured STP blend FT4 ->
     * third F4 -> zero texel FT4 -> opaque STP=0 FT4.
     * Non-draw mode commands must never increase draw ordinals. */
    ClearOTag(ot, 2);
    AddPrim(&ot[0], &stp_off);
    AddPrim(&ot[0], &transparent);
    AddPrim(&ot[0], &third);
    AddPrim(&ot[0], &stp_on);
    AddPrim(&ot[0], &mode3);
    AddPrim(&ot[0], &first);
    AddPrim(&ot[0], &mode1);
    DrawOTag(ot);
    after = vram[10][10];
    assert(after == 0x0010); /* last STP=0 textured write is opaque */
#ifdef VH_MAP02_SCOPED_BLEND_PROBE
    assert(!vh_map02_scope_failed());
    assert(vh_map02_scope_count() >= 4);
    for (i = 0; i < vh_map02_scope_count(); i++) {
        int ordinal, abr;
        assert(vh_map02_scope_copy(i, &event));
        ordinal = (int)event.ordinal;
        assert(ordinal == 0 || ordinal == 1 || ordinal == 2 || ordinal == 4);
        assert(ordinal >= last_ordinal);
        assert(event.frame == 1 && event.x == 10 && event.y == 10);
        assert(event.accurate && event.step == i);
        if (last_ordinal >= 0 && ordinal == last_ordinal)
            assert(event.before == last_after);
        if (ordinal == 0 || ordinal == 1 || ordinal == 2) {
            abr = ordinal == 0 ? 1 : ordinal == 1 ? 2 : 3;
            assert(event.abr == abr && event.semi && event.has_blend);
            assert(event.primitive_type == (ordinal == 1 ?
                   PC_GPU_PRIM_POLY_FT4 : PC_GPU_PRIM_POLY_F4));
            assert(event.textured == (ordinal == 1));
            assert(event.blend_fg == (unsigned short)(event.front | 0x8000u));
            assert(event.blend_bg == event.before);
            assert(event.blend_result == event.after);
            if (ordinal == 0 && !seen[0]) assert(event.before == before);
        } else {
            assert(event.primitive_type == PC_GPU_PRIM_POLY_FT4);
            assert(event.textured && !event.semi && !event.has_blend);
            assert(event.after == event.front);
        }
        last_ordinal = ordinal;
        last_after = event.after;
        seen[ordinal]++;
    }
    assert(seen[0] && seen[1] && seen[2] && !seen[3] && seen[4]);
    assert(last_after == after);
#endif
    /* Observer off/on/staged must leave the EXACT SAME 1 MiB native VRAM. */
    {
        size_t byte_count, i;
        const unsigned char *bytes = PC_GpuVramBytes(&byte_count);
        unsigned long long digest = 14695981039346656037ULL;
        assert(byte_count == 1024u * 512u * 2u && bytes);
        for (i = 0; i < byte_count; i++)
            digest = (digest ^ bytes[i]) * 1099511628211ULL;
        printf("%016llx\n", digest);
    }
    return 0;
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_upstream", type=Path)
    args = parser.parse_args()
    try:
        modes = run_original_ot(
            args.pinned_upstream,
            harness=COMPLEX_HARNESS,
            expected_ordinals=frozenset((0, 1, 2, 4)),
            minimum_blends=3,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print("Overlapping original DrawOTag complex runtime: " + ", ".join(modes))
    print("Synthetic textures only; real MAP02 and PS1 parity unverified.")


if __name__ == "__main__":
    main()
