#!/usr/bin/env python3
"""Relocatable-link all verified asset-free original PC code and MAP02 observers.

This is intentionally *not* a complete executable: the pinned public port
requires user-owned retail assets and PsyQ KROMDAT for four omitted objects.
Only 85 public game modules and 33 backend/diagnostic objects are linked
by ld -r. Undefined ordinary original-game symbols are expected; unresolved
vh_map02_ observer symbols, missing original API exports, source drift or a
linked executable fail closed. No original image or private journal is used.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from tools.check_map02_cycle_make_plan import BUILD, preflight, clean_make_environment
from tools.check_map02_cycle_object_inventory import audit_objects
from tools.check_map02_elf_code_witness import (
    compare_function_images, function_images,
)

OUTPUT = "map02-public-original-cd-gpu-reloc.o"
REQUIRED_SYMBOLS = (
    "LoadCdFile", "ContinueLoadingCdFile", "CdRead", "DrawOTag",
    "vh_map02_cycle_load", "vh_map02_cycle_draw_start",
    "vh_map02_cd_read_finish", "vh_map02_stage_private_pair",
    "vh_map02_scope_begin_frame", "vh_map02_edges_begin_frame",
    "vh_map02_pc_capture_preoverlay",
)


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def stable_object_input(path):
    """Double-read one original ELF object and bind its pathname/inode.

    Objects are produced by the pinned public GNU Make step. They need not
    be private 0600 outputs, but must never be symlinked, hardlinked, or
    writable by another owner. Repeated checks cover identity swaps.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)

        def identity(item):
            return (item.st_dev, item.st_ino, item.st_uid,
                    stat.S_IMODE(item.st_mode), item.st_nlink,
                    item.st_size, item.st_mtime_ns, item.st_ctime_ns)

        anchor = identity(info)
        if (not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) & 0o022
                or info.st_size < 256):
            raise ValueError("untrusted public original PC input ELF object")

        def check_identity():
            if (identity(os.fstat(fd)) != anchor
                    or identity(os.stat(path, follow_symlinks=False)) != anchor):
                raise ValueError("original PC input ELF object identity changed")

        check_identity()
        hashes = []
        for _ in range(2):
            os.lseek(fd, 0, os.SEEK_SET)
            hashed = hashlib.sha256()
            read_total = 0
            while True:
                block = os.read(fd, 1024 * 1024)
                if not block:
                    break
                read_total += len(block)
                hashed.update(block)
            if read_total != info.st_size:
                raise ValueError("original PC input ELF object short read")
            check_identity()
            hashes.append(hashed.hexdigest())
        if hashes[0] != hashes[1]:
            raise ValueError("original PC input ELF object bytes changed")
        return (hashes[0], anchor)
    finally:
        os.close(fd)


