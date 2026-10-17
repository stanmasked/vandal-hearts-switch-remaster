"""Asset-free fail-closed direct DrawOTag VRAM edge witness regression."""
import json
import unittest

from tools.map02_vram_edge_witness import (
    compare_vram_edges, parse_vram_edges, parse_and_compare_edges,
)


def line(event):
    return (json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n").encode()


def sample():
    edges = []
    words = [1, 2, 3, 4, 4, 16]
    types = [1, 2, 1, 2, 2]
    for ordinal in range(5):
        edges.append(dict(stage="native_vram_edge", frame=7,
                          primitive_ordinal=ordinal,
                          primitive_type=types[ordinal], x=10, y=20,
                          before=words[ordinal], after=words[ordinal + 1]))
    pixels = []
    for step, ordinal in enumerate((0, 1, 2, 4)):
        e = edges[ordinal]
        pixels.append(dict(stage="native_putpixel", step=step, frame=7,
                           primitive_ordinal=ordinal, primitive_type=e["primitive_type"],
                           x=10, y=20, before=e["before"], after=e["after"],
                           front=e["after"], semi=0, textured=0, accurate=1, abr=0))
    return pixels, edges


class VramEdgeWitnessTests(unittest.TestCase):
    def test_preserves_empty_draw_and_matches_all_writes(self):
        pixels, edges = sample()
        report = parse_and_compare_edges(b"".join(map(line, pixels)),
                                         b"".join(map(line, edges)))
        self.assertEqual(report["independently_sampled_draw_edges"], 5)
        self.assertEqual(report["unchanged_draws_without_selected_pixel_writes"], 1)
        self.assertEqual(report["matched_native_putpixel_events"], 4)
        self.assertFalse(report["ps1_hardware_equivalence_proven"])

    def test_detects_tampered_endpoints_and_provenance(self):
        pixels, edges = sample()
        for bad in (
            [*edges[:3], dict(edges[3], after=5), *edges[4:]],
            [*edges[:4], dict(edges[4], before=5)],
            [*edges[:1], dict(edges[1], primitive_type=4), *edges[2:]],
            [*edges[:2], dict(edges[2], frame=8), *edges[3:]],
            [*edges[:3], dict(edges[3], primitive_ordinal=6), *edges[4:]],
            [*edges[:3], dict(edges[3], after=1, before=1), *edges[4:]],
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_and_compare_edges(b"".join(map(line, pixels)),
                                        b"".join(map(line, bad)))
        for corrupt in (
            [*pixels[:1], dict(pixels[1], before=99), *pixels[2:]],
            [*pixels[:3], dict(pixels[3], primitive_type=3)],
            [*pixels[:3], dict(pixels[3], step=4)],
            [*pixels[:3], dict(pixels[3], x=11)],
        ):
            with self.subTest(corrupt=corrupt), self.assertRaises(ValueError):
                compare_vram_edges(corrupt, edges)

    def test_rejects_truncation_crlf_extra_keys_bool_and_nonobjects(self):
        _, edges = sample()
        raw = b"".join(map(line, edges))
        bad = (
            raw[:-1], raw.replace(b"\n", b"\r\n"),
            raw + b"\n", raw + b"{}\n",
            b"[]\n", b"{garbage}\n",
            line(dict(edges[0], before=True)),
            line(dict(edges[0], arbitrary=1)),
            line(dict(edges[0], stage="native_putpixel")),
        )
        for item in bad:
            with self.subTest(item=item[:60]), self.assertRaises(ValueError):
                parse_vram_edges(item)


if __name__ == "__main__":
    unittest.main()
