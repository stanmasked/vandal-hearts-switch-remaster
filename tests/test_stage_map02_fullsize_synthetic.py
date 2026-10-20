"""Asset-free full-length (664,849,248-byte) private-disc staging trial.

The synthetic image is sparse, mainly zero-filled, with explicitly synthetic
test markers at three offsets. No original Vandal Hearts disc sectors or
executable, textures, audio or screenshots are included or generated.
"""
import hashlib
import os
from pathlib import Path
import stat
import tempfile
import unittest

from tools.check_map02_local_disc_receipt import RAW_BYTES
from tools.stage_map02_private_disc import (
    BIN_NAME, CUE_NAME, STAGE_NAME, stage_disc,
)

MARKER = b"SYNTHETIC_TEST_BYTES_ONLY_NOT_A_GAME_DISC"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb", buffering=0) as stream:
        while True:
            block = stream.read(4 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


class OriginalLengthSyntheticStagingTests(unittest.TestCase):
    def test_entire_original_length_streamed_verified_and_private(self):
        """Use the correct disc length and read every source/output byte."""
        with tempfile.TemporaryDirectory(prefix="vh-map02-synthetic-") as temp:
            root = Path(temp)
            source_dir = root / "mounted-fake-input"
            source_dir.mkdir()
            private_parent = root / "private-output"
            private_parent.mkdir(mode=0o700)
            bin_path = source_dir / BIN_NAME
            cue_path = source_dir / CUE_NAME

            # Do not allocate original-game bytes. Explicitly create a sparse
            # full-sized synthetic fixture with markers in three distant places.
            with bin_path.open("wb") as stream:
                stream.truncate(RAW_BYTES)
                for offset in (0, 7116 * 2352 + 24, RAW_BYTES - len(MARKER)):
                    stream.seek(offset)
                    stream.write(MARKER)
            cue = (f'FILE "{BIN_NAME}" BINARY\r\n'
                   '  TRACK 01 MODE2/2352\r\n'
                   '    INDEX 01 00:00:00\r\n').encode("ascii")
            cue_path.write_bytes(cue)
            bin_path.chmod(0o644)
            cue_path.chmod(0o644)
            self.assertEqual(bin_path.stat().st_size, RAW_BYTES)
            original_digest = sha256_file(bin_path)
            original_cue = cue_path.read_bytes()

            staged_dir, measured_digest = stage_disc(
                bin_path, cue_path, private_parent)
            staged_bin = staged_dir / BIN_NAME
            staged_cue = staged_dir / CUE_NAME
            self.assertEqual(staged_dir.name, STAGE_NAME)
            self.assertEqual(measured_digest, original_digest)
            self.assertEqual(staged_bin.stat().st_size, RAW_BYTES)
            self.assertEqual(stat.S_IMODE(staged_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(staged_bin.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(staged_cue.stat().st_mode), 0o600)
            self.assertEqual(staged_cue.read_bytes(), original_cue)
            self.assertEqual(sha256_file(staged_bin), original_digest)
            self.assertEqual(stat.S_IMODE(bin_path.stat().st_mode), 0o644)
            self.assertEqual(stat.S_IMODE(cue_path.stat().st_mode), 0o644)
            self.assertEqual(sorted(p.name for p in private_parent.iterdir()),
                             [STAGE_NAME])
            for offset in (0, 7116 * 2352 + 24, RAW_BYTES - len(MARKER)):
                with staged_bin.open("rb") as stream:
                    stream.seek(offset)
                    self.assertEqual(stream.read(len(MARKER)), MARKER)
            print("ASSET-FREE FULL-SIZE STAGING VERIFIED:",
                  RAW_BYTES, "bytes; identical source/staged SHA-256")


if __name__ == "__main__":
    unittest.main()
