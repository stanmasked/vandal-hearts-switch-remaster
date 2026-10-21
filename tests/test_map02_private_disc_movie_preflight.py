"""Fictional raw sectors and a tiny synthetic BK2 only; no retail bytes."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.map02_private_disc_movie_preflight import (
    MAP02_BYTES, MAP02_LBA, PVD_LBA, SECTOR_BYTES, USER_DATA_BYTES,
    EXPECTED_BIN_BYTES, EXPECTED_VOLUME_ID, inspect_pair, _full_image_sha256,
    read_private_full_bin_sha256,
)

SYNC = json.dumps({"o":{"FIOConfig":{
    "Devices8":[2,0,0,0,0,0,0,0],
    "Memcards":[False,False],
    "Multitaps":[False,False],
}}})


def raw_sector(user, lba):
    payload = bytes(user).ljust(USER_DATA_BYTES, b"\x00")
    if len(payload) != USER_DATA_BYTES:
        raise ValueError("test payload too large")
    sector = bytearray(SECTOR_BYTES)
    sector[:12] = b"\x00" + b"\xff" * 10 + b"\x00"
    absolute_frame = lba + 150
    sector[12:15] = bytes(
        ((n // 10) << 4) | (n % 10)
        for n in (absolute_frame // 4500,
                  (absolute_frame // 75) % 60,
                  absolute_frame % 75)
    )
    sector[15] = 2
    sector[24:24 + USER_DATA_BYTES] = payload
    return bytes(sector)


def write_movie(path, *, game="Vandal Hearts (USA)", core="Octoshock",
                sync=SYNC):
    header = ("MovieVersion SyntheticCIOnly\nPlatform PSX\n"
              + "GameName " + game + "\nCore " + core + "\n")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Header.txt", header)
        archive.writestr("SyncSettings.json", sync)
        archive.writestr("Input Log.txt", "[Input]\nsynthetic only\n[/Input]\n")


class DiscMoviePreflightTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.cue = self.root / "fictional.cue"
        self.bin = self.root / "fictional.bin"
        self.movie = self.root / "fictional.bk2"
        self.map_data = (b"SYNTHETIC MAP02 PROFILE ONLY\n" * 900)[:MAP02_BYTES]
        self.map_data = self.map_data.ljust(MAP02_BYTES, b"Z")
        self._write_disc(volume_id=EXPECTED_VOLUME_ID)
        self.cue.write_text(
            'FILE "fictional.bin" BINARY\n'
            '  TRACK 01 MODE2/2352\n'
            '    INDEX 01 00:00:00\n',
            encoding="ascii",
        )
        write_movie(self.movie)

    def _write_disc(self, *, volume_id=EXPECTED_VOLUME_ID, valid_pvd=True):
        sectors = MAP02_LBA + (MAP02_BYTES + USER_DATA_BYTES - 1) // USER_DATA_BYTES
        # Sparse synthetic image, no retail contents and no 665 MB of data written.
        with self.bin.open("wb") as handle:
            handle.truncate(EXPECTED_BIN_BYTES)
        pvd = bytearray(USER_DATA_BYTES)
        pvd[0] = 1
        pvd[1:6] = b"CD001" if valid_pvd else b"NOPE!"
        pvd[6] = 1
        pvd[40:72] = volume_id.encode("ascii").ljust(32, b" ")
        with self.bin.open("r+b") as handle:
            handle.seek(PVD_LBA * SECTOR_BYTES)
            handle.write(raw_sector(pvd, PVD_LBA))
            remaining = self.map_data
            for lba in range(MAP02_LBA, sectors):
                block, remaining = remaining[:USER_DATA_BYTES], remaining[USER_DATA_BYTES:]
                handle.seek(lba * SECTOR_BYTES)
                handle.write(raw_sector(block, lba))

    def call(self, **kwargs):
        return inspect_pair(
            self.cue, self.movie,
            expected_map02_sha256=kwargs.pop(
                "expected_map02_sha256", hashlib.sha256(self.map_data).hexdigest()),
            **kwargs,
        )

    def test_matching_disc_profile_and_movie_header_is_ready_for_owner_replay(self):
        result = self.call()
        self.assertTrue(result["disc_volume_id_matches_audited_profile"])
        self.assertTrue(result["disc_size_matches_audited_profile"])
        self.assertTrue(result["map02_prs_matches_expected_profile"])
        self.assertTrue(result["movie_header_matches_vandal_hearts_usa_psx_octoshock"])
        self.assertTrue(result["movie_sync_matches_one_controller_no_cards"])
        self.assertTrue(result["media_preflight_ready_for_owner_replay"])
        self.assertFalse(result["exact_disc_movie_compatibility_verified"])
        self.assertFalse(result["actual_octoshock_playback_verified"])
        self.assertFalse(result["map02_scene_identity_verified"])

    def test_truncated_disc_with_valid_map02_sectors_is_not_ready(self):
        # A minimal synthetic image can preserve the PVD/MAP02 bytes but
        # lacks the rest of the known 282674-sector release profile.
        sectors = MAP02_LBA + (MAP02_BYTES + USER_DATA_BYTES - 1) // USER_DATA_BYTES
        with self.bin.open("r+b") as handle:
            handle.truncate(sectors * SECTOR_BYTES)
        result = self.call()
        self.assertTrue(result["map02_prs_matches_expected_profile"])
        self.assertTrue(result["disc_volume_id_matches_audited_profile"])
        self.assertFalse(result["disc_size_matches_audited_profile"])
        self.assertFalse(result["media_preflight_ready_for_owner_replay"])

    def test_oversized_disc_with_matching_resource_is_not_ready(self):
        with self.bin.open("r+b") as handle:
            handle.truncate(EXPECTED_BIN_BYTES + SECTOR_BYTES)
        result = self.call()
        self.assertTrue(result["map02_prs_matches_expected_profile"])
        self.assertFalse(result["disc_size_matches_audited_profile"])
        self.assertFalse(result["media_preflight_ready_for_owner_replay"])

    def test_rejects_wrong_pvd_sector_msf_despite_valid_payload(self):
        with self.bin.open("r+b") as handle:
            handle.seek(PVD_LBA * SECTOR_BYTES + 12)
            handle.write(b"\x00\x00\x00")
        with self.assertRaisesRegex(ValueError, "MSF address"):
            self.call()

    def test_rejects_wrong_map02_sector_msf_despite_valid_resource_hash(self):
        # Leave the 2048-byte sector payload unchanged so its SHA-256 matches.
        target = MAP02_LBA + 3
        with self.bin.open("r+b") as handle:
            handle.seek(target * SECTOR_BYTES + 12)
            handle.write(b"\x00\x00\x00")
        with self.assertRaisesRegex(ValueError, "MSF address"):
            self.call()

    def test_different_map02_resource_profile_is_not_accepted(self):
        result = self.call(expected_map02_sha256=hashlib.sha256(b"other profile").hexdigest())
        self.assertFalse(result["map02_prs_matches_expected_profile"])
        self.assertFalse(result["media_preflight_ready_for_owner_replay"])

    def test_no_private_full_image_fingerprint_is_printed_by_default(self):
        report = self.call()
        self.assertFalse(report["full_bin_sha256_requested"])
        self.assertIsNone(report["full_bin_sha256_verified"])
        self.assertTrue(report["media_preflight_ready_for_owner_replay"])

    def test_full_image_digest_identity_matched_when_explicitly_requested(self):
        synthetic_digest = hashlib.sha256(b"fictional full image").hexdigest()
        with patch(
            "tools.map02_private_disc_movie_preflight._full_image_sha256",
            return_value=synthetic_digest,
        ) as hashing:
            report = self.call(
                verify_full_bin_sha256=True,
                expected_bin_sha256=synthetic_digest,
            )
        hashing.assert_called_once()
        self.assertTrue(report["full_bin_sha256_requested"])
        self.assertTrue(report["full_bin_sha256_verified"])
        self.assertTrue(report["media_preflight_ready_for_owner_replay"])
        self.assertNotIn(synthetic_digest, json.dumps(report))

    def test_full_image_digest_mismatch_blocks_replay(self):
        synthetic_digest = hashlib.sha256(b"fictional expected image").hexdigest()
        with patch(
            "tools.map02_private_disc_movie_preflight._full_image_sha256",
            return_value=hashlib.sha256(b"fictional different image").hexdigest(),
        ):
            report = self.call(
                verify_full_bin_sha256=True,
                expected_bin_sha256=synthetic_digest,
            )
        self.assertTrue(report["map02_prs_matches_expected_profile"])
        self.assertTrue(report["disc_size_matches_audited_profile"])
        self.assertTrue(report["full_bin_sha256_requested"])
        self.assertFalse(report["full_bin_sha256_verified"])
        self.assertFalse(report["media_preflight_ready_for_owner_replay"])

    def test_full_image_digest_on_wrong_size_fails_without_hashing(self):
        sectors = MAP02_LBA + (MAP02_BYTES + USER_DATA_BYTES - 1) // USER_DATA_BYTES
        with self.bin.open("r+b") as handle:
            handle.truncate(sectors * SECTOR_BYTES)
        with patch(
            "tools.map02_private_disc_movie_preflight._full_image_sha256",
        ) as hashing:
            report = self.call(
                verify_full_bin_sha256=True,
                expected_bin_sha256=hashlib.sha256(b"fictional").hexdigest(),
            )
        hashing.assert_not_called()
        self.assertTrue(report["full_bin_sha256_requested"])
        self.assertFalse(report["full_bin_sha256_verified"])
        self.assertFalse(report["media_preflight_ready_for_owner_replay"])

    def test_full_image_digest_requires_valid_private_reference(self):
        with self.assertRaisesRegex(ValueError, "private lowercase SHA-256"):
            self.call(verify_full_bin_sha256=True)
        with self.assertRaisesRegex(ValueError, "without verification"):
            self.call(expected_bin_sha256="f" * 64)

    def test_full_image_digest_streams_small_synthetic_file(self):
        miniature = self.root / "nonretail-payload.bin"
        payload = b"TEST-ONLY-BIN" * 50000
        miniature.write_bytes(payload)
        fd = os.open(miniature, os.O_RDONLY)
        try:
            with patch(
                "tools.map02_private_disc_movie_preflight.FULL_HASH_CHUNK_BYTES",
                513,
            ):
                self.assertEqual(
                    _full_image_sha256(fd, len(payload)),
                    hashlib.sha256(payload).hexdigest(),
                )
        finally:
            os.close(fd)

    def test_read_owner_private_full_bin_digest_reference(self):
        reference = self.root / "owner-only.sha256"
        digest = hashlib.sha256(b"invented original-image substitute").hexdigest()
        reference.write_text(digest + "\n", encoding="ascii")
        reference.chmod(0o600)
        self.assertEqual(read_private_full_bin_sha256(reference), digest)

    def test_reject_world_readable_or_symlinked_digest_reference(self):
        if os.name == "nt":
            self.skipTest("POSIX mode bit enforcement not applicable")
        reference = self.root / "unsafe.sha256"
        reference.write_text("b" * 64 + "\n", encoding="ascii")
        reference.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "user-private"):
            read_private_full_bin_sha256(reference)
        reference.chmod(0o600)
        link = self.root / "link.sha256"
        link.symlink_to(reference)
        with self.assertRaisesRegex(ValueError, "nonsymlink"):
            read_private_full_bin_sha256(link)

    def test_reject_malformed_private_reference(self):
        reference = self.root / "malformed.sha256"
        reference.write_text("A" * 64, encoding="ascii")
        reference.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "lowercase"):
            read_private_full_bin_sha256(reference)
        reference.write_text("invalid", encoding="ascii")
        with self.assertRaisesRegex(ValueError, "64 hex"):
            read_private_full_bin_sha256(reference)

    def test_different_volume_id_is_not_accepted(self):
        self._write_disc(volume_id="SLUS_99999")
        result = self.call()
        self.assertFalse(result["disc_volume_id_matches_audited_profile"])
        self.assertFalse(result["media_preflight_ready_for_owner_replay"])

    def test_invalid_iso9660_pvd_is_rejected(self):
        self._write_disc(valid_pvd=False)
        with self.assertRaisesRegex(ValueError, "descriptor is invalid"):
            self.call()

    def test_audio_or_non_mode2_cue_layout_is_rejected(self):
        self.cue.write_text(
            'FILE "fictional.bin" BINARY\nTRACK 01 AUDIO\nINDEX 01 00:00:00\n',
            encoding="ascii",
        )
        with self.assertRaisesRegex(ValueError, "unsupported CUE layout|expected one"):
            self.call()

    def test_cue_path_traversal_is_rejected(self):
        self.cue.write_text(
            'FILE "../fictional.bin" BINARY\n'
            'TRACK 01 MODE2/2352\nINDEX 01 00:00:00\n',
            encoding="ascii",
        )
        with self.assertRaisesRegex(ValueError, "sibling BIN"):
            self.call()

    def test_parent_directory_inside_git_checkout_is_rejected(self):
        (self.root / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "outside Git"):
            self.call()

    def test_symlinked_bin_is_rejected(self):
        actual = self.root / "real.bin"
        self.bin.rename(actual)
        self.bin.symlink_to(actual)
        with self.assertRaisesRegex(ValueError, "nonsymlink"):
            self.call()

    def test_wrong_movie_game_header_returns_not_ready(self):
        write_movie(self.movie, game="Vandal Hearts (Japan)")
        result = self.call()
        self.assertFalse(result["movie_header_matches_vandal_hearts_usa_psx_octoshock"])
        self.assertFalse(result["media_preflight_ready_for_owner_replay"])

    def test_wrong_movie_sync_returns_not_ready(self):
        wrong_sync = json.dumps({"o":{"FIOConfig":{
            "Devices8":[2,1,0,0,0,0,0,0],
            "Memcards":[False,False], "Multitaps":[False,False],
        }}})
        write_movie(self.movie, sync=wrong_sync)
        result = self.call()
        self.assertFalse(result["movie_sync_matches_one_controller_no_cards"])
        self.assertFalse(result["media_preflight_ready_for_owner_replay"])

    def test_report_contains_no_paths_hashes_or_asset_bytes(self):
        result = self.call()
        rendered = json.dumps(result)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn(hashlib.sha256(self.map_data).hexdigest(), rendered)
        self.assertNotIn("fictional.bin", rendered)
        self.assertFalse(result["private_asset_paths_or_hashes_reported"])
        self.assertFalse(result["private_assets_uploaded"])


if __name__ == "__main__":
    unittest.main()
