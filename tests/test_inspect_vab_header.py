"""Synthetic tests for standalone VAB VH header metadata."""
import struct
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inspect_vab_header import inspect_vab_header


class VABHeaderTests(unittest.TestCase):
    def test_header_and_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.vh"
            data = bytearray(32)
            data[:4] = b"pBAV"
            struct.pack_into("<III", data, 4, 7, 2, 4096)
            struct.pack_into("<HHHH", data, 16, 0, 3, 10, 5)
            struct.pack_into("<BBBB", data, 24, 127, 64, 0, 1)
            path.write_bytes(data)
            result = inspect_vab_header(path)
            self.assertEqual(result["header_sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual((result["programs"], result["tones"], result["vags"]), (3, 10, 5))
            self.assertEqual((result["master_volume"], result["master_pan"]), (127, 64))
            self.assertEqual(path.read_bytes(), data)
            for bad in (b"", bytes(data[:31]), b"xxxx" + bytes(data[4:])):
                path.write_bytes(bad)
                with self.assertRaises(ValueError):
                    inspect_vab_header(path)
            data[18:20] = struct.pack("<H", 129)
            path.write_bytes(data)
            with self.assertRaises(ValueError):
                inspect_vab_header(path)


if __name__ == "__main__":
    unittest.main()
