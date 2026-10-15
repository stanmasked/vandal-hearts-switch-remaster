#!/usr/bin/env python3
"""Evaluate repeated Map02 loads as separate, ordered gameplay episodes.

A second post_load for a previously loaded target *after renderer activity*
marks a new map-load episode. Ambiguous repetitions before renderer activity
remain invalid duplicates in the original single-load validator.
"""
from tools.verify_map02_trace import TARGETS, evaluate_trace


def evaluate_capture_session(entries, *, require_full_trace=False):
    source = iter(entries)
    pending = None
    episodes = []

    while True:
        started = False
        loaded_faces = set()
        renderer_seen = False

        def this_episode():
            nonlocal pending, started, renderer_seen
            while True:
                if pending is not None:
                    entry = pending
                    pending = None
                else:
                    try:
                        entry = next(source)
                    except StopIteration:
                        return
                target = (isinstance(entry, dict)
                          and (entry.get("z"), entry.get("x"), entry.get("face")) in TARGETS)
                stage = entry.get("stage") if isinstance(entry, dict) else None
                if target and stage == "post_load":
                    pos = (entry["z"], entry["x"], entry["face"])
                    if pos in loaded_faces and renderer_seen:
                        pending = entry
                        return
                    loaded_faces.add(pos)
                elif target and stage in ("visit", "skip", "draw"):
                    renderer_seen = True
                started = True
                yield entry

        result = evaluate_trace(this_episode(), require_full_trace=require_full_trace)
        if not started:
            break
        episodes.append(result)

    if len(episodes) == 1:
        # Preserve the pre-existing report format for the common single load.
        return episodes[0]
    if not episodes:
        return evaluate_trace([], require_full_trace=require_full_trace)

    errors = []
    for index, episode in enumerate(episodes, 1):
        errors.extend(f"map load {index}: {error}" for error in episode["errors"])

    def aggregate(field):
        variants = [e[field] for e in episodes]
        if any(v not in ("PRS", "DAT") for v in variants):
            return "incomplete_or_unknown"
        return variants[0] if len(set(variants)) == 1 else "mixed"

    post = aggregate("post_load_overall_variant")
    drawn = aggregate("draw_overall_variant")
    if post == "mixed" or drawn == "mixed":
        errors.append("Map02 PRS/DAT variant changed between gameplay map loads")
    return {
        "observations": [],  # never conflate two independent game-map loads
        "errors": errors,
        "post_load_overall_variant": post,
        "draw_overall_variant": drawn,
        "map_load_count": len(episodes),
        "map_loads": episodes,
        "warning": (
            "Map loads analyzed independently; combined face observations are "
            "intentionally omitted. AddPrim submissions do not prove visible pixels."
        ),
    }
