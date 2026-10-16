"""Strict comparison of optional original-PC BlendG1 entry/exit witnesses.

Input must first be authenticated by caller against a bounded SHA256 manifest,
then joined to the already verified coordinate-scoped PutPixel event log.
The comparator refuses partial, duplicated, reordered or unexplained witnesses.
It never claims full pixel coverage, hardware PS1 accuracy, or gameplay origin.
"""


def _uint(row, name, upper):
    value = row.get(name)
    if type(value) is not int or not 0 <= value <= upper:
        raise ValueError("invalid BlendG1 witness " + name)
    return value


def compare_blendg1_witnesses(putpixel_rows, witness_rows):
    """Require witness only for accurate-mode semi PutPixel, not legacy blending.

    Each witness contains the PutPixel step, frame, primitive ordinal, x/y,
    accurate, abr, PutPixel words, and independently observed fg/bg/result.
    This validates correspondence, NOT the blend arithmetic itself.
    """
    if not isinstance(putpixel_rows, list) or not isinstance(witness_rows, list):
        raise ValueError("witness streams must be lists")
    # The verifier normally authenticates these upstream, but keep this
    # standalone comparator fail-closed for synthetic tests and direct callers.
    last_step = -1
    for p in putpixel_rows:
        if not isinstance(p, dict) or p.get("stage") != "native_putpixel":
            raise ValueError("invalid PutPixel witness")
        step = _uint(p, "step", 63)
        if step <= last_step:
            raise ValueError("PutPixel steps duplicated or out of order")
        last_step = step
        for key, upper in (("frame", 2**32 - 1),
                           ("primitive_ordinal", 2**32 - 1),
                           ("x", 1023), ("y", 511),
                           ("accurate", 1), ("abr", 3),
                           ("before", 65535), ("front", 65535),
                           ("after", 65535)):
            _uint(p, key, upper)
        if _uint(p, "semi", 1) == 0:
            if _uint(p, "front", 65535) != _uint(p, "after", 65535):
                raise ValueError("opaque PutPixel differs from front copy")
    requested = [p for p in putpixel_rows if p["semi"] == 1 and p["accurate"] == 1]
    if not requested:
        raise ValueError("no directly witnessed semi-transparent BlendG1 call")
    if len(requested) != len(witness_rows):
        raise ValueError("BlendG1 witnesses missing or unexpected")
    counts = [[0] * 4 for _ in range(2)]
    keys = ("frame", "primitive_ordinal", "x", "y", "accurate",
            "abr", "before", "front", "after")
    limits = {"frame": 2**32 - 1, "primitive_ordinal": 2**32 - 1,
              "x": 1023, "y": 511, "accurate": 1, "abr": 3,
              "before": 65535, "front": 65535, "after": 65535}
    for p, w in zip(requested, witness_rows):
        if not isinstance(w, dict) or w.get("stage") != "native_blendg1":
            raise ValueError("invalid BlendG1 witness stage")
        if _uint(w, "putpixel_step", 63) != p["step"]:
            raise ValueError("BlendG1 witness step/order mismatch")
        for key in keys:
            if _uint(w, key, limits[key]) != p[key]:
                raise ValueError("BlendG1 witness differs from PutPixel: " + key)
        # Actual BlendG1 fg has bit 15 forced high; bg is destination before.
        # Do not accept an echo of PutPixel values as a complete witness.
        if _uint(w, "blend_fg", 65535) != (p["front"] | 0x8000):
            raise ValueError("BlendG1 fg argument disagrees with PutPixel front")
        if _uint(w, "blend_bg", 65535) != p["before"]:
            raise ValueError("BlendG1 bg argument disagrees with destination")
        if _uint(w, "blend_result", 65535) != p["after"]:
            raise ValueError("BlendG1 result disagrees with PutPixel")
        counts[p["accurate"]][p["abr"]] += 1
    return {
        "observed_blendg1_witnesses_by_accuracy_and_abr": counts,
        "observed_blendg1_putpixel_pairs": len(witness_rows),
        "legacy_semi_putpixel_calls_without_blendg1": sum(
            p["semi"] == 1 and p["accurate"] == 0 for p in putpixel_rows),
        "observed_blendg1_entry_exit_matches_putpixel": True,
        "blendg1_arithmetic_equivalence_proven": False,
        "full_original_pixel_coverage_proven": False,
        "ps1_hardware_equivalence_proven": False,
    }
