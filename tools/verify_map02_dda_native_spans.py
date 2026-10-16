"""Strict offline parser for private *entered* native DDA span journal.

This is structural validation, not hardware origin attestation. Unlike a
vertically rejected row, each record denotes an entered dda_span call.
"""
import json
from tools.map02_dda_span_join import Span, MAX_EVENTS

EXPECTED = frozenset(("stage", "step", "frame", "primitive_ordinal",
                      "primitive_type", "y", "x_start", "x_bound",
                      "clip_l", "clip_r", "clip_t", "clip_b"))

def parse_native_spans(raw: bytes):
    if type(raw) is not bytes or len(raw) > 16384:
        raise ValueError("invalid or oversized journal")
    lines = raw.splitlines()
    if not 1 <= len(lines) <= MAX_EVENTS or not raw.endswith(b"\n"):
        raise ValueError("empty, truncated or saturated journal")
    result = []
    last_key = None
    for expected_step, line in enumerate(lines):
        def reject_constant(value):
            raise ValueError("nonfinite JSON constant")
        try:
            obj = json.loads(line, parse_constant=reject_constant)
        except (ValueError, UnicodeError) as exc:
            raise ValueError("invalid span JSONL") from exc
        if type(obj) is not dict or frozenset(obj) != EXPECTED:
            raise ValueError("unexpected span schema")
        if obj["stage"] != "native_dda_span":
            raise ValueError("wrong span stage")
        for name in EXPECTED - {"stage"}:
            if type(obj[name]) is not int:
                raise ValueError("noninteger span field")
        if obj["step"] != expected_step or obj["frame"] < 1 or obj["primitive_ordinal"] < 0:
            raise ValueError("invalid ordering or frame")
        if not (0 <= obj["primitive_type"] <= 255 and
                0 <= obj["y"] <= 511 and
                0 <= obj["clip_t"] <= obj["clip_b"] <= 511 and
                0 <= obj["clip_l"] <= obj["clip_r"] <= 1023 and
                obj["x_start"] <= obj["x_bound"]):
            raise ValueError("invalid DDA geometry")
        key = (obj["frame"], obj["primitive_ordinal"])
        if last_key is not None and key < last_key:
            raise ValueError("primitive ordering decreased")
        last_key = key
        result.append(Span(obj["frame"], obj["primitive_ordinal"],
                           obj["y"], obj["x_start"], obj["x_bound"],
                           obj["clip_l"], obj["clip_r"], obj["clip_t"], obj["clip_b"]))
    return result
