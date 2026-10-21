#!/usr/bin/env python3
"""Actually link X11, XCB, Xau, Xdmcp static archives as ONE GNU group.

Source is the owner-private 1085-import public after-SDL2 MAP02 ET_REL;
no retail bytes, raw undefined names or private filesystem paths are logged.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

from tools.check_map02_private_incremental_link import (
    _check_abi, _confirm_owned, _open_owned, _private_output_dir, _unresolved,
    probe_private_incremental_link,
)
from tools.check_map02_private_provider_coverage import (
    audit_provider_coverage, read_private_manifest,
)
from tools.check_map02_public_sdl2_archive_witness import _copy_system_archive

SCHEMA = "vh.map02.public-sdl2-four-x11-xcb-xau-xdmcp-archive-group.v1"
XAU_COPY = "xau-system-candidate.a"
XDMCP_COPY = "xdmcp-system-candidate.a"


def measure_four_group(private_after_sdl2_manifest, after_sdl2_elf,
                       private_copied_x11, private_copied_xcb,
                       system_xau_archive, system_xdmcp_archive,
                       new_private_output_dir, *,
                       expected_after_sdl2_strong=1085):
    """Compare true four-archive native linker group with prior group."""
    if type(expected_after_sdl2_strong) is not int or expected_after_sdl2_strong < 0:
        raise ValueError("MAP02 four-archive expected import count invalid")
    if (Path(after_sdl2_elf).suffix != ".o"
            or any(Path(p).suffix != ".a" for p in
                   (private_copied_x11, private_copied_xcb,
                    system_xau_archive, system_xdmcp_archive))):
        raise ValueError("MAP02 four-archive native input suffix invalid")
    doc = read_private_manifest(private_after_sdl2_manifest)
    inputs = []
    try:
        for path in (after_sdl2_elf, private_copied_x11, private_copied_xcb):
            item = _open_owned(path, require_private=True)
            inputs.append(item)
            _check_abi(item)
        source, x11, xcb = inputs
        if (len({(x[2][0], x[2][1]) for x in inputs}) != 3
                or source[3] != doc["relocatable_elf_sha256"]):
            raise ValueError("MAP02 four-archive source or input identity differs")
        strong, weak = _unresolved(source)
        if (strong != doc["strong_symbols"] or weak != doc["weak_symbols"]
                or len(strong) != expected_after_sdl2_strong):
            raise ValueError("MAP02 four-archive source manifest differs")
        for x in inputs:
            _confirm_owned(x)

        root, _ = _private_output_dir(new_private_output_dir)
        # Two packages outside the repository, copied byte-for-byte to 0600.
        local_xau = root / XAU_COPY
        local_xdmcp = root / XDMCP_COPY
        xau_digest = _copy_system_archive(system_xau_archive, local_xau)
        xdmcp_digest = _copy_system_archive(system_xdmcp_archive, local_xdmcp)
        for path, digest in ((local_xau, xau_digest),
                             (local_xdmcp, xdmcp_digest)):
            x = _open_owned(path, require_private=True)
            inputs.append(x)
            _check_abi(x)
            if x[3] != digest:
                raise ValueError("MAP02 four-archive system copy SHA differs")
        if len({(x[2][0], x[2][1]) for x in inputs}) != 5:
            raise ValueError("MAP02 four-archive duplicate file identity")
        for x in inputs:
            _confirm_owned(x)

        archive_paths = [private_copied_x11, private_copied_xcb,
                         local_xau, local_xdmcp]
        coverage = audit_provider_coverage(private_after_sdl2_manifest,
                                            archive_paths)
        result = probe_private_incremental_link(
            private_after_sdl2_manifest, after_sdl2_elf, archive_paths,
            root / "linked", group_archives=True,
            expected_initial_strong_imports=expected_after_sdl2_strong)
        for x in inputs:
            _confirm_owned(x)
        if (coverage["original_strong_unresolved_count"] !=
                expected_after_sdl2_strong
                or coverage["candidate_provider_file_count"] != 4
                or coverage["strong_symbols_with_candidate_provider"] +
                   coverage["strong_symbols_without_candidate_provider"] !=
                   expected_after_sdl2_strong
                or result["source_partial_elf_sha256"] != source[3]
                or result["candidate_count"] != 4
                or result["candidate_archive_count"] != 4
                or result["archive_selection_strategy"] !=
                   "repeated_archive_group"
                or result["original_strong_import_count"] !=
                   expected_after_sdl2_strong
                or result["original_strong_imports_resolved_by_ld_r"] +
                   result["original_strong_imports_remaining_after_ld_r"] !=
                   expected_after_sdl2_strong
                or result["original_strong_imports_remaining_after_ld_r"] +
                   result["new_strong_imports_introduced_by_candidates"] !=
                   result["final_strong_import_count"]):
            raise ValueError("MAP02 four-archive native measurement inconsistent")
        return {
            "schema": SCHEMA,
            "input_after_sdl2_sha256": source[3],
            "copied_x11_sha256": x11[3],
            "copied_xcb_sha256": xcb[3],
            "copied_xau_sha256": xau_digest,
            "copied_xdmcp_sha256": xdmcp_digest,
            "linked_four_archive_elf_sha256": result["linked_candidate_elf_sha256"],
            "initial_after_sdl2_strong_undefined": expected_after_sdl2_strong,
            "original_with_any_of_four_strong_providers":
                coverage["strong_symbols_with_candidate_provider"],
            "original_with_multiple_of_four_strong_providers":
                coverage["strong_symbols_with_multiple_candidates"],
            "original_without_four_strong_providers":
                coverage["strong_symbols_without_candidate_provider"],
            "original_strong_imports_resolved":
                result["original_strong_imports_resolved_by_ld_r"],
            "original_strong_imports_remaining":
                result["original_strong_imports_remaining_after_ld_r"],
            "new_strong_imports_from_four_archives":
                result["new_strong_imports_introduced_by_candidates"],
            "final_strong_undefined_after_four_archives":
                result["final_strong_import_count"],
            "real_four_archive_group_ld_r_executed": True,
            "system_archive_origin_independently_attested": False,
            "retail_assets_linked": False,
            "fully_linked_game_executable": False,
            "authentic_map02_execution_proven": False,
        }
    finally:
        for x in inputs:
            os.close(x[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_after_sdl2_manifest", type=Path)
    parser.add_argument("owner_private_after_sdl2_elf", type=Path)
    parser.add_argument("private_copied_x11_archive", type=Path)
    parser.add_argument("private_copied_xcb_archive", type=Path)
    parser.add_argument("system_xau_archive", type=Path)
    parser.add_argument("system_xdmcp_archive", type=Path)
    parser.add_argument("new_private_output_dir", type=Path)
    args = parser.parse_args()
    try:
        data = measure_four_group(
            args.private_after_sdl2_manifest,
            args.owner_private_after_sdl2_elf,
            args.private_copied_x11_archive,
            args.private_copied_xcb_archive,
            args.system_xau_archive, args.system_xdmcp_archive,
            args.new_private_output_dir)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        parser.error("MAP02 public four-static-archive GNU ld-r probe failed")
    print(json.dumps(data, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
