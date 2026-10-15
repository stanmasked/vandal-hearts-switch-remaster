#!/usr/bin/env python3
"""Stage owner-supplied Vandal Hearts map 11 bank on a local SD card.

No proprietary bytes are bundled or uploaded. The optional Switch probe reads
exactly these two staged files from sdmc:/switch/vandal-hearts-remaster/
private-assets/. This is an isolated UV/CLUT fragment preview, not gameplay.
"""
import argparse
import hashlib
import json
from pathlib import Path

from inspect_vh_map_texture_bank import (
    LAND_BYTES, TEXTURE_BYTES, extract_mode2_file, inspect_bank,
)

AUDITED_RU_SHA = {
    "F_TEX01.DAT": "a3c6db4516930cdb2555cf7cda2456bcd118e5ec46737e2c320431d7b9a63b75",
    "LAND_DT.DAT": "e91891bad10efbc58ee010a52740c1510383529fcbf24eec3783e344cbcf773b",
}
MAP_NUMBER = 11
SLOT = 241
RELATIVE_DESTINATION = Path("switch/vandal-hearts-remaster/private-assets")


def stage_private_assets(texture, land, sd_root, strict_hashes=False):
    """Validate first, then stage without overwriting existing user data."""
    metadata = inspect_bank(texture, land, MAP_NUMBER)
    uvwh = metadata["slot_uvwh"][SLOT]
    clut_id = metadata["slot_clut_ids"][SLOT]
    if not (32 <= clut_id <= 47):
        raise ValueError("map 11 slot 241 does not use one of 16 local LAND_DT CLUT rows")
    u, v, w, h = uvwh
    if not (u <= 254 and v <= 254 and
            w >= 1 and h >= 1 and u + w < 256 and v + h < 256):
        raise ValueError("map 11 slot 241 UVWH is outside the 256x256 texture page")
    hashes = {
        "F_TEX01.DAT": hashlib.sha256(texture).hexdigest(),
        "LAND_DT.DAT": hashlib.sha256(land).hexdigest(),
    }
    if strict_hashes and hashes != AUDITED_RU_SHA:
        raise ValueError("source bytes do not match audited RU v1.6 SHA-256")

    target_dir = Path(sd_root) / RELATIVE_DESTINATION
    target_files = [
        target_dir / "F_TEX01.DAT",
        target_dir / "LAND_DT.DAT",
        target_dir / "source-manifest.json",
    ]
    if any(path.exists() or path.is_symlink() for path in target_files):
        raise FileExistsError("destination has existing assets; refusing to overwrite")
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "status": "local_user_provided_not_committed",
        "map_number": MAP_NUMBER,
        "slot": SLOT,
        "uvwh": uvwh,
        "local_clut_id": clut_id,
        "file_sha256": hashes,
        "audited_ru_v1_6_match": hashes == AUDITED_RU_SHA,
        "texture_bytes": TEXTURE_BYTES,
        "land_bytes": LAND_BYTES,
    }
    # Assets stay on the user's requested local SD root; only metadata
    # (not asset bytes) appears in stdout, the manifest or the public repo.
    target_files[0].write_bytes(texture)
    target_files[1].write_bytes(land)
    target_files[2].write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sources = p.add_mutually_exclusive_group(required=True)
    sources.add_argument("--texture", type=Path, help="local extracted F_TEX01.DAT")
    sources.add_argument("--raw-bin", type=Path, help="local 2352-byte-sector PS1 BIN")
    p.add_argument("--land", type=Path, help="local extracted LAND_DT.DAT")
    p.add_argument("--texture-lba", type=int)
    p.add_argument("--land-lba", type=int)
    p.add_argument("--sd-root", type=Path, required=True,
                   help="root of mounted Switch SD card (not GitHub checkout)")
    p.add_argument("--require-audited-ru-sha", action="store_true",
                   help="reject any image not identical to audited RU v1.6 resource hashes")
    args = p.parse_args(argv)
    if args.raw_bin:
        if args.land or args.texture_lba is None or args.land_lba is None:
            p.error("--raw-bin requires --texture-lba and --land-lba; omit --land")
        texture = extract_mode2_file(args.raw_bin, args.texture_lba, TEXTURE_BYTES)
        land = extract_mode2_file(args.raw_bin, args.land_lba, LAND_BYTES)
    else:
        if args.land is None or args.texture_lba is not None or args.land_lba is not None:
            p.error("--texture requires --land; omit both LBA options")
        if args.texture.stat().st_size != TEXTURE_BYTES or args.land.stat().st_size != LAND_BYTES:
            p.error("invalid input resource length")
        texture, land = args.texture.read_bytes(), args.land.read_bytes()
    try:
        report = stage_private_assets(
            texture, land, args.sd_root, args.require_audited_ru_sha)
    except (ValueError, FileExistsError, OSError) as exc:
        p.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
