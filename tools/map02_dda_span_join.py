"""Conservative join of DDA row-rejection and independently supplied spans.

Neither input authenticates original GPU provenance. Never upgrade a joined
synthetic event into a hardware/retail pixel-coverage claim.
"""
from dataclasses import dataclass
from tools.map02_dda_coverage import Row, classify

MAX_EVENTS = 63  # 64 is a potentially truncated source capture.
VERTICAL_REASONS = frozenset((4, 5, 6, 7))


@dataclass(frozen=True)
class Span:
    frame: int
    primitive_ordinal: int
    y: int
    x_start: int
    x_bound: int
    clip_l: int
    clip_r: int
    clip_t: int
    clip_b: int


def _int(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"invalid {name}")
    return value


def reconcile(events, spans):
    """Require a unique row span per event and check reason/Y consistency.

    Does not assert that a span was obtained from an executed dda_part.
    A future authenticated capture format must provide that independently.
    """
    if not 1 <= len(events) <= MAX_EVENTS or len(spans) > MAX_EVENTS:
        raise ValueError("empty, oversized or potentially truncated capture")
    index = {}
    for span in spans:
        if not isinstance(span, Span):
            raise ValueError("span type")
        key = (span.frame, span.primitive_ordinal, span.y)
        for n, v in zip(("frame", "primitive_ordinal", "row"), key):
            _int(v, n)
        if key in index:
            raise ValueError("ambiguous duplicate span")
        index[key] = span
    results = []
    seen = set()
    for step, event in enumerate(events):
        if type(event) is not dict or set(event) != {
            "frame", "primitive_ordinal", "y", "x", "reason", "step"
        }:
            raise ValueError("unexpected event fields")
        for name in ("frame", "primitive_ordinal", "y", "x", "step"):
            _int(event[name], name)
        if event["step"] != step or type(event["reason"]) is not int or event["reason"] not in VERTICAL_REASONS:
            raise ValueError("wrong step or vertical reason")
        key = (event["frame"], event["primitive_ordinal"], event["y"])
        event_id = (key, event["x"], event["reason"])
        if event_id in seen:
            raise ValueError("duplicate rejection")
        seen.add(event_id)
        span = index.get(key)
        if span is None:
            raise ValueError("no unique matched span for rejected row")
        top = event["y"] < span.clip_t
        bottom = event["y"] > span.clip_b
        if (event["reason"] in (4, 7) and not top) or (event["reason"] in (5, 6) and not bottom):
            raise ValueError("reason disagrees with vertical clip")
        status = classify(Row(span.x_start, span.x_bound, span.y,
                              span.clip_l, span.clip_r, span.clip_t,
                              span.clip_b, event["x"], event["y"]))
        results.append({
            "event_step": step,
            "x_inside_supplied_unclipped_span": status["dda_unclipped_x_covered"],
            "vertical_rejected_and_x_in_supplied_span": status["vertical_rejected_but_unclipped_x_covered"],
            "original_dda_span_provenance_verified": False,
            "original_triangle_coverage_verified": False,
            "retail_map02_verified": False,
        })
    return results
