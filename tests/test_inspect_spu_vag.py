"""Synthetic standalone VAGp header tests (no game assets)."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inspect_spu_vag import inspect_vag


def vag(*, blocks=2, rate=22050, magic=b"VAGp", declared=None):
    header = bytearray(48)
    header[:4] = magic
    struct.pack_into(">IIII", header, 4, 0x20, 0, blocks * 16 if declared is None else declared, rate)
    header[0x20:0x25] = b"test" + bytes([0])
    return bytes(header) + bytes(blocks * 16)


class VAGInspectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "test.vag"

    def test_valid_header_is_read_only(self):
        data = vag()
        self.path.write_bytes(data)
        result = inspect_vag(self.path)
        self.assertEqual((result["sample_rate"], result["adpcm_blocks"],
                          result["pcm_samples_nominal"]), (22050, 2, 56))
        self.assertEqual(self.path.read_bytes(), data)

    def test_rejects_malformed_or_truncated(self):
        for data in (b"", vag(magic=b"xxxx"), vag(declared=17),
                     vag(rate=0), vag(blocks=1, declared=32)):
            with self.subTest(data=data[:8]):
                self.path.write_bytes(data)
                with self.assertRaises(ValueError):
                    inspect_vag(self.path)


if __name__ == "__main__":
    unittest.main()