def sealed_input_fd(path, expected, *, index):
    """Read a verified original object into Linux kernel-sealed anonymous RAM.

    GNU ld receives a /proc/self/fd handle, never the mutable upstream path.
    An unsupported memfd/sealing environment must fail closed, not silently
    fall back to unprotected filesystem inputs.
    """
    if not (hasattr(os, "memfd_create") and hasattr(os, "MFD_ALLOW_SEALING")
            and all(hasattr(fcntl, name) for name in
                    ("F_ADD_SEALS", "F_GET_SEALS", "F_SEAL_SEAL",
                     "F_SEAL_GROW", "F_SEAL_SHRINK", "F_SEAL_WRITE"))):
        raise ValueError("Linux sealed memory input required for original PC link")

    source_fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    sealed_fd = None
    try:
        original = os.fstat(source_fd)
        identity = (
            original.st_dev, original.st_ino, original.st_uid,
            stat.S_IMODE(original.st_mode), original.st_nlink,
            original.st_size, original.st_mtime_ns, original.st_ctime_ns)
        if identity != expected[1]:
            raise ValueError("original PC object changed before sealed copy")
        if (os.stat(path, follow_symlinks=False).st_ino != original.st_ino
                or os.stat(path, follow_symlinks=False).st_dev != original.st_dev):
            raise ValueError("original PC object pathname replaced before copy")

        sealed_fd = os.memfd_create(
            "vh-map02-verified-object-%03d" % index,
            flags=os.MFD_ALLOW_SEALING | getattr(os, "MFD_CLOEXEC", 0))
        hashed = hashlib.sha256()
        count = 0
        while True:
            block = os.read(source_fd, 1024 * 1024)
            if not block:
                break
            count += len(block)
            hashed.update(block)
            data = memoryview(block)
            while data:
                written = os.write(sealed_fd, data)
                if written <= 0:
                    raise ValueError("short sealed original PC object write")
                data = data[written:]
        if (count != original.st_size or hashed.hexdigest() != expected[0]
                or (original.st_dev, original.st_ino, original.st_uid,
                    stat.S_IMODE(original.st_mode), original.st_nlink,
                    original.st_size, original.st_mtime_ns,
                    original.st_ctime_ns) != expected[1]):
            raise ValueError("original PC object bytes changed while sealing")
        after = os.fstat(source_fd)
        end_identity = (
            after.st_dev, after.st_ino, after.st_uid,
            stat.S_IMODE(after.st_mode), after.st_nlink,
            after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        named = os.stat(path, follow_symlinks=False)
        if (end_identity != expected[1]
                or (named.st_dev, named.st_ino, named.st_uid,
                    stat.S_IMODE(named.st_mode), named.st_nlink,
                    named.st_size, named.st_mtime_ns,
                    named.st_ctime_ns) != expected[1]):
            raise ValueError("original PC object changed during sealed copy")

        required = (fcntl.F_SEAL_SEAL | fcntl.F_SEAL_WRITE |
                    fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK)
        fcntl.fcntl(sealed_fd, fcntl.F_ADD_SEALS, required)
        if fcntl.fcntl(sealed_fd, fcntl.F_GET_SEALS) & required != required:
            raise ValueError("original PC input ELF memory seals unavailable")
        os.lseek(sealed_fd, 0, os.SEEK_SET)
        check = hashlib.sha256()
        while True:
            block = os.read(sealed_fd, 1024 * 1024)
            if not block:
                break
            check.update(block)
        if check.hexdigest() != expected[0]:
            raise ValueError("sealed original PC input differs from source")
        return sealed_fd
    except BaseException:
        if sealed_fd is not None:
            os.close(sealed_fd)
        raise
    finally:
        os.close(source_fd)


def stable_relocatable_output(path, *, expected=None):
    """Bind the partial ELF's bytes and inode to two reads of one descriptor.

    A same-byte replacement at the output pathname is not equivalent to
    retaining the linked object. This is a bounded audit, not a filesystem
    lock against an attacker who can concurrently modify owner-owned files.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)

        def identity(item):
            return (item.st_dev, item.st_ino, item.st_uid,
                    stat.S_IMODE(item.st_mode), item.st_nlink,
                    item.st_size, item.st_mtime_ns, item.st_ctime_ns)

        anchor = identity(info)
        if (not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_size < 1024):
            raise ValueError("untrusted original PC partial ELF output metadata")

        def check_identity():
            if (identity(os.fstat(fd)) != anchor
                    or identity(os.stat(path, follow_symlinks=False)) != anchor):
                raise ValueError("original PC partial ELF output inode or metadata changed")

        check_identity()
        results = []
        for _ in range(2):
            os.lseek(fd, 0, os.SEEK_SET)
            hashed = hashlib.sha256()
            count = 0
            while True:
                block = os.read(fd, 1024 * 1024)
                if not block:
                    break
                hashed.update(block)
                count += len(block)
            if count != info.st_size:
                raise ValueError("original PC partial ELF output short descriptor read")
            check_identity()
            results.append(hashed.hexdigest())
        if results[0] != results[1]:
            raise ValueError("original PC partial ELF output bytes changed")
        proof = (results[0], anchor)
        if expected is not None and proof != expected:
            raise ValueError("original PC partial ELF output differs from linked proof")
        return proof
    finally:
        os.close(fd)


def make_inventory(upstream, bundle, *, make="make"):
    pc = Path(upstream).absolute() / "platform/pc"
    overlay = Path(bundle).absolute() / "map02_cycle.mk"
    eval_target = (
        "map02-public-reloc-inventory:;@printf '%s\\n' "
        "'$(VH_MAP02_PUBLIC_CODE_OBJS)' "
        "'$(VH_MAP02_PUBLIC_BACKEND_OBJS)'"
    )
    result = subprocess.run(
        [make, "-s", "-f", "Makefile", "-f", str(overlay),
         "--eval", eval_target, "map02-public-reloc-inventory",
         "BUILD_DIR=" + BUILD, "REGION=us", "NO_WEBP=1",
         "NO_HDVIDEO=1"],
        cwd=pc, env=clean_make_environment(), capture_output=True,
        text=True, timeout=60, check=False)
    if result.returncode:
        raise ValueError("original public code Make inventory unavailable")
    lines = result.stdout.splitlines()
    if len(lines) != 2:
        raise ValueError("original game/backend GNU Make inventories incomplete")
    return [line.split() for line in lines]


def function_code_sha256(path, symbols, *, pass_fds=()):
    """Hash exact original ELF FUNC machine bytes in executable sections.

    The ELF symbol points to an in-section offset (ET_REL); GNU readelf's
    section file offset identifies the actual bytes. The caller passes
    kernel-sealed input/output paths, not mutable original source paths.
    """
    section_result = subprocess.run(
        ["readelf", "-W", "-S", str(path)], capture_output=True,
        text=True, timeout=30, check=False, pass_fds=pass_fds)
    symbol_result = subprocess.run(
        ["readelf", "-W", "-s", str(path)], capture_output=True,
        text=True, timeout=30, check=False, pass_fds=pass_fds)
    if section_result.returncode or symbol_result.returncode:
        raise ValueError("original PC ELF code fingerprint metadata unavailable")
    sections = {}
    for line in section_result.stdout.splitlines():
        matched = re.match(r"^\s*\[\s*(\d+)\]\s+(.+)$", line)
        if not matched:
            continue
        cells = matched.group(2).split()
        if (len(cells) >= 7 and cells[1] == "PROGBITS"
                and "A" in cells[6] and "X" in cells[6]
                and "W" not in cells[6]):
            try:
                sections[matched.group(1)] = (
                    int(cells[2], 16), int(cells[3], 16),
                    int(cells[4], 16))
            except ValueError:
                raise ValueError("original PC ELF code fingerprint section invalid") from None

    definitions = {name: [] for name in symbols}
    for line in symbol_result.stdout.splitlines():
        cells = line.split()
        if (len(cells) >= 8 and cells[0].endswith(":")
                and cells[0][:-1].isdigit() and cells[7] in definitions):
            definitions[cells[7]].append(cells)
    with open(path, "rb") as stream:
        raw = stream.read()
    fingerprints = {}
    for name, entries in definitions.items():
        if (len(entries) != 1
                or entries[0][3:5] != ["FUNC", "GLOBAL"]
                or entries[0][6] not in sections):
            raise ValueError("original PC ELF code fingerprint FUNC invalid")
        sym = entries[0]
        section_address, file_offset, section_size = sections[sym[6]]
        try:
            start = int(sym[1], 16) - section_address
            size = int(sym[2], 16) if sym[2].startswith("0x") else int(sym[2], 10)
        except ValueError:
            raise ValueError("original PC ELF code fingerprint range invalid") from None
        if (start < 0 or size < 1 or start + size > section_size
                or file_offset + section_size > len(raw)):
            raise ValueError("original PC ELF code fingerprint range invalid")
        code = raw[file_offset + start:file_offset + start + size]
        fingerprints[name] = hashlib.sha256(code).hexdigest()
    return fingerprints


def inspect_sealed_export_origins(names, sealed, *, with_sizes=False):
    """Attribute each required strong code export to exactly one sealed .o.

    This checks the compiler inputs consumed by ld -r, rather than trusting
    a symbol that appears only after linking. Source names are public
    Make-inventory paths; no private retail paths enter the witness.
    """
    if len(names) != len(sealed):
        raise ValueError("MAP02 original code source/descriptor count mismatch")
    owners = {name: [] for name in REQUIRED_SYMBOLS}
    for source, fd in zip(names, sealed):
        result = subprocess.run(
            ["nm", "-g", "-S", "--defined-only", f"/proc/self/fd/{fd}"],
            pass_fds=(fd,), capture_output=True, text=True,
            timeout=30, check=False)
        if result.returncode:
            raise ValueError("cannot examine sealed original input ELF exports")
        for line in result.stdout.splitlines():
            cells = line.split()
            if len(cells) < 2:
                continue
            symbol = cells[-1]
            if symbol in owners:
                size = None
                if len(cells) >= 4:
                    try:
                        size = int(cells[-3], 16)
                    except ValueError:
                        pass
                owners[symbol].append((source, cells[-2], size))
    if any(len(values) != 1 or values[0][1] != "T"
           for values in owners.values()):
        raise ValueError("original CD/GPU or observer sealed input export absent/duplicated")
    paths = {name: owners[name][0][0] for name in REQUIRED_SYMBOLS}
    if not with_sizes:
        return paths
    if any(owners[name][0][2] is None or owners[name][0][2] < 1
           for name in REQUIRED_SYMBOLS):
        raise ValueError("original CD/GPU sealed input function size unavailable")
    return paths, {name: owners[name][0][2] for name in REQUIRED_SYMBOLS}


def check_elf_function_sections(path, *, pass_fds=(), expected_source_sizes=None):
    """Require original API entrypoints to be sized global ELF FUNC symbols.

    A global NOTYPE label inside .text is reported as 'T' by nm but must
    not impersonate an original C function. Use the same sealed descriptor
    as readelf -h and nm during partial-ELF inspection.
    """
    section_result = subprocess.run(
        ["readelf", "-W", "-S", str(path)], capture_output=True,
        text=True, timeout=30, check=False, pass_fds=pass_fds)
    symbol_result = subprocess.run(
        ["readelf", "-W", "-s", str(path)], capture_output=True,
        text=True, timeout=30, check=False, pass_fds=pass_fds)
    if section_result.returncode or symbol_result.returncode:
        raise ValueError("original PC ELF section/function symbols unavailable")
    code_sections = {}
    for line in section_result.stdout.splitlines():
        match = re.match(r"^\s*\[\s*(\d+)\]\s+(.+)$", line)
        if not match:
            continue
        cells = match.group(2).split()
        # GNU readelf -W -S: name type addr off size ES flags link info align.
        # For ET_REL, symbol values are offsets relative to their sections.
        if (len(cells) >= 7 and cells[1] == "PROGBITS"
                and "A" in cells[6] and "X" in cells[6]
                and "W" not in cells[6]):
            try:
                bounds = (int(cells[2], 16), int(cells[4], 16))
            except ValueError:
                raise ValueError("original PC ELF code section bounds invalid") from None
            if match.group(1) in code_sections or bounds[1] < 1:
                raise ValueError("original PC ELF code section bounds invalid")
            code_sections[match.group(1)] = bounds
    if not code_sections:
        raise ValueError("original PC ELF executable code sections unavailable")
    exported = {name: [] for name in REQUIRED_SYMBOLS}
    for line in symbol_result.stdout.splitlines():
        cells = line.split()
        # GNU readelf -W -s: num value size type bind vis ndx name
        if (len(cells) < 8 or not cells[0].endswith(":")
                or not cells[0][:-1].isdigit()):
            continue
        name = cells[7]
        if name in exported:
            exported[name].append(cells)
    ranges_by_section = {}
    for name, candidates in exported.items():
        if (len(candidates) != 1
                or candidates[0][3:5] != ["FUNC", "GLOBAL"]
                or candidates[0][6] not in code_sections):
            raise ValueError("original CD/GPU or observer ELF FUNC export invalid")
        try:
            start = int(candidates[0][1], 16)
            size = int(candidates[0][2], 0)
        except ValueError:
            raise ValueError("original CD/GPU or observer ELF FUNC bounds invalid") from None
        if (expected_source_sizes is not None
                and (name not in expected_source_sizes
                     or size != expected_source_sizes[name])):
            raise ValueError("original CD/GPU linked ELF FUNC size differs from sealed input")
        section_start, section_size = code_sections[candidates[0][6]]
        # Checking only Ndx and nonzero size accepts a forged FUNC symbol
        # placed after .text or a huge size extending beyond its section.
        if (size < 1 or start < section_start
                or start >= section_start + section_size
                or size > section_start + section_size - start):
            raise ValueError("original CD/GPU or observer ELF FUNC bounds invalid")
        ranges_by_section.setdefault(candidates[0][6], []).append(
            (start, start + size, name))
    # A global FUNC alias may have its own nonzero size and legal .text
    # section index while sharing bytes with an unrelated original export.
    # The required entrypoints must identify disjoint executable spans.
    for section_ranges in ranges_by_section.values():
        section_ranges.sort()
        for previous, current in zip(section_ranges, section_ranges[1:]):
            if current[0] < previous[1]:
                raise ValueError("original CD/GPU or observer ELF FUNC ranges overlap")
    return len(exported)


def summarize_partial_elf_undefined_symbols(nm_output):
    """Aggregate external symbol gaps without publishing symbol names.

    A partial link is NOT a final executable. GNU nm -u may list strong
    undefined (U) and optional weak undefined (w/v) imports. Capture their
    exact stable counts and a digest of the strong-name set so later work
    can tell if the public link dependency boundary moved, but never
    confuse the count with actual missing libraries or private assets.
    """
    strong = set()
    weak = set()
    for line in nm_output.splitlines():
        fields = line.split()
        if not fields:
            continue
        if len(fields) != 2 or fields[0] not in ("U", "w", "v"):
            raise ValueError("original PC partial ELF has unexpected undefined nm row")
        kind, symbol = fields
        if kind == "U":
            strong.add(symbol)
        else:
            weak.add(symbol)
    serialized = json.dumps(
        sorted(strong), ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return {
        "partial_elf_unresolved_strong_symbol_count": len(strong),
        "partial_elf_unresolved_weak_symbol_count": len(weak),
        "partial_elf_unresolved_strong_symbols_sha256":
            hashlib.sha256(serialized).hexdigest(),
    }


def inspect_relocatable(path, *, pass_fds=(), expected_source_sizes=None):
    header = subprocess.run(
        ["readelf", "-h", str(path)], capture_output=True,
        text=True, timeout=30, check=False, pass_fds=pass_fds)
    if header.returncode or not re.search(
            r"^\s*Type:\s+REL\s", header.stdout, re.M):
        raise ValueError("public code proof must be a relocatable ELF, not a game")
    exports = subprocess.run(
        ["nm", "-g", "--defined-only", str(path)],
        capture_output=True, text=True, timeout=30, check=False,
        pass_fds=pass_fds)
    undefined = subprocess.run(
        ["nm", "-u", str(path)],
        capture_output=True, text=True, timeout=30, check=False,
        pass_fds=pass_fds)
    if exports.returncode or undefined.returncode:
        raise ValueError("cannot examine linked original code symbols")
    # nm -g --defined-only includes weak functions (W) and global data
    # objects (B/D). Neither is a strong original C function export.
    # A name match alone cannot prove the CD/GPU callback's code is present.
    definitions = [
        (fields[-1], fields[-2])
        for line in exports.stdout.splitlines()
        if len(fields := line.split()) >= 2
    ]
    if any(
            sum(name == wanted and kind == "T"
                for name, kind in definitions) != 1
            or sum(name == wanted for name, _ in definitions) != 1
            for wanted in REQUIRED_SYMBOLS):
        raise ValueError("original CD/GPU or in-process observer strong code export absent/duplicated")
    if any(re.search(r"\bU\s+vh_map02_\w+", line)
           for line in undefined.stdout.splitlines()):
        raise ValueError("combined original PC code has unresolved MAP02 observer hooks")
    unresolved = summarize_partial_elf_undefined_symbols(undefined.stdout)
    function_count = check_elf_function_sections(
        path, pass_fds=pass_fds, expected_source_sizes=expected_source_sizes)
    return {
        "original_cd_gpu_and_vram_exports_verified": function_count,
        "ordinary_game_or_private_asset_symbols_may_be_unresolved": True,
        **unresolved,
    }


def audit_public_link(upstream, bundle, out_dir, *, make="make", linker="ld"):
    upstream = Path(upstream).absolute()
    bundle = Path(bundle).absolute()
    out_dir = Path(out_dir).absolute()
    preflight(upstream, bundle)
    before = audit_objects(upstream, bundle, make=make)
    objects = make_inventory(upstream, bundle, make=make)
    if len(objects[0]) != before["original_game_translation_units_compiled"] or (
            len(objects[1]) != before["native_backend_and_observer_objects_compiled"]):
        raise ValueError("expanded original code inventory differs from audited objects")
    names = objects[0] + objects[1]
    if len(set(names)) != len(names):
        raise ValueError("duplicate original object in relocatable input list")
    root = upstream / "platform/pc"
    root_build = root / BUILD
    sources = []
    for name in names:
        candidate = root / name
        if (not name.startswith(BUILD + "/") or not name.endswith(".o")
                or any(x in ("", ".", "..") for x in name.split("/"))
                or candidate.is_symlink() or not candidate.is_file()
                or root_build not in candidate.parents):
            raise ValueError("invalid original object passed to partial linker")
        sources.append(candidate)
    initial = [stable_object_input(path) for path in sources]
    # The public manifest contains only relative object names and hashes of
    # asset-free compiler outputs, never private original game data or paths.
    ordered_objects = [
        {"path": name, "sha256": proof[0]}
        for name, proof in zip(names, initial)
    ]
    input_manifest_sha256 = hashlib.sha256(json.dumps(
        ordered_objects, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    if (out_dir == upstream or upstream in out_dir.parents
            or out_dir.exists() or out_dir.is_symlink()):
        raise ValueError("original partial link requires a NEW private external directory")
    out_dir.mkdir(mode=0o700)
    if (out_dir.stat().st_uid != os.geteuid()
            or stat.S_IMODE(out_dir.stat().st_mode) != 0o700):
        raise ValueError("relocatable output directory not owner-only 0700")
    output = out_dir / OUTPUT
    # Bind each input to an immutable kernel-sealed anonymous memory file.
    # The child inherits ONLY the sealed read-only descriptors, so a changed
    # original pathname cannot redirect ld's inputs while it is running.
    sealed = []
    try:
        for index, (source, proof) in enumerate(zip(sources, initial)):
            sealed.append(sealed_input_fd(source, proof, index=index))
        if [stable_object_input(path) for path in sources] != initial:
            raise ValueError("original PC objects changed while sealing inputs")
        export_origins, export_source_sizes = inspect_sealed_export_origins(
            names, sealed, with_sizes=True)
        source_function_images = {}
        for source, fd in zip(names, sealed):
            owned = [name for name, owner in export_origins.items()
                     if owner == source]
            if owned:
                source_function_images.update(function_images(fd, owned))
        if set(source_function_images) != set(REQUIRED_SYMBOLS):
            raise ValueError("original CD/GPU sealed machine-code witness incomplete")
        combined = subprocess.run(
            [linker, "-r", "-o", str(output),
             *(f"/proc/self/fd/{fd}" for fd in sealed)],
            cwd=root, pass_fds=tuple(sealed), capture_output=True, text=True,
            timeout=150, check=False)
    finally:
        for fd in sealed:
            os.close(fd)
    if combined.returncode:
        # This is an intentionally incomplete original code link; any
        # failure is a genuine issue, not proof of game correctness.
        # Linker diagnostics can include private checkout locations and
        # arguments. Keep stderr out of the public audit/CLI output.
        raise ValueError("original public CD/GPU combined ld -r link failed")
    # Never chmod a pathname without first anchoring the linked inode.
    # The private output folder (0700) already prevents other users from
    # reading ld's temporary output before this 0600 permissions change.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(output, flags)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid() or info.st_nlink != 1
                or (info.st_dev, info.st_ino) !=
                   (os.stat(output, follow_symlinks=False).st_dev,
                    os.stat(output, follow_symlinks=False).st_ino)):
            raise ValueError("untrusted original PC partial ELF output")
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    output_proof = stable_relocatable_output(output)
    # readelf and both nm passes must inspect exactly the same immutable
    # bytes. A stable pathname check before/after each separate process is
    # insufficient if an owner can swap it while symbol tools execute.
    witness_fd = sealed_input_fd(output, output_proof, index=len(sources))
    try:
        checked = inspect_relocatable(
            f"/proc/self/fd/{witness_fd}", pass_fds=(witness_fd,),
            expected_source_sizes=export_source_sizes)
        code_witness = compare_function_images(
            source_function_images,
            function_images(witness_fd, REQUIRED_SYMBOLS))
    finally:
        os.close(witness_fd)
    stable_relocatable_output(output, expected=output_proof)
    if [stable_object_input(path) for path in sources] != initial:
        raise ValueError("original PC objects changed or swapped during public partial link")
    if audit_objects(upstream, bundle, make=make) != before:
        raise ValueError("pinned original public source/code inventory changed")
    preflight(upstream, bundle)
    stable_relocatable_output(output, expected=output_proof)
    return {
        "schema": "vh.map02.public-source-partial-elf-link.v1",
        "public_game_object_count": len(objects[0]),
        "backend_and_observer_object_count": len(objects[1]),
        "total_compiled_elf_objects": len(names),
        "ordered_object_input_manifest_sha256": input_manifest_sha256,
        "verified_original_export_input_owners": export_origins,
        "original_cd_gpu_source_function_sizes_matched": True,
        "original_cd_gpu_relocation_normalized_code_matched": True,
        **code_witness,
        "relocatable_elf_sha256": output_proof[0],
        **checked,
        "fully_linked_game_executable": False,
        "retail_game_assets_linked": False,
        "actual_gameplay_executed": False,
        "original_map02_rendering_proven": False,
        "physical_ps1_equivalence_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_original_pc_checkout", type=Path)
    parser.add_argument("private_prepared_bundle", type=Path)
    parser.add_argument("new_private_output_directory", type=Path)
    args = parser.parse_args()
    try:
        result = audit_public_link(
            args.pinned_original_pc_checkout, args.private_prepared_bundle,
            args.new_private_output_directory)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        # Avoid exposing private paths via tool or filesystem exceptions.
        parser.error("MAP02 public relocatable audit failed")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
