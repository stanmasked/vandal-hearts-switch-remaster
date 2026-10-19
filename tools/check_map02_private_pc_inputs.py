#!/usr/bin/env python3
"""Check user-owned input readiness for the original US MAP02 full PC build.

This tool is intentionally local-only. It does NOT generate, download or
redistribute a retail executable, extracted data, PsyQ KROMDAT or BIOS. It
compares the input formats with the pinned original source/generators and
returns only a combined private-input digest and non-sensitive readiness
flags; never prints file contents, game path, or individual hashes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from tools.check_map02_original_extraction_anchors import (
    compare_data_ranges, compare_loaded_sections,
)
from tools.check_map02_original_inc_provenance import (_original_blob_sha1,
                                                      check_original_includes)

EXE = "SLUS_004.47"
US_EXE_MD5 = "596bb082a2de5f1fe977dd3d7e160b03"
US_FONT_SHA256 = "19b1dd839020e62a8a0f6dfc673c320da36105d9bc9bbce876aa151b7bd927a7"
FONT_LENGTH = 209 * 30
FONT_BIOS_OFFSET = 0x66000
BIOS_SIZE = 512 * 1024
ASSETS = ("801012e4.inc", "801009bc.inc", "80100e9c.inc")
FONT_GENERATOR = "platform/pc/tools/gen_kanji_font.py"
FONT_GENERATOR_BLOB_SHA1 = "67cf3aebe3dfd46467483d3899d10f04d2fe0c18"


def _checked_file(path, category, *, max_size=128 * 1024 * 1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("missing or linked private original input: " + category)
    st = path.stat()
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
            or st.st_size <= 0 or st.st_size > max_size):
        raise ValueError("invalid owner, type or size for original input: " + category)
    return path


def _hash_file(path, algorithm):
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _original_exe(path):
    path = _checked_file(path, "US PS-X executable", max_size=8 * 1024 * 1024)
    with path.open("rb") as stream:
        header = stream.read(0x800)
    if len(header) != 0x800 or not header.startswith(b"PS-X EXE"):
        raise ValueError("original US input is not a PS-X EXE")
    expected = 0x800 + int.from_bytes(header[0x1c:0x20], "little")
    if expected <= 0x800 or path.stat().st_size < expected:
        raise ValueError("original US PS-X executable is truncated")
    if _hash_file(path, "md5") != US_EXE_MD5:
        raise ValueError("original US PS-X executable does not match pinned retail identity")
    return _hash_file(path, "sha256")


def _original_elf(path):
    path = _checked_file(path, "matching-decomp extracted ELF")
    with path.open("rb") as stream:
        header = stream.read(64)
    if (len(header) < 52 or header[:4] != b"\x7fELF"
            or header[5] not in (1, 2)):
        raise ValueError("original decomp input is not an ELF")
    machine = int.from_bytes(
        header[18:20], "little" if header[5] == 1 else "big")
    if machine != 8:
        raise ValueError("original decomp input is not a MIPS PS1 ELF")
    return _hash_file(path, "sha256")


def _asset_file(path, kind):
    path = _checked_file(path, "extracted original asset " + kind,
                         max_size=32 * 1024 * 1024)
    if path.stat().st_size < 8:
        raise ValueError("original extracted asset is unexpectedly short: " + kind)
    return _hash_file(path, "sha256")


def _krom_font(path):
    path = _checked_file(path, "PsyQ KROMDAT or owned PS1 BIOS",
                         max_size=BIOS_SIZE)
    with path.open("rb") as stream:
        if path.stat().st_size == BIOS_SIZE:
            stream.seek(FONT_BIOS_OFFSET)
        glyph = stream.read(FONT_LENGTH)
    if len(glyph) != FONT_LENGTH or hashlib.sha256(
            glyph).hexdigest() != US_FONT_SHA256:
        raise ValueError("original PS1 font charset does not match pinned US generator")
    return _hash_file(path, "sha256")


def _pinned_font_generator(path):
    # A good KROM hash alone does not authenticate the Python source that
    # the original full-game Makefile will execute over that private font.
    path = _checked_file(path, "original pinned US font generator",
                         max_size=128 * 1024)
    content = path.read_bytes()
    if _original_blob_sha1(content) != FONT_GENERATOR_BLOB_SHA1:
        raise ValueError("original US font generator differs from pinned source")
    return hashlib.sha256(content).hexdigest()


def _input_identity(path, category):
    # Compare metadata at both boundaries, not just hashes. This detects
    # byte-identical inode swaps and in-place changes during the audit.
    path = _checked_file(path, category)
    st = path.stat()
    return (st.st_dev, st.st_ino, st.st_uid, st.st_mode, st.st_nlink,
            st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _audit_input(path, category, verifier):
    first = _input_identity(path, category)
    digest = verifier(path)
    if _input_identity(path, category) != first:
        raise ValueError("private original input changed during audit: " + category)
    return digest, first


def verify_private_pc_inputs(upstream, *, krom_source=None):
    upstream = Path(upstream).absolute()
    if upstream.is_symlink() or not upstream.is_dir():
        raise ValueError("original PC checkout missing or linked")
    # In this source-pinned checkout the compiler flag -I$(GAME_ROOT)
    # resolves src/{core,maps} quotes to <repo>/assets/*.inc.
    root = upstream
    if krom_source is None:
        krom_source = (root / "external/psy-q/3.6/PSYQ/BIN/KROMDAT.BIN")
    root_identity = _input_identity(root / EXE, "US PS-X executable")
    paths = [
        ("retail-us-exe", root / EXE, _original_exe),
        ("decomp-mips-elf", root / "build" / (EXE + ".elf"), _original_elf),
    ]
    # Source-provenance: the original Makefile's KROM-to-C generator is
    # executable code with access to a user-owned ROM. Do not bless a local
    # full-game build if that code differs from the pinned public checkout.
    generator_path = root / FONT_GENERATOR
    generator_digest, generator_identity = _audit_input(
        generator_path, "original-font-generator", _pinned_font_generator)
    snapshots = [("original-font-generator", generator_path,
                  _pinned_font_generator, generator_digest, generator_identity)]
    tokens = []
    for category, path, verifier in paths:
        digest, identity = _audit_input(path, category, verifier)
        tokens.append((category, digest))
        snapshots.append((category, path, verifier, digest, identity))
    # Compare selected source-pinned, non-proprietary-offset anchor *locations*
    # byte for byte across the user's original EXE and extracted MIPS ELF.
    # The raw compared bytes never leave the local verifier.
    anchors = compare_data_ranges(root / EXE,
                                  root / "build" / (EXE + ".elf"))
    if anchors["original_exe_and_mips_elf_data_anchors_match"] is not True:
        raise ValueError("retail decomp data anchors not verified")
    # Compare all initialized ELF runtime sections mapped into the original
    # PS-X loaded image, not only the three named data anchor locations.
    # Coverage gaps and outside-image allocations are NOT authenticated.
    mapped_sections = compare_loaded_sections(
        root / EXE, root / "build" / (EXE + ".elf"))
    if (mapped_sections["original_exe_and_mips_elf_loaded_sections_match"]
            is not True):
        raise ValueError("original extracted MIPS loaded sections not verified")
    # Verify all three generated C initializer include FILE BYTES against
    # the pinned original US EXE, not merely their presence or combined SHA.
    includes = check_original_includes(root)
    if includes["asset_includes_regenerated_and_identical"] != len(ASSETS):
        raise ValueError("original US asset includes not fully authenticated")
    for filename in ASSETS:
        category = "asset-" + filename
        path = root / "assets" / filename
        # Preserve the asset kind for existing category-specific failures.
        verifier = lambda p, name=filename: _asset_file(p, name)
        digest, identity = _audit_input(path, category, verifier)
        tokens.append((category, digest))
        snapshots.append((category, path, verifier, digest, identity))
    digest, identity = _audit_input(krom_source, "ps1-font", _krom_font)
    tokens.append(("ps1-font", digest))
    snapshots.append(("ps1-font", krom_source, _krom_font, digest, identity))

    # A successful check must describe ONE coherent set of inputs. In
    # particular, the ELF or an already-checked .inc must not be replaced
    # during the slow subprocess that regenerates the original includes.
    # Repeat full format/hash checks on all six private inputs and the
    # source-pinned font generator after all expensive checks are complete.
    for category, path, verifier, digest, identity in snapshots:
        if (_input_identity(path, category) != identity
                or verifier(path) != digest
                or _input_identity(path, category) != identity):
            raise ValueError("private original input changed during audit: " + category)
    if _input_identity(root / EXE, "US PS-X executable") != root_identity:
        raise ValueError("private original input changed during audit: retail-us-exe")
    # Bind path/category identity, digest and pinned order, without outputting
    # individual source input digests or original asset contents.
    combined = hashlib.sha256(
        json.dumps(tokens + [("original-font-generator", generator_digest)],
                   separators=(",", ":"), sort_keys=False).encode()
    ).hexdigest()
    return {
        "schema": "vh.map02.private-retail-input-readiness.v1",
        "private_original_input_categories_checked": len(tokens),
        "original_us_exe_matches_pinned_hash": True,
        "matching_decomp_mips_elf_present": True,
        "original_exe_and_mips_elf_data_anchors_match": True,
        "original_private_data_bytes_compared":
            anchors["original_private_data_bytes_compared"],
        "original_exe_and_mips_elf_loaded_sections_match": True,
        "original_allocated_sections_compared":
            mapped_sections["original_allocated_sections_compared"],
        "original_allocated_section_bytes_compared":
            mapped_sections["original_allocated_section_bytes_compared"],
        "unmapped_allocated_sections_not_authenticated":
            mapped_sections["unmapped_allocated_sections_not_authenticated"],
        "original_resource_includes_present": len(ASSETS),
        "original_resource_includes_match_owned_us_exe": True,
        "us_ps1_font_charset_verified": True,
        "pinned_original_font_generator_verified": True,
        "private_build_inputs_binding_sha256": combined,
        "full_pc_game_executable_linked": False,
        "actual_gameplay_executed": False,
        "original_map02_rendering_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_original_pc_checkout", type=Path)
    parser.add_argument("--krom-source", type=Path,
                        help="local original KROMDAT.BIN or owned 512-KiB PS1 BIOS")
    args = parser.parse_args()
    try:
        result = verify_private_pc_inputs(
            args.pinned_original_pc_checkout, krom_source=args.krom_source)
    except ValueError as exc:
        parser.error(str(exc))
    except OSError:
        parser.error("private original input verification failed")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
