#!/usr/bin/env python3
"""Compare privately owned original US font bytes against a linked PC ELF.

A separate ELF32/ELF64 little-endian parser locates pc_kanji_charset2 in
an initialized, allocated read-only section backed by a readable PT_LOAD.
Only a Boolean is reported: never publish font contents or byte differences.
"""
import hashlib
import os
from pathlib import Path
import stat
import struct

FONT_SYMBOL = b"pc_kanji_charset2"
FONT_BYTES = 209 * 30
MAX_ELF = 512 * 1024 * 1024
MAX_TABLE = 32 * 1024 * 1024


def _inside(offset, length, total):
    return (isinstance(offset, int) and isinstance(length, int)
            and 0 <= offset <= total and 0 <= length <= total - offset)



def stable_owned_elf_sha256(binary):
    """Hash the same nonlinked owned executable inode from start to finish.

    Return only the full ELF hash. Never disclose private paths or binary data.
    Compare the final pathname identity to the original open descriptor,
    rejecting symlink/hardlink replacement and concurrent metadata mutation.
    """
    path = Path(binary)
    if path.is_symlink():
        raise ValueError("private ELF digest input symlinked")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise ValueError("private ELF digest input unavailable") from None
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid()
                or before.st_nlink != 1
                or not (before.st_mode & stat.S_IXUSR)
                or not 0 < before.st_size <= MAX_ELF):
            raise ValueError("private ELF digest input is not owned executable")
        identity = lambda st: (st.st_dev, st.st_ino, st.st_uid, st.st_mode,
                               st.st_nlink, st.st_size, st.st_mtime_ns,
                               st.st_ctime_ns)
        def hash_pass():
            digest = hashlib.sha256()
            for offset in range(0, before.st_size, 1 << 20):
                length = min(1 << 20, before.st_size - offset)
                block = os.pread(fd, length, offset)
                if len(block) != length:
                    raise ValueError("private ELF digest short read")
                digest.update(block)
            return digest.digest()

        # Verify *both* passes on the same descriptor. Metadata-only checks
        # cannot distinguish in-place changes with restored timestamps, and
        # a one-pass hash may silently describe a mixture of two file versions.
        first_digest = hash_pass()
        if identity(os.fstat(fd)) != identity(before):
            raise ValueError("private ELF digest input changed during hashing")
        second_digest = hash_pass()
        if first_digest != second_digest:
            raise ValueError("private ELF digest bytes changed between read passes")
        try:
            named = os.stat(path, follow_symlinks=False)
        except OSError:
            raise ValueError("private ELF digest input replaced") from None
        if (identity(os.fstat(fd)) != identity(before)
                or identity(named) != identity(before)):
            raise ValueError("private ELF digest input changed during hashing")
        return first_digest.hex()
    finally:
        os.close(fd)


