"""Bounded, relocation-aware witness of public x86-64 ET_REL function bytes.

No user-owned retail data is read. Only immutable sealed GNU/Clang ELF64
relocatable inputs and outputs are accepted. Unsupported relocation kinds
in a required function fail closed; unrelocated instruction bytes must match.
"""
import hashlib
import json
import os
import struct

EHDR = struct.Struct("<16sHHIQQQIHHHHHH")
SHDR = struct.Struct("<IIQQQQIIQQ")
SYM = struct.Struct("<IBBHQQ")
RELA = struct.Struct("<QQq")
REL = struct.Struct("<QQ")
MAX_ELF = 128 * 1024 * 1024
# Relocation type -> number of bytes it can modify on x86-64.
# The currently pinned GNU toolchain normally emits PC32, PLT32 and
# REX_GOTPCRELX. Unknown relocations inside a function fail closed.
WIDTH = {
    1: 8, 2: 4, 3: 4, 4: 4, 9: 4, 10: 4, 11: 4,
    12: 2, 13: 2, 14: 1, 15: 1, 16: 8, 17: 8,
    18: 8, 19: 4, 20: 4, 21: 4, 22: 4, 23: 4,
    24: 8, 25: 8, 26: 4, 27: 8, 28: 8, 29: 8,
    30: 8, 31: 8, 32: 4, 33: 8, 41: 4, 42: 4,
}


def _require_slice(data, offset, length):
    if offset < 0 or length < 0 or offset + length > len(data):
        raise ValueError("original PC ELF section/symbol exceeds file bounds")
    return data[offset:offset + length]


def _string(table, index):
    if index < 0 or index >= len(table):
        raise ValueError("original PC ELF symbol name offset invalid")
    stop = table.find(b"\0", index)
    if stop < 0:
        raise ValueError("original PC ELF symbol name unterminated")
    return table[index:stop].decode("ascii", errors="strict")


