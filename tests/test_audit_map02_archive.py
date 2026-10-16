"""Synthetic archive-backed map02 resource audit. No original game assets."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.audit_map02_archive import (
    MAX_DISC_BYTES, archive_members, audit_archive, pick_disc_member,
    stream_member_sector_windows,
)
from tools.audit_map02_disc_prs import PRIOR_DAT_LENGTH, unpack_prs
from test_audit_map02_disc_prs import (
    DAT_START_SECTOR, DAT_SECTOR_COUNT, encoded_test_map,
    write_fake_dat_sectors, write_fake_image,
)


def fake_archiver(path: Path) -> None:
    # Emulate 7z -slt and 7z x -so with synthetic owned disc bytes.
    path.write_text(
        '#!/usr/bin/env python3\n'
        'import os, pathlib, sys\n'
        'disc = pathlib.Path(os.environ["FAKE_MAP02_DISC"])\n'
        'name = os.environ.get("FAKE_MAP02_MEMBER", "game image.iso")\n'
        'size = int(os.environ.get("FAKE_MAP02_SIZE", str(disc.stat().st_size)))\n'
        'if sys.argv[1] == "l":\n'
        '    print("Path = archive.7z\\nType = 7z\\n\\n----------")\n'
        '    print(f"Path = {name}\\nSize = {size}\\nFolder = -\\n")\n'
        'elif sys.argv[1] == "x":\n'
        '    if sys.argv[-1] != name: sys.exit(3)\n'
        '    with disc.open("rb") as stream:\n'
        '        while True:\n'
        '            block = stream.read(65536)\n'
        '            if not block: break\n'
        '            sys.stdout.buffer.write(block)\n'
        'else: sys.exit(4)\n',
        encoding="utf-8",
    )
    path.chmod(0o700)


class AuditMap02ArchiveTests(unittest.TestCase):
    def _fixture(self, root: Path):
        source = encoded_test_map()
        image = root / "synthetic.iso"
        write_fake_image(image, source, "iso-2048")
        dat = bytearray(unpack_prs(source))
        for index, local in ((8 * 28 + 19, 98), (11 * 28 + 11, 150)):
            # Test-only map GFX position is supplied by the public layout.
            from tools.compare_map02_variants import RECORD_SIZE, FACE_GFX_OFFSET
            dat[index * RECORD_SIZE + FACE_GFX_OFFSET] = local
        dat.extend(bytes(PRIOR_DAT_LENGTH - len(dat)))
        write_fake_dat_sectors(image, bytes(dat), "iso-2048")
        archive = root / "user-owned.7z"
        archive.write_bytes(b"synthetic 7z wrapper (test archiver supplies bytes)")
        archiver = root / "fake7z"
        fake_archiver(archiver)
        return archive, image, archiver

    def test_read_only_archive_audit_matches_two_disc_resource_differences(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            archive, image, archiver = self._fixture(root)
            before_archive = hashlib.sha256(archive.read_bytes()).hexdigest()
            with patch.dict(os.environ, {"FAKE_MAP02_DISC": str(image)}):
                result = audit_archive(archive, layout="iso-2048", sevenzip=archiver)
            self.assertEqual(result["member_name"], "game image.iso")
            self.assertEqual(result["member_bytes"], image.stat().st_size)
            self.assertTrue(result["original_archive_modified"] is False)
            self.assertTrue(result["temporary_disc_deleted"])
            self.assertFalse(result["full_disc_reconstructed"])
            self.assertEqual(result["temporarily_retained_sector_bytes"],
                             (12 + 117) * 2048)
            self.assertLess(result["temporarily_retained_sector_bytes"],
                            result["member_bytes"] // 10)
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),
                             before_archive)
            self.assertEqual([face["local_gfx"] for face in result["target_faces"]],
                             [241, 243])
            self.assertEqual(result["dat_comparison"]["difference_count"], 2)
            self.assertFalse(result["matches_prior_decompressed_sha256"])
            self.assertIn("not a PC-port gameplay trace", result["evidence_scope"])

    def test_cli_exits_nonzero_when_synthetic_data_is_not_us_provenance(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            archive, image, archiver = self._fixture(root)
            command = [sys.executable, "-m", "tools.audit_map02_archive",
                       str(archive), "--layout", "iso-2048",
                       "--sevenzip", str(archiver), "--require-prior-provenance"]
            with patch.dict(os.environ, {"FAKE_MAP02_DISC": str(image)}):
                result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            audit = json.loads(result.stdout)
            self.assertEqual(audit["dat_source"], "same_disc_archive")
            self.assertEqual(audit["dat_comparison"]["difference_count"], 2)

    def test_multiple_members_need_explicit_choice(self):
        entries = [{"path": "disc1.bin", "size": 1000},
                   {"path": "disc2.iso", "size": 2000}]
        with self.assertRaisesRegex(ValueError, "found 2"):
            pick_disc_member(entries, None)
        self.assertEqual(pick_disc_member(entries, "disc2.iso")["size"], 2000)
        with self.assertRaisesRegex(ValueError, "not uniquely present"):
            pick_disc_member(entries, "missing.bin")
        with self.assertRaisesRegex(ValueError, "1 GiB"):
            pick_disc_member([{"path": "huge.iso",
                              "size": MAX_DISC_BYTES + 1}], None)
        with self.assertRaisesRegex(ValueError, "wildcard"):
            pick_disc_member([{"path": "part?.iso", "size": 1000}], None)

    def test_sector_stream_only_writes_selected_windows_not_whole_disc(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            archive, image, archiver = self._fixture(root)
            p1 = root / "private-prs-range.bin"
            p2 = root / "private-dat-range.bin"
            ranges = [(100, 241, p1),
                      (image.stat().st_size - 321, 321, p2)]
            member = {"path": "game image.iso", "size": image.stat().st_size}
            with patch.dict(os.environ, {"FAKE_MAP02_DISC": str(image)}):
                streamed = stream_member_sector_windows(archive, member,
                                                         str(archiver), ranges)
            self.assertEqual(streamed, image.stat().st_size)
            with image.open("rb") as original:
                original.seek(100)
                self.assertEqual(p1.read_bytes(), original.read(241))
                original.seek(image.stat().st_size - 321)
                self.assertEqual(p2.read_bytes(), original.read(321))
            self.assertEqual(sum(path.stat().st_size for path in (p1, p2)), 562)
            self.assertFalse((root / "owned-disc-temporary.bin").exists())

    def test_rejects_invalid_or_overlapping_ranges_before_unarchiving(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            archive, image, archiver = self._fixture(root)
            member = {"path": "game image.iso", "size": image.stat().st_size}
            for bad in (
                [(0, 100, root / "a"), (50, 10, root / "b")],
                [(-2, 10, root / "a")],
                [(0, 0, root / "a")],
                [(member["size"] - 4, 8, root / "a")],
                [(0, 100, root / "a"), (0, 2, root / "b")],
            ):
                with self.subTest(ranges=bad):
                    with self.assertRaisesRegex(ValueError, "invalid, overlapping"):
                        stream_member_sector_windows(archive, member, str(archiver), bad)

    def test_archive_without_dat_retains_only_twelve_prs_sectors(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            archive, image, archiver = self._fixture(root)
            with patch.dict(os.environ, {"FAKE_MAP02_DISC": str(image)}):
                report = audit_archive(archive, layout="iso-2048",
                                       with_dat=False, sevenzip=archiver)
            self.assertEqual(report["temporarily_retained_sector_bytes"],
                             12 * 2048)
            self.assertNotIn("dat_comparison", report)
            self.assertIsNone(report["dat_start_sector"])
            self.assertFalse(report["full_disc_reconstructed"])

    def test_declared_size_mismatch_rejected_not_silently_truncated(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            archive, image, archiver = self._fixture(root)
            with patch.dict(os.environ, {
                "FAKE_MAP02_DISC": str(image),
                "FAKE_MAP02_SIZE": str(image.stat().st_size + 1),
            }):
                with self.assertRaisesRegex(ValueError, "size differs"):
                    audit_archive(archive, layout="iso-2048", sevenzip=archiver)

    def test_member_metadata_and_no_disc_upload(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            archive, image, archiver = self._fixture(root)
            with patch.dict(os.environ, {"FAKE_MAP02_DISC": str(image)}):
                listing = archive_members(archive, str(archiver))
                self.assertEqual(listing, [
                    {"path": "game image.iso", "size": image.stat().st_size}
                ])


if __name__ == "__main__":
    unittest.main()
