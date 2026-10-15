"""Asset-free reference checks for the DrawOTag Switch texture smoke fixtures.

Checks test-vector packing/palette addressing; does NOT test the upstream rasterizer.
"""
import unittest

WIDTH = 1024


def tpage(tp, x, y=0):
    return ((x // 64) & 15) | (((y // 256) & 1) << 4) | ((tp & 3) << 7)


def clut(x, y):
    return ((x // 16) & 63) | ((y & 511) << 6)


def upload(vram, x, y, w, h, data):
    assert len(data) == w * h
    for j in range(h):
        for i in range(w):
            vram[(x + i, y + j)] = data[j * w + i]


def sample(vram, page, palette, u, v):
    x = (page & 15) * 64
    y = ((page >> 4) & 1) * 256
    tp = (page >> 7) & 3
    if tp == 0:
        word = vram[(x + u // 4, y + v)]
        index = (word >> ((u % 4) * 4)) & 15
    elif tp == 1:
        word = vram[(x + u // 2, y + v)]
        index = (word >> ((u % 2) * 8)) & 255
    else:
        return vram[(x + u, y + v)]
    cx, cy = (palette & 63) * 16, (palette >> 6) & 511
    return vram[(cx + index, cy)]


class TextureFixtureTests(unittest.TestCase):
    def setUp(self):
        self.vram = {}
        upload(self.vram, 64, 0, 1, 2, [0x2121, 0x2121])
        upload(self.vram, 0, 40, 16, 1, [0, 0x001F, 0x03E0] + [0] * 13)
        upload(self.vram, 128, 0, 1, 2, [0x0201, 0x0201])
        upload(self.vram, 0, 41, 256, 1, [0, 0x7C00, 0x7FFF] + [0] * 253)
        upload(self.vram, 192, 0, 2, 2, [0x03FF, 0x7C1F] * 2)
        upload(self.vram, 256, 0, 2, 2, [0, 0x7FE0] * 2)
        upload(self.vram, 320, 0, 2, 2, [0x801F, 0x03E0] * 2)

    def test_4bpp_clut(self):
        self.assertEqual([sample(self.vram, tpage(0, 64), clut(0, 40), u, 0)
                          for u in range(4)], [0x001F, 0x03E0] * 2)

    def test_8bpp_clut(self):
        self.assertEqual([sample(self.vram, tpage(1, 128), clut(0, 41), u, 0)
                          for u in range(2)], [0x7C00, 0x7FFF])

    def test_direct_colour(self):
        self.assertEqual([sample(self.vram, tpage(2, 192), 0, u, 0)
                          for u in range(2)], [0x03FF, 0x7C1F])

    def test_zero_texel(self):
        self.assertEqual([sample(self.vram, tpage(2, 256), 0, u, 0)
                          for u in range(2)], [0, 0x7FE0])

    def test_stp_is_per_texel(self):
        values = [sample(self.vram, tpage(2, 320), 0, u, 0)
                  for u in range(2)]
        self.assertEqual(values, [0x801F, 0x03E0])
        self.assertEqual([bool(v & 0x8000) for v in values], [True, False])
        self.assertTrue(all(v != 0 for v in values))

    def test_vram_fixture_regions_do_not_overlap_display(self):
        self.assertFalse(any(x < 12 and y < 9 for x, y in self.vram))
        self.assertTrue(all(0 <= x < WIDTH and 0 <= y < 512 for x, y in self.vram))


if __name__ == "__main__":
    unittest.main()