def function_images(fd, names):
    """Return {symbol: (immutable raw bytes, frozenset reloc-byte offsets)}.

    Relocation offsets are relative to each function, not absolute address,
    so linker section concatenation can legitimately change st_value.
    """
    names = tuple(names)
    wanted = set(names)
    if len(wanted) != len(names):
        raise ValueError("original PC ELF witness duplicate required symbol")
    size = os.fstat(fd).st_size
    if not 64 <= size <= MAX_ELF:
        raise ValueError("original PC ELF witness size outside policy")
    data = os.pread(fd, size, 0)
    if len(data) != size:
        raise ValueError("original PC ELF witness short read")
    (ident, etype, machine, _, _, _, shoff, _, _, _, _, shentsize,
     shnum, _) = EHDR.unpack(_require_slice(data, 0, EHDR.size))
    if (ident[:4] != b"\x7fELF" or ident[4] != 2 or ident[5] != 1
            or etype != 1 or machine != 62 or shentsize != SHDR.size
            or not 0 < shnum < 4096):
        raise ValueError("original PC ELF witness requires x86-64 little-endian ET_REL")
    sections = [SHDR.unpack(_require_slice(data, shoff + i * shentsize, SHDR.size))
                for i in range(shnum)]
    # fields: name,type,flags,addr,offset,size,link,info,align,entsize
    found = {}
    for section in sections:
        if section[1] != 2:  # SHT_SYMTAB
            continue
        if (section[9] != SYM.size or section[5] % SYM.size
                or section[6] >= shnum):
            raise ValueError("original PC ELF witness malformed symbol table")
        strings_section = sections[section[6]]
        strings = _require_slice(data, strings_section[4], strings_section[5])
        table = _require_slice(data, section[4], section[5])
        for i in range(0, len(table), SYM.size):
            nameidx, info, _, index, start, length = SYM.unpack_from(table, i)
            if not nameidx:
                continue
            name = _string(strings, nameidx)
            if name not in wanted:
                continue
            if (name in found or info >> 4 != 1 or info & 15 != 2
                    or index >= shnum or not length):
                raise ValueError("original PC ELF witness function definition invalid")
            sec = sections[index]
            if sec[1] != 1 or sec[2] & 0x6 != 0x6 or sec[2] & 1:
                raise ValueError("original PC ELF witness function outside executable section")
            if start < sec[3] or length > sec[5] or start - sec[3] > sec[5] - length:
                raise ValueError("original PC ELF witness function bounds invalid")
            function = _require_slice(data, sec[4] + start - sec[3], length)
            found[name] = (function, index, start, length)
    if set(found) != wanted:
        raise ValueError("original PC ELF witness missing mandatory source function")
    masks = {name: set() for name in wanted}
    for section in sections:
        if section[1] not in (4, 9):  # SHT_RELA / SHT_REL
            continue
        relfmt = RELA if section[1] == 4 else REL
        if section[9] != relfmt.size or section[5] % relfmt.size:
            raise ValueError("original PC ELF witness malformed relocation table")
        target = section[7]  # sh_info: section affected by relocations
        relevant = {name: row for name, row in found.items() if row[1] == target}
        if not relevant:
            continue
        entries = _require_slice(data, section[4], section[5])
        for i in range(0, len(entries), relfmt.size):
            offset, info = relfmt.unpack_from(entries, i)[:2]
            kind = info & 0xffffffff
            if kind == 0:  # R_X86_64_NONE, writes no bytes
                continue
            # A relocation cannot refer beyond the executable section that
            # owns our mandatory functions. Otherwise it could evade
            # function-local validation merely by moving its r_offset.
            if offset >= sections[target][5]:
                raise ValueError("original PC ELF witness out-of-section relocation")
            for name, (_, _, start, length) in relevant.items():
                if start <= offset < start + length:
                    width = WIDTH.get(kind)
                    if width is None or offset + width > start + length:
                        raise ValueError("original PC ELF witness unsupported/out-of-function relocation")
                    affected = set(range(offset - start, offset - start + width))
                    if masks[name] & affected:
                        raise ValueError("original PC ELF witness overlapping relocations")
                    masks[name].update(affected)
    return {name: (found[name][0], frozenset(masks[name])) for name in names}


def compare_function_images(source, linked):
    """Compare all non-relocation bytes and report an integrity-only digest."""
    if set(source) != set(linked) or not source:
        raise ValueError("original PC ELF witness input/output symbols mismatch")
    total = skipped = 0
    records = []
    for name in sorted(source):
        a, reloc_a = source[name]
        b, reloc_b = linked[name]
        if len(a) != len(b) or not a:
            raise ValueError("original PC ELF witness function length differs")
        # GNU ld -r may rewrite a relocation's value and symtab index,
        # but must not introduce new relocation *byte locations* inside
        # mandatory code. A union here lets an output-only relocation hide
        # arbitrary instruction corruption by expanding the ignored region.
        if reloc_a != reloc_b:
            raise ValueError("original PC ELF witness relocated byte positions differ")
        ignored = reloc_a
        if (any(not isinstance(pos, int) or pos < 0 or pos >= len(a)
                for pos in ignored)):
            raise ValueError("original PC ELF witness invalid relocated byte position")
        if len(ignored) >= len(a):
            raise ValueError("original PC ELF witness no unrelocated function code")
        normalized = bytearray(a)
        for pos in ignored:
            normalized[pos] = 0
        if any(a[i] != b[i] for i in range(len(a)) if i not in ignored):
            raise ValueError("original PC ELF witness unrelocated instruction bytes changed")
        total += len(a)
        skipped += len(ignored)
        records.append((name, hashlib.sha256(normalized).hexdigest()))
    digest = hashlib.sha256(json.dumps(records, separators=(",", ":")).encode()).hexdigest()
    return {"source_link_function_code_bytes_checked": total,
            "source_link_relocation_bytes_excluded": skipped,
            "source_link_nonrelocated_function_code_sha256": digest}
