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
    """Require one witness for each semi PutPixel and none for opaque copy.

    Each witness contains the PutPixel step, frame, primitive ordinal, x/y,
    accurate, abr, input 'before' and 'front', and output 'after'.
    This validates correspondence, NOT the blend arithmetic itself.
    """
    if not isinstance(putpixel_rows, list) or not isinstance(witness_rows, list):
        raise ValueError("witness streams must be lists")
    requested = [p for p in putpixel_rows if p.get("semi") == 1]
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
        counts[p["accurate"]][p["abr"]] += 1
    return {
        "observed_blendg1_witnesses_by_accuracy_and_abr": counts,
        "observed_blendg1_putpixel_pairs": len(witness_rows),
        "observed_blendg1_entry_exit_matches_putpixel": True,
        "blendg1_arithmetic_equivalence_proven": False,
        "full_original_pixel_coverage_proven": False,
        "ps1_hardware_equivalence_proven": False,
    }
