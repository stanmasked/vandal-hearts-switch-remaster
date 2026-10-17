#!/usr/bin/env python3
"""Exact original-PC WritePixel BGR555 effect for already validated inputs.

Source: pinned HalmyLyseas/VandalHearts-PcPort pc_raster.c at
14552fffa0e0b47e02b57592e274fc6e7a649923 (Git blob
ba8a05d161ad778c0b75e452ff0a11ed163c65cd), WritePixel/BlendG1.
This checks observed PC software outputs, NOT PS1 hardware GPU parity.
"""


def _pack(r, g, b):
    def five(value):
        return min(255, max(0, value)) >> 3

    return (five(b) << 10) | (five(g) << 5) | five(r)


def _blend_g1(before, front, abr, textured):
    # Mirror pinned unsigned BlendG1 exactly; fg bit15 is forced on.
    fg = front | 0x8000
    bg = before
    if abr == 0:
        bg |= 0x8000
        result = ((fg + bg) - ((fg ^ bg) & 0x0421)) >> 1
    elif abr == 1:
        bg &= ~0x8000
        summed = fg + bg
        carry = (summed - ((fg ^ bg) & 0x8421)) & 0x8420
        result = (summed - carry) | (carry - (carry >> 5))
    elif abr == 2:
        bg |= 0x8000
        fg &= ~0x8000
        diff = bg - fg + 0x108420
        borrow = (diff - ((bg ^ fg) & 0x108420)) & 0x108420
        result = (diff - borrow) & (borrow - (borrow >> 5))
    elif abr == 3:
        bg &= ~0x8000
        fg = ((fg >> 2) & 0x1ce7) | 0x8000
        summed = fg + bg
        carry = (summed - ((fg ^ bg) & 0x8421)) & 0x8420
        result = (summed - carry) | (carry - (carry >> 5))
    else:
        raise ValueError("unknown original PC ABR mode")
    if not textured:
        result &= ~0x8000
    return result & 0xffff


def expected_write_pixel(before, front, abr, semi, textured, accurate):
    """Compute one native PC WritePixel AFTER from witnessed BEFORE/front.

    Inputs must already be integer-validated by the private event parser:
    BGR555 words 0..65535; abr 0..3; semi/textured/accurate 0 or 1.
    """
    if not semi:
        return front
    if accurate:
        return _blend_g1(before, front, abr, textured)

    # Pinned legacy raster path: UnpackColor scales channels by 8;
    # arithmetic uses C integer division (all divided operands here >= 0);
    # PackColorDither clamps to 8-bit and truncates back to BGR555.
    foreground = [((front >> shift) & 31) << 3 for shift in (0, 5, 10)]
    background = [((before >> shift) & 31) << 3 for shift in (0, 5, 10)]
    if abr == 0:
        rgb = [(b + f) // 2 for b, f in zip(background, foreground)]
    elif abr == 1:
        rgb = [b + f for b, f in zip(background, foreground)]
    elif abr == 2:
        rgb = [b - f for b, f in zip(background, foreground)]
    elif abr == 3:
        rgb = [b + f // 4 for b, f in zip(background, foreground)]
    else:
        raise ValueError("unknown original PC ABR mode")
    return _pack(*rgb)
