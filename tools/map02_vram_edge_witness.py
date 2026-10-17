"""Validate independent DrawOTag native-VRAM edges against scoped PutPixel.

Edges are sampled directly by the original OT walker. Comparison here does
NOT authenticate a real MAP02 frame or independent PS1 hardware.
"""
import json
from tools.verify_map02_frame_bundle import number
from tools.verify_map02_blendg1_witness import complete_events

MAX_EDGE_EVENTS = 8192
MAX_EDGE_BYTES = 2 * 1024 * 1024


def parse_vram_edges(raw):
    if not raw.endswith(b"\n") or b"\r" in raw or len(raw) > MAX_EDGE_BYTES:
        raise ValueError("incomplete, noncanonical or oversized native VRAM edge log")
    lines = raw.split(b"\n")[:-1]
    if not 1 <= len(lines) <= MAX_EDGE_EVENTS or any(not line for line in lines):
        raise ValueError("invalid native VRAM edge count/empty rows")
    rows = []
    for i, line in enumerate(lines):
        try:
            event = json.loads(line.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise ValueError("invalid VRAM edge JSON") from exc
        if type(event) is not dict or set(event) != {
            "stage", "frame", "primitive_ordinal", "primitive_type",
            "x", "y", "before", "after"
        }:
            raise ValueError("malformed VRAM edge fields")
        if event["stage"] != "native_vram_edge":
            raise ValueError("invalid VRAM edge stage")
        if number(event["primitive_ordinal"], "edge ordinal", 0,
                  MAX_EDGE_EVENTS-1) != i:
            raise ValueError("VRAM edges missing, reordered or duplicated")
        for name, low, high in (
            ("frame", 1, 2**32 - 1),
            ("primitive_type", 1, 4),
            ("x", 0, 1023), ("y", 0, 511),
            ("before", 0, 65535), ("after", 0, 65535),
        ):
            number(event[name], "edge " + name, low, high)
        if rows:
            prev = rows[-1]
            if (event["frame"], event["x"], event["y"]) != (
                    prev["frame"], prev["x"], prev["y"]):
                raise ValueError("native VRAM edge frame or coordinate drift")
            if event["before"] != prev["after"]:
                raise ValueError("direct native VRAM boundary chain broken")
        rows.append(event)
    return rows


def compare_vram_edges(putpixel_rows, edge_rows):
    if (type(putpixel_rows) is not list or type(edge_rows) is not list or
            not edge_rows):
        raise ValueError("VRAM edge comparison requires two nonempty lists")
    expected_step = 0
    p = 0
    unchanged = 0
    for ordinal, edge in enumerate(edge_rows):
        if edge["primitive_ordinal"] != ordinal:
            raise ValueError("non-contiguous VRAM draw edge ordinal")
        count = 0
        latest = edge["before"]
        while p < len(putpixel_rows):
            event = putpixel_rows[p]
            if type(event) is not dict or event.get("stage") != "native_putpixel":
                raise ValueError("invalid PutPixel entry")
            draw = number(event.get("primitive_ordinal"), "pixel ordinal",
                          0, MAX_EDGE_EVENTS - 1)
            if draw < ordinal:
                raise ValueError("PutPixel lacks a matching VRAM edge")
            if draw > ordinal:
                break
            if number(event.get("step"), "PutPixel step", 0, 63) != expected_step:
                raise ValueError("PutPixel step gap or duplication")
            if (event.get("frame"), event.get("x"), event.get("y"),
                    event.get("primitive_type")) != (
                    edge["frame"], edge["x"], edge["y"],
                    edge["primitive_type"]):
                raise ValueError("PutPixel disagrees with direct VRAM provenance")
            before = number(event.get("before"), "PutPixel before", 0, 65535)
            latest = number(event.get("after"), "PutPixel after", 0, 65535) if before == latest else -1
            if latest < 0:
                raise ValueError("PutPixel chain disagrees with VRAM edge")
            p += 1
            count += 1
            expected_step += 1
        if latest != edge["after"]:
            raise ValueError("native VRAM after draw disagrees with PutPixel")
        if not count:
            unchanged += 1
    if p != len(putpixel_rows):
        raise ValueError("PutPixel contains events outside observed draw edges")
    if not p:
        raise ValueError("no native PutPixel events captured")
    return {
        "independently_sampled_draw_edges": len(edge_rows),
        "unchanged_draws_without_selected_pixel_writes": unchanged,
        "matched_native_putpixel_events": p,
        "direct_vram_endpoint_matches_putpixel": True,
        "original_gameplay_authenticated": False,
        "ps1_hardware_equivalence_proven": False,
    }


def parse_and_compare_edges(pixel_raw, edge_raw):
    pixels = complete_events(pixel_raw, "verified PutPixel")
    edges = parse_vram_edges(edge_raw)
    return compare_vram_edges(pixels, edges)
