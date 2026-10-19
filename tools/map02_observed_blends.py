"""Conservative counters for directly witnessed PC PutPixel STP/ABR outcomes.

This does not reconstruct BlendG1, model hardware PS1 equations, or infer
uncaptured pixels. It only stratifies validated original-PC observer rows.
"""
def summarize_observed_blends(rows):
    bins = [[{"calls": 0, "same_color": 0, "changed": 0,
              "front_equal_after": 0, "bit15_rises": 0, "bit15_falls": 0}
             for _ in range(4)] for _ in range(2)]
    opaque = [0, 0]
    for row in rows:
        accurate = row["accurate"]
        abr = row["abr"]
        semi = row["semi"]
        before, front, after = row["before"], row["front"], row["after"]
        if type(accurate) is not int or accurate not in (0, 1):
            raise ValueError("invalid accurate mode")
        if type(abr) is not int or abr not in range(4):
            raise ValueError("invalid ABR")
        if type(semi) is not int or semi not in (0, 1):
            raise ValueError("invalid semi flag")
        for value in (before, front, after):
            if type(value) is not int or not 0 <= value <= 65535:
                raise ValueError("invalid observed pixel word")
        if semi == 0:
            if front != after:
                raise ValueError("opaque PutPixel differs from front copy")
            opaque[accurate] += 1
            continue
        b = bins[accurate][abr]
        b["calls"] += 1
        b["same_color"] += before == after
        b["changed"] += before != after
        b["front_equal_after"] += front == after
        b["bit15_rises"] += not bool(before & 0x8000) and bool(after & 0x8000)
        b["bit15_falls"] += bool(before & 0x8000) and not bool(after & 0x8000)
    return {
        "observed_semi_putpixel_by_accuracy_and_abr": bins,
        "observed_opaque_putpixel_by_accuracy": opaque,
        "blendg1_equation_verified": False,
        "ps1_hardware_abr_equivalence_verified": False,
    }
