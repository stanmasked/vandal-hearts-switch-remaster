"""Asset-free reference checks for the DrawOTag Switch texture smoke fixtures.

Checks test-vector packing/palette addressing; does NOT test the upstream rasterizer.
"""
import unittest
from pathlib import Path
import re

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
        upload(self.vram, 66, 0, 1, 2, [0x0043, 0x0043])
        upload(self.vram, 64, 8, 1, 2, [0x0043, 0x0065])
        upload(self.vram, 0, 40, 16, 1,
               [0, 0x001F, 0x03E0, 0x7C00, 0x7FFF, 0x7C1F, 0x03FF] + [0] * 9)
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

    def test_fixture_matches_guest_probe(self):
        guest = (Path(__file__).resolve().parents[1] /
                 'probes/pinned_drawotag_switch_smoke.c').read_text()
        expected = {
            'texels': [0x2121, 0x2121],
            'texels_window': [0x0043, 0x0043],
            'texels_vwindow': [0x0043, 0x0065],
            'texels8': [0x0201, 0x0201],
            'texels15': [0x03FF, 0x7C1F, 0x03FF, 0x7C1F],
            'texels_alpha': [0, 0x7FE0, 0, 0x7FE0],
            'texels_stp': [0x801F, 0x03E0, 0x801F, 0x03E0],
        }
        for name, values in expected.items():
            match = re.search(r'unsigned short\s+' + name +
                              r'\s*\[\d+\]\s*=\s*\{([^}]+)\}', guest)
            self.assertIsNotNone(match, name)
            parsed = [int(n.strip(), 0) for n in match.group(1).split(',')]
            self.assertEqual(parsed, values, name)


    def test_palette_initializers_match_guest(self):
        guest = (Path(__file__).resolve().parents[1] /
                 'probes/pinned_drawotag_switch_smoke.c').read_text()
        for name, size, expected in (
            ('palette', 16,
             [0, 0x001F, 0x03E0, 0x7C00, 0x7FFF, 0x7C1F, 0x03FF] + [0] * 9),
            ('palette8', 256, [0, 0x7C00, 0x7FFF] + [0] * 253),
        ):
            match = re.search(r'unsigned short\s+' + name +
                              r'\s*\[(\d+)\]\s*=\s*\{([^}]+)\}', guest)
            self.assertIsNotNone(match, name)
            self.assertEqual(int(match.group(1)), size, name)
            words = [int(n.strip(), 0) for n in match.group(2).split(',')]
            self.assertLessEqual(len(words), size, name)
            self.assertEqual(words + [0] * (size - len(words)), expected, name)

    def test_guest_upload_rectangles_and_texture_modes(self):
        guest = (Path(__file__).resolve().parents[1] /
                 'probes/pinned_drawotag_switch_smoke.c').read_text()
        expected_uploads = {
            'tex_rect': (64, 0, 1, 2, 'texels'),
            'tex_window_rect': (66, 0, 1, 2, 'texels_window'),
            'tex_vwindow_rect': (64, 8, 1, 2, 'texels_vwindow'),
            'clut_rect': (0, 40, 16, 1, 'palette'),
            'tex8_rect': (128, 0, 1, 2, 'texels8'),
            'clut8_rect': (0, 41, 256, 1, 'palette8'),
            'tex15_rect': (192, 0, 2, 2, 'texels15'),
            'alpha_rect': (256, 0, 2, 2, 'texels_alpha'),
            'stp_rect': (320, 0, 2, 2, 'texels_stp'),
        }
        rects = {
            name: tuple(map(int, (x, y, w, h)))
            for name, x, y, w, h in re.findall(
                r'setRECT\(&(\w+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)', guest)
        }
        self.assertEqual({name: rects[name] for name in expected_uploads}, {
            name: data[:4] for name, data in expected_uploads.items()
        })
        self.assertEqual(rects['window_rect'], (8, 0, 248, 256))
        self.assertEqual(rects['reset_rect'], (0, 0, 256, 256))
        self.assertEqual(rects['v_window_rect'], (0, 8, 256, 248))
        self.assertEqual(rects['v_reset_rect'], (0, 0, 256, 256))
        self.assertEqual(set(rects), set(expected_uploads) |
                         {'window_rect', 'reset_rect',
                          'v_window_rect', 'v_reset_rect'})
        for name, (x, y, w, h, array) in expected_uploads.items():
            self.assertRegex(guest, r'LoadImage\(&' + name +
                             r',\s*\(unsigned int \*\)' + array + r'\)')
            self.assertTrue(0 <= x and 0 <= y and x + w <= 1024 and
                            y + h <= 512, name)
            self.assertFalse(x < 12 and y < 9, name)
        entries = list(expected_uploads.items())
        for i, (an, (ax, ay, aw, ah, _)) in enumerate(entries):
            for bn, (bx, by, bw, bh, _) in entries[i + 1:]:
                self.assertFalse(ax < bx + bw and bx < ax + aw and
                                 ay < by + bh and by < ay + ah,
                                 f'VRAM uploads overlap: {an} / {bn}')

        pages = {
            name: tuple(map(int, (tp, abr, x, y)))
            for name, tp, abr, x, y in re.findall(
                r'setTPage\(&(\w+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)', guest)
        }
        self.assertEqual(pages, {
            'textured': (0, 0, 64, 0),
            'textured8': (1, 0, 128, 0),
            'textured15': (2, 0, 192, 0),
            'transparent15': (2, 0, 256, 0),
            'semi15': (2, 0, 320, 0),
        })
        cluts = {
            name: (int(x), int(y))
            for name, x, y in re.findall(
                r'setClut\(&(\w+),\s*(\d+),\s*(\d+)\)', guest)
        }
        self.assertEqual(cluts['textured'], (0, 40))
        self.assertEqual(cluts['textured8'], (0, 41))
        self.assertRegex(guest, r'SetSemiTrans\(&semi15,\s*1\)')

    def test_sprite_draw_mode_precedes_primitive_in_ot_walk(self):
        guest = (Path(__file__).resolve().parents[1] /
                 'probes/pinned_drawotag_switch_smoke.c').read_text()
        self.assertRegex(guest, r'SetSprt\(&sprite\)')
        self.assertRegex(guest, r'setXY0\(&sprite,\s*0,\s*3\)')
        self.assertRegex(guest, r'setWH\(&sprite,\s*2,\s*2\)')
        self.assertRegex(guest, r'setUV0\(&sprite,\s*0,\s*0\)')
        self.assertRegex(guest, r'setClut\(&sprite,\s*0,\s*40\)')
        self.assertRegex(
            guest,
            r'SetDrawMode\(&mode,\s*0,\s*0,\s*'
            r'GetTPage\(0,\s*0,\s*64,\s*0\),\s*NULL\)'
        )
        sprite_link = guest.index('AddPrim(&ot[0], &sprite);')
        mode_link = guest.index('AddPrim(&ot[0], &mode);')
        self.assertLess(sprite_link, mode_link,
                        'OT is head-inserted; mode must execute before SPRT')
        self.assertEqual([sample(self.vram, tpage(0, 64), clut(0, 40), u, 0)
                          for u in range(2)], [0x001F, 0x03E0])

    def test_texture_window_gp0_e2_and_ot_reset(self):
        # Pinned libgpu.c GP0(E2h): 8px mask/offset units.
        mask_x = ((256 - 248) >> 3) & 31
        off_x = (8 >> 3) & 31
        self.assertEqual((mask_x, off_x), (1, 1))
        def window_u(u):
            return (u & ~(mask_x * 8)) | ((off_x & mask_x) * 8)
        self.assertEqual([window_u(u) for u in (0, 1)], [8, 9])
        self.assertEqual([
            sample(self.vram, tpage(0, 64), clut(0, 40), window_u(u), 0)
            for u in (0, 1)
        ], [0x7C00, 0x7FFF])
        # A 256-wide reset RECT has mask=0 and restores red/green.
        self.assertEqual(((256 - 256) >> 3) & 31, 0)
        self.assertEqual([
            sample(self.vram, tpage(0, 64), clut(0, 40), u, 0)
            for u in (0, 1)
        ], [0x001F, 0x03E0])
        guest = (Path(__file__).resolve().parents[1] /
                 'probes/pinned_drawotag_switch_smoke.c').read_text()
        for name, rect in (('window_rect', '8, 0, 248, 256'),
                           ('reset_rect', '0, 0, 256, 256')):
            self.assertIn(f'setRECT(&{name}, {rect});', guest)
        self.assertIn('SetDrawMode(&window_mode, 0, 0, GetTPage(0, 0, 64, 0), &window_rect);', guest)
        self.assertIn('SetDrawMode(&window_reset, 0, 0, GetTPage(0, 0, 64, 0), &reset_rect);', guest)
        self.assertIn('setXY0(&window_sprite, 0, 5);', guest)
        self.assertIn('setClut(&window_sprite, 0, 40);', guest)
        # Head-inserted ordering table: execution is reverse AddPrim order.
        order = ('AddPrim(&ot[0], &sprite);',
                 'AddPrim(&ot[0], &mode);',
                 'AddPrim(&ot[0], &window_reset);',
                 'AddPrim(&ot[0], &window_sprite);',
                 'AddPrim(&ot[0], &window_mode);')
        offsets = [guest.index(item) for item in order]
        self.assertEqual(offsets, sorted(offsets))

    def test_vertical_texture_window_mask_and_reset(self):
        # Pinned GP0(E2h) applies the V mask independently of the U mask.
        mask_y = ((256 - 248) >> 3) & 31
        off_y = (8 >> 3) & 31
        mask_x = ((256 - 256) >> 3) & 31
        self.assertEqual((mask_x, mask_y, off_y), (0, 1, 1))
        def window_v(v):
            return (v & ~(mask_y * 8)) | ((off_y & mask_y) * 8)
        self.assertEqual([window_v(v) for v in (0, 1)], [8, 9])
        self.assertEqual([
            sample(self.vram, tpage(0, 64), clut(0, 40), u, window_v(v))
            for v in (0, 1) for u in (0, 1)
        ], [0x7C00, 0x7FFF, 0x7C1F, 0x03FF])
        self.assertEqual(((256 - 256) >> 3) & 31, 0)
        self.assertEqual([
            sample(self.vram, tpage(0, 64), clut(0, 40), u, v)
            for v in (0, 1) for u in (0, 1)
        ], [0x001F, 0x03E0] * 2)
        guest = (Path(__file__).resolve().parents[1] /
                 'probes/pinned_drawotag_switch_smoke.c').read_text()
        self.assertIn('setRECT(&v_window_rect, 0, 8, 256, 248);', guest)
        self.assertIn('setRECT(&v_reset_rect, 0, 0, 256, 256);', guest)
        self.assertIn('setXY0(&v_window_sprite, 2, 0);', guest)
        self.assertIn('setWH(&v_window_sprite, 2, 2);', guest)
        self.assertIn('setUV0(&v_window_sprite, 0, 0);', guest)
        self.assertIn('setClut(&v_window_sprite, 0, 40);', guest)
        self.assertIn(
            'SetDrawMode(&v_window_mode, 0, 0, GetTPage(0, 0, 64, 0), &v_window_rect);',
            guest
        )
        self.assertIn(
            'SetDrawMode(&v_window_reset, 0, 0, GetTPage(0, 0, 64, 0), &v_reset_rect);',
            guest
        )
        # Head insertion means the last packet is visited first by DrawOTag.
        order = ('AddPrim(&ot[0], &window_mode);',
                 'AddPrim(&ot[0], &v_window_reset);',
                 'AddPrim(&ot[0], &v_window_sprite);',
                 'AddPrim(&ot[0], &v_window_mode);')
        offsets = [guest.index(item) for item in order]
        self.assertEqual(offsets, sorted(offsets))

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
