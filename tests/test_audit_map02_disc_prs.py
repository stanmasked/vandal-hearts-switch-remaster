"""Synthetic MAP02 US disc/PRS read-only audit (no copyrighted bytes)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.audit_map02_disc_prs import (
    START_SECTOR, SECTOR_COUNT, DAT_START_SECTOR, DAT_SECTOR_COUNT,
    PRIOR_DAT_LENGTH, USER_BYTES, RAW_BYTES, SYNC,
    audit_prs, read_sectors, read_sectors_from_stream, unpack_prs, xa_edc,
)
from tools.compare_map02_variants import (
    EXPECTED_LENGTH, RECORD_SIZE, FACE_GFX_OFFSET, TARGET_RECORDS,
)


def encoded_test_map() -> bytes:
    """Construct a full-size, highly compressible synthetic map and two GFX bytes."""
    target = {record * RECORD_SIZE + FACE_GFX_OFFSET: value
              for record, value in zip(TARGET_RECORDS, (241, 243))}
    flags_and_tokens = []
    position = 0
    while position < EXPECTED_LENGTH:
        if position in target:
            flags_and_tokens.append((0, bytes([target[position]])))
            position += 1
        else:
            next_marker = min((k for k in target if k > position), default=EXPECTED_LENGTH)
            n = min(34, next_marker - position)
            if n < 3:
                flags_and_tokens.append((0, b"\x00"))
                position += 1
            else:
                # Cache bytes at indexes 100..133 remain zero: both marker writes
                # land at unrelated dictionary positions (286 and 862).
                flags_and_tokens.append((1, bytes(((n - 3) << 2, 100))))
                position += n
    payload = bytearray()
    for start in range(0, len(flags_and_tokens), 8):
        group = flags_and_tokens[start:start + 8]
        payload.append(sum(ref << i for i, (ref, _) in enumerate(group)))
        for _, token in group:
            payload.extend(token)
    assert len(payload) + 4 <= SECTOR_COUNT * USER_BYTES
    return len(payload).to_bytes(4, "little") + payload


def write_fake_image(path: Path, payload: bytes, layout: str, bias: int = 0):
    assert len(payload) <= SECTOR_COUNT * USER_BYTES
    padded = payload.ljust(SECTOR_COUNT * USER_BYTES, b"\x00")
    sector_size = RAW_BYTES if layout == "mode2-2352" else USER_BYTES
    first = START_SECTOR + bias
    with path.open("wb") as handle:
        handle.truncate((first + SECTOR_COUNT) * sector_size)
        handle.seek(first * sector_size)
        for i in range(SECTOR_COUNT):
            chunk = padded[i * USER_BYTES:(i + 1) * USER_BYTES]
            if layout == "mode2-2352":
                # Valid Mode2 Form1 EDC; P/Q ECC parity remains out of scope.
                prefix = SYNC + bytes(3) + b"\x02" + bytes(8) + chunk
                sector = (prefix + xa_edc(prefix[16:2072]).to_bytes(4, "little")
                          + bytes(276))
            else:
                sector = chunk
            assert len(sector) == sector_size
            handle.write(sector)


def write_fake_dat_sectors(path: Path, dat: bytes, layout: str, bias: int = 0):
    """Put DAT before PRS in the same synthetic ISO/Mode2 disc image."""
    assert len(dat) == PRIOR_DAT_LENGTH
    padded = dat.ljust(DAT_SECTOR_COUNT * USER_BYTES, b"\x00")
    sector_size = RAW_BYTES if layout == "mode2-2352" else USER_BYTES
    with path.open("r+b") as handle:
        handle.seek((DAT_START_SECTOR + bias) * sector_size)
        for index in range(DAT_SECTOR_COUNT):
            data = padded[index * USER_BYTES:(index + 1) * USER_BYTES]
            if layout == "mode2-2352":
                prefix = SYNC + bytes(3) + b"\x02" + bytes(8) + data
                sector = (prefix + xa_edc(prefix[16:2072]).to_bytes(4, "little")
                          + bytes(276))
            else:
                sector = data
            handle.write(sector)



class AuditMap02DiscPRSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prs = encoded_test_map()

    def test_decodes_all_616_tiles_and_two_original_prs_indices(self):
        report = audit_prs(self.prs)
        self.assertEqual(report["logical_prs_byte_count"], len(self.prs))
        self.assertEqual([item["local_gfx"] for item in report["target_faces"]], [241, 243])
        self.assertEqual([item["global_gfx_if_loaded"] for item in report["target_faces"]],
                         [641, 643])
        self.assertTrue(report["matches_prior_target_gfx"])
        self.assertFalse(report["matches_prior_decompressed_sha256"])
        self.assertFalse(report["matches_prior_logical_compressed_sha256"])

    def test_decoded_prs_compares_exactly_two_dat_bytes_without_writing_assets(self):
        decompressed = unpack_prs(self.prs)
        dat = bytearray(decompressed)
        for record, local in zip(TARGET_RECORDS, (98, 150)):
            dat[record * RECORD_SIZE + FACE_GFX_OFFSET] = local
        comparison = audit_prs(self.prs, dat=bytes(dat))["dat_comparison"]
        self.assertEqual(comparison["difference_count"], 2)
        self.assertTrue(comparison["matches_prior_disc_audit"])
        self.assertFalse(comparison["matches_prior_disc_audit_with_provenance"])
        self.assertEqual(
            [(item["prs_local_gfx"], item["dat_local_gfx"]) for item in comparison["target_faces"]],
            [(241, 98), (243, 150)],
        )
        dat[0] ^= 1
        comparison = audit_prs(self.prs, dat=bytes(dat))["dat_comparison"]
        self.assertEqual(comparison["difference_count"], 3)
        self.assertFalse(comparison["matches_prior_disc_audit"])

    def test_dat_comparison_rejects_short_data(self):
        with self.assertRaisesRegex(ValueError, "DAT must contain"):
            audit_prs(self.prs, dat=b"not a map")

    def test_cli_dat_option_exposes_only_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            prs = base / "map.prs"
            dat = base / "map.dat"
            prs.write_bytes(self.prs)
            decoded = bytearray(unpack_prs(self.prs))
            decoded[TARGET_RECORDS[0] * RECORD_SIZE + FACE_GFX_OFFSET] = 98
            decoded[TARGET_RECORDS[1] * RECORD_SIZE + FACE_GFX_OFFSET] = 150
            dat.write_bytes(decoded)
            proc = subprocess.run(
                [sys.executable, "-m", "tools.audit_map02_disc_prs",
                 "--prs-file", str(prs), "--dat-file", str(dat)],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(proc.stdout)
            self.assertEqual(report["dat_comparison"]["difference_count"], 2)
            self.assertTrue(report["dat_comparison"]["matches_prior_disc_audit"])
            self.assertFalse(report["matches_prior_decompressed_sha256"])

    def test_decompress_literal_and_dictionary_tokens(self):
        # A zero bit is a literal. A one bit with a short b1 references cache.
        payload = bytes((0x00,)) + b"abcdefgh"
        encoded = len(payload).to_bytes(4, "little") + payload
        self.assertEqual(unpack_prs(encoded, max_output=8), b"abcdefgh")
        payload = b"\x01" + bytes((0, 100)) + b"1234567"
        encoded = len(payload).to_bytes(4, "little") + payload
        self.assertEqual(unpack_prs(encoded, max_output=10), b"\x00" * 3 + b"1234567")

    def test_extracts_identical_prs_from_raw_mode2_and_iso_tracks(self):
        for layout in ("mode2-2352", "iso-2048"):
            with self.subTest(layout=layout):
                with tempfile.TemporaryDirectory() as folder:
                    image = Path(folder) / "fake.bin"
                    write_fake_image(image, self.prs, layout)
                    extracted = read_sectors(image, layout)
                    self.assertEqual(extracted[:len(self.prs)], self.prs)
                    result = audit_prs(extracted)
                    self.assertTrue(result["matches_prior_target_gfx"])
                    self.assertEqual(result["available_bytes"], SECTOR_COUNT * USER_BYTES)

    def test_stream_reader_reuses_open_image_for_raw_mode2_and_iso(self):
        for layout in ("mode2-2352", "iso-2048"):
            with self.subTest(layout=layout):
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / "one-open-image.bin"
                    write_fake_image(path, self.prs, layout)
                    with path.open("rb") as source:
                        payload = read_sectors_from_stream(source, layout)
                        self.assertEqual(payload, read_sectors(path, layout))
                        self.assertEqual(payload[:len(self.prs)], self.prs)
                        self.assertFalse(source.closed)

    def test_stream_reader_retains_original_inode_after_filename_replace(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "disc.bin"
            old = Path(folder) / "original-inode.bin"
            write_fake_image(image, self.prs, "mode2-2352")
            with image.open("rb") as stream:
                image.rename(old)
                image.write_bytes(b"substituted content")
                self.assertEqual(
                    read_sectors_from_stream(stream, "mode2-2352")[:len(self.prs)],
                    self.prs,
                )
                with self.assertRaisesRegex(ValueError, "too short"):
                    read_sectors(image, "mode2-2352")

    def test_disc_sector_adjustment_must_be_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "track.iso"
            write_fake_image(image, self.prs, "iso-2048", bias=150)
            with self.assertRaises(ValueError):
                audit_prs(read_sectors(image, "iso-2048", bias=0))
            self.assertTrue(audit_prs(read_sectors(image, "iso-2048", bias=150))
                            ["matches_prior_target_gfx"])

    def test_xa_edc_known_crc_vector_and_corrupt_sector(self):
        self.assertEqual(xa_edc(b"123456789"), 0x6EC2EDC4)
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "valid.bin"
            write_fake_image(file, self.prs, "mode2-2352")
            self.assertTrue(audit_prs(read_sectors(file, "mode2-2352"))
                            ["matches_prior_target_gfx"])
            for offset in (24, 2071, 2072, 2075):
                with self.subTest(offset=offset):
                    with file.open("r+b") as handle:
                        handle.seek(START_SECTOR * RAW_BYTES + offset)
                        original = handle.read(1)
                        handle.seek(START_SECTOR * RAW_BYTES + offset)
                        handle.write(bytes((original[0] ^ 1,)))
                    with self.assertRaisesRegex(ValueError, "EDC mismatch"):
                        read_sectors(file, "mode2-2352")
                    with file.open("r+b") as handle:
                        handle.seek(START_SECTOR * RAW_BYTES + offset)
                        handle.write(original)

    def test_bad_edc_in_later_sector_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "later-sector.bin"
            write_fake_image(image, self.prs, "mode2-2352")
            with image.open("r+b") as handle:
                handle.seek((START_SECTOR + 11) * RAW_BYTES + 24)
                byte = handle.read(1)
                handle.seek((START_SECTOR + 11) * RAW_BYTES + 24)
                handle.write(bytes((byte[0] ^ 0x80,)))
            with self.assertRaisesRegex(ValueError, "sector 11: Mode2 Form1 EDC mismatch"):
                read_sectors(image, "mode2-2352")

    def test_archived_dat_digest_is_required_for_strict_provenance(self):
        decompressed = bytearray(unpack_prs(self.prs))
        for record, local in zip(TARGET_RECORDS, (98, 150)):
            decompressed[record * RECORD_SIZE + FACE_GFX_OFFSET] = local
        report = audit_prs(self.prs, dat=bytes(decompressed))
        self.assertTrue(report["dat_comparison"]["matches_prior_disc_audit"])
        self.assertFalse(report["dat_comparison"]["matches_prior_dat_sha256"])
        self.assertEqual(report["dat_comparison"]["dat_byte_count"], EXPECTED_LENGTH)

    def test_rejects_bad_raw_sector_headers_and_form2(self):
        for index, wrong in ((15, 1), (18, 32), (20, 1), (0, 99)):
            with self.subTest(index=index):
                with tempfile.TemporaryDirectory() as folder:
                    image = Path(folder) / "corrupt.bin"
                    write_fake_image(image, self.prs, "mode2-2352")
                    with image.open("r+b") as handle:
                        handle.seek(START_SECTOR * RAW_BYTES + index)
                        handle.write(bytes([wrong]))
                    with self.assertRaisesRegex(ValueError, "Mode2|subheader|Form2"):
                        read_sectors(image, "mode2-2352")

    def test_corrupted_compressed_header_fails_without_overread(self):
        bad = (SECTOR_COUNT * USER_BYTES).to_bytes(4, "little") + self.prs[4:]
        with self.assertRaisesRegex(ValueError, "invalid MAP02 compressed byte count"):
            audit_prs(bad)
        with self.assertRaisesRegex(ValueError, "shorter than"):
            audit_prs(self.prs[:50])
        with self.assertRaisesRegex(ValueError, "decompressed map has"):
            audit_prs(b"\x09\x00\x00\x00\x00abcdefgh")

    def test_bounded_decoder_rejects_output_overflow(self):
        with self.assertRaisesRegex(ValueError, "beyond map buffer limit"):
            unpack_prs(self.prs, max_output=512)

    def test_fake_data_cannot_pass_known_provenance_check(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "M_MAP02.PRS"
            file.write_bytes(self.prs)
            cmd = [sys.executable, "-m", "tools.audit_map02_disc_prs",
                   "--prs-file", str(file), "--require-prior-provenance"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(result.stdout)
            self.assertFalse(data["matches_prior_decompressed_sha256"])
            self.assertTrue(data["matches_prior_target_gfx"])
            cmd.remove("--require-prior-provenance")
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)

    def test_same_disc_prs_dat_audit_with_valid_crc_and_exact_dat_length(self):
        dat = bytearray(unpack_prs(self.prs))
        for record, value in zip(TARGET_RECORDS, (98, 150)):
            dat[record * RECORD_SIZE + FACE_GFX_OFFSET] = value
        dat = bytes(dat).ljust(PRIOR_DAT_LENGTH, b"\x00")
        for layout in ("mode2-2352", "iso-2048"):
            with self.subTest(layout=layout):
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / "disc.bin"
                    write_fake_image(path, self.prs, layout)
                    write_fake_dat_sectors(path, dat, layout)
                    decoded = read_sectors(
                        path, layout, start_sector=DAT_START_SECTOR,
                        sector_count=DAT_SECTOR_COUNT,
                    )
                    self.assertEqual(decoded[:PRIOR_DAT_LENGTH], dat)
                    command = [sys.executable, "-m", "tools.audit_map02_disc_prs",
                               "--disc-image", str(path), "--layout", layout,
                               "--dat-from-disc"]
                    proc = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    report = json.loads(proc.stdout)
                    self.assertEqual(report["dat_source"], "disc_image")
                    self.assertEqual(report["dat_start_sector"], 6999)
                    self.assertEqual(report["dat_sector_count"], 117)
                    self.assertEqual(report["dat_comparison"]["dat_byte_count"], PRIOR_DAT_LENGTH)
                    self.assertEqual(report["dat_comparison"]["difference_count"], 2)
                    self.assertTrue(report["dat_comparison"]["matches_prior_disc_audit"])
                    self.assertFalse(report["dat_comparison"]["matches_prior_dat_sha256"])
                    expected_edc = 117 if layout == "mode2-2352" else None
                    self.assertEqual(report["dat_mode2_form1_edc_verified_sectors"],
                                     expected_edc)

    def test_same_disc_dat_crc_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "disc.bin"
            write_fake_image(path, self.prs, "mode2-2352")
            dat = bytes(unpack_prs(self.prs)).ljust(PRIOR_DAT_LENGTH, b"\x00")
            write_fake_dat_sectors(path, dat, "mode2-2352")
            with path.open("r+b") as handle:
                handle.seek((DAT_START_SECTOR + 1) * RAW_BYTES + 24)
                original = handle.read(1)
                handle.seek((DAT_START_SECTOR + 1) * RAW_BYTES + 24)
                handle.write(bytes((original[0] ^ 1,)))
            cmd = [sys.executable, "-m", "tools.audit_map02_disc_prs",
                   "--disc-image", str(path), "--layout", "mode2-2352",
                   "--dat-from-disc"]
            failed = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("sector 1: Mode2 Form1 EDC mismatch", failed.stderr)

    def test_disc_dat_source_requires_disc_image_and_excludes_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map.prs"
            path.write_bytes(self.prs)
            base = [sys.executable, "-m", "tools.audit_map02_disc_prs"]
            for args in (
                ["--prs-file", str(path), "--dat-from-disc"],
                ["--disc-image", str(path), "--layout", "mode2-2352",
                 "--dat-from-disc", "--dat-file", str(path)],
            ):
                with self.subTest(args=args):
                    proc = subprocess.run(base + args, capture_output=True, text=True)
                    self.assertNotEqual(proc.returncode, 0)
                    self.assertIn("error:", proc.stderr)

    def test_cd_image_cli_reports_pinned_sector_table(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "track.bin"
            write_fake_image(file, self.prs, "mode2-2352")
            result = subprocess.run(
                [sys.executable, "-m", "tools.audit_map02_disc_prs",
                 "--disc-image", str(file), "--layout", "mode2-2352"],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["cd_table_start_sector"], 0x1bcc)
            self.assertEqual(report["sector_count"], 12)
            self.assertEqual(report["input_type"], "disc_image")
            self.assertEqual(report["sector_bias"], 0)
            self.assertEqual(report["mode2_form1_edc_verified_sectors"], 12)


if __name__ == "__main__":
    unittest.main()
