"""Independent offline DDA interval audit; does NOT instrument original GPU."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Row:
    x_start: int
    x_bound: int
    y: int
    clip_l: int
    clip_r: int
    clip_t: int
    clip_b: int
    sample_x: int
    sample_y: int

def classify(row: Row) -> dict:
    """Half-open DDA X interval and inclusive drawing rectangle.

    Inputs must come from a separate trustworthy DDA span observation before
    claims about original geometry can be made. This function is only an
    arithmetic consistency check, not GPU evidence.
    """
    for name, value in vars(row).items():
        if type(value) is not int:
            raise ValueError(f"{name} must be an integer")
    if row.clip_l > row.clip_r or row.clip_t > row.clip_b:
        raise ValueError("inverted clip rectangle")
    if row.x_start > row.x_bound:
        raise ValueError("inverted DDA interval")
    same_row = row.y == row.sample_y
    raw_x = row.x_start <= row.sample_x < row.x_bound
    y_inside = row.clip_t <= row.y <= row.clip_b
    x_inside = row.clip_l <= row.sample_x <= row.clip_r
    return {
        "sample_row_matches": same_row,
        "dda_unclipped_x_covered": same_row and raw_x,
        "inside_drawing_area": same_row and x_inside and y_inside,
        "dda_clipped_x_covered": same_row and raw_x and x_inside and y_inside,
        "vertical_rejected_but_unclipped_x_covered": same_row and raw_x and not y_inside,
        "coverage_proven_by_original_gpu": False,
        "pixel_written_proven": False,
        "hardware_mask_stp_abr_proven": False,
    }