def check_linked_font_bytes(binary, expected):
    """Fail closed unless exactly one genuine, loaded symbol has these bytes."""
    if type(expected) is not bytes or len(expected) != FONT_BYTES:
        raise ValueError("invalid original US font comparison input")
    binary = Path(binary)
    if binary.is_symlink():
        raise ValueError("linked original font ELF cannot be symlinked")
    try:
        fd = os.open(binary, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise ValueError("original font ELF unavailable") from None
    try:
        first = os.fstat(fd)
        if (not stat.S_ISREG(first.st_mode) or first.st_uid != os.geteuid()
                or first.st_nlink != 1 or not (first.st_mode & stat.S_IXUSR)
                or not 256 <= first.st_size <= MAX_ELF):
            raise ValueError("original font ELF is not an owned executable")
        total = first.st_size

        def chunk(offset, length):
            if not _inside(offset, length, total) or length > MAX_TABLE:
                raise ValueError("invalid original font ELF table bounds")
            data = os.pread(fd, length, offset)
            if len(data) != length:
                raise ValueError("incomplete original font ELF read")
            return data

        eh = chunk(0, 64)
        if eh[:4] != b"\x7fELF" or eh[5] != 1 or eh[6] != 1:
            raise ValueError("unsupported original font ELF encoding")
        elf_type, machine = struct.unpack_from("<HH", eh, 16)
        if eh[4] == 1:
            phoff, shoff = struct.unpack_from("<II", eh, 28)
            phentsize, phnum = struct.unpack_from("<HH", eh, 42)
            shentsize, shnum = struct.unpack_from("<HH", eh, 46)
            shfmt, syfmt, phfmt = "<IIIIIIIIII", "<IIIBBH", "<IIIIIIII"
        elif eh[4] == 2:
            phoff = struct.unpack_from("<Q", eh, 32)[0]
            shoff = struct.unpack_from("<Q", eh, 40)[0]
            phentsize, phnum = struct.unpack_from("<HH", eh, 54)
            shentsize, shnum = struct.unpack_from("<HH", eh, 58)
            shfmt, syfmt, phfmt = "<IIQQQQIIQQ", "<IBBHQQ", "<IIQQQQQQ"
        else:
            raise ValueError("unsupported original font ELF class")
        if (elf_type not in (2, 3) or machine not in (3, 62, 183)
                or shnum == 0 or phnum == 0):
            raise ValueError("original font input is not a host executable")
        shsize, sysize, phsize = (struct.calcsize(x) for x in
                                  (shfmt, syfmt, phfmt))
        if (shentsize != shsize or phentsize != phsize
                or not _inside(shoff, shnum * shsize, total)
                or not _inside(phoff, phnum * phsize, total)):
            raise ValueError("invalid original font ELF headers")
        shraw = chunk(shoff, shnum * shsize)
        sections = [struct.unpack_from(shfmt, shraw, i * shsize)
                    for i in range(shnum)]
        phraw = chunk(phoff, phnum * phsize)
        programs = [struct.unpack_from(phfmt, phraw, i * phsize)
                    for i in range(phnum)]
        candidates = []
        for symtab in sections:
            if symtab[1] != 2:  # SHT_SYMTAB; the stripped ELF must fail closed
                continue
            _, _, _, _, table_off, table_size, link, _, _, entsize = symtab
            if (link >= shnum or sections[link][1] != 3 or
                    entsize != sysize or table_size % sysize or
                    table_size > MAX_TABLE):
                raise ValueError("invalid original font symbol table")
            str_off, str_size = sections[link][4:6]
            if str_size > MAX_TABLE:
                raise ValueError("oversized original font string table")
            names = chunk(str_off, str_size)
            sym_bytes = chunk(table_off, table_size)
            for i in range(table_size // sysize):
                sym = struct.unpack_from(syfmt, sym_bytes, i * sysize)
                if eh[4] == 1:
                    nameidx, value, size, info, _, shndx = sym
                else:
                    nameidx, info, _, shndx, value, size = sym
                if nameidx >= len(names):
                    raise ValueError("invalid original font ELF symbol name")
                ending = names.find(b"\x00", nameidx)
                if ending < 0:
                    raise ValueError("invalid original font ELF symbol name")
                if names[nameidx:ending] != FONT_SYMBOL:
                    continue
                if ((info >> 4) not in (1, 2) or (info & 15) != 1
                        or size != FONT_BYTES):
                    raise ValueError("original font ELF symbol identity or size differs")
                if not (0 < shndx < shnum):
                    raise ValueError("original font ELF data section missing")
                section = sections[shndx]
                _, stype, flags, address, sec_off, sec_len, _, _, _, _ = section
                if stype != 1 or not (flags & 2) or flags & 1:
                    raise ValueError("original font ELF symbol is not read-only loaded data")
                if value < address or value - address + size > sec_len:
                    raise ValueError("original font symbol escapes loaded section")
                offset = sec_off + (value - address)
                if not _inside(offset, size, total):
                    raise ValueError("original font section is not file-backed")
                matched = False
                for ph in programs:
                    if eh[4] == 1:
                        typ, file_off, vaddr, _, filesz, _, pflags, _ = ph
                    else:
                        typ, pflags, file_off, vaddr, _, filesz, _, _ = ph
                    if (typ == 1 and pflags & 4 and not (pflags & 2)
                            and value >= vaddr and
                            value - vaddr + size <= filesz
                            and file_off + value - vaddr == offset):
                        matched = True
                        break
                if not matched:
                    raise ValueError("original font ELF is not in a read-only load segment")
                candidates.append(offset)
        if len(candidates) != 1:
            raise ValueError("original font ELF requires one initialized glyph symbol")
        if chunk(candidates[0], FONT_BYTES) != expected:
            raise ValueError("linked original US font bytes differ from owned source")
        again = os.fstat(fd)
        try:
            current = os.stat(binary, follow_symlinks=False)
        except OSError:
            raise ValueError("original font ELF replaced during inspection") from None
        signature = lambda s: (s.st_dev, s.st_ino, s.st_uid, s.st_mode,
                               s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if (signature(first) != signature(again)
                or signature(first) != signature(current)
                or chunk(candidates[0], FONT_BYTES) != expected):
            raise ValueError("original font ELF changed during inspection")
    finally:
        os.close(fd)
    return {"linked_original_us_font_bytes_match": True,
            "original_font_bytes_disclosed": False,
            "original_map02_rendering_proven": False}
