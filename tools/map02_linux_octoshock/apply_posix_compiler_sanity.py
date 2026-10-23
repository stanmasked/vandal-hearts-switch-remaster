#!/usr/bin/env python3
"""Apply a narrow GCC/POSIX compatibility shim to a disposable BizHawk source checkout.

This is deliberately not applied to the project's tracked source or to a release
archive. Anchors are exact and must each occur once so upstream drift fails closed.
"""
from pathlib import Path
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one exact upstream anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply_posix_compiler_sanity.py PATH_TO_EMUWARE_H")

    path = Path(sys.argv[1])
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")

    markers = (
        "#include <cstddef>",
        "#define SIZEOF_PTRDIFF_T sizeof(ptrdiff_t)",
        "#define NO_CLONE __attribute__((noclone))",
    )
    if any(marker in text for marker in markers):
        raise SystemExit("refusing partial or repeated POSIX compiler-sanity shim")

    if '#define EW_EXPORT extern "C" __attribute__((visibility("default")))' not in text:
        raise SystemExit("POSIX export shim must be applied before compiler-sanity shim")

    text = replace_once(
        text,
        "#include <cstdlib>\n",
        "#include <cstdlib>\n#include <cstddef>\n#include <sys/types.h>\n",
        "standard-header insertion",
    )

    size_macros = (
        "#define SIZEOF_CHAR sizeof(char)\n"
        "#define SIZEOF_SHORT sizeof(short)\n"
        "#define SIZEOF_INT sizeof(int)\n"
        "#define SIZEOF_LONG sizeof(long)\n"
        "#define SIZEOF_LONG_LONG sizeof(long long)\n"
        "#define SIZEOF_OFF_T sizeof(off_t)\n"
        "#define SIZEOF_PTRDIFF_T sizeof(ptrdiff_t)\n"
        "#define SIZEOF_SIZE_T sizeof(size_t)\n"
        "#define SIZEOF_VOID_P sizeof(void*)\n"
    )
    text = replace_once(
        text,
        "#else\ntypedef __int64_t s64;",
        "#else\n" + size_macros + "typedef __int64_t s64;",
        "POSIX type-size definitions",
    )

    msvc_anchor = (
        "#if defined(_MSC_VER)\n"
        "\t#define strncasecmp _strnicmp\n"
        "\t#define NO_CLONE\n"
        "#endif\n\n"
        "#if defined(_MSC_VER) && _MSC_VER < 1900"
    )
    gcc_attributes = (
        "#if defined(_MSC_VER)\n"
        "\t#define strncasecmp _strnicmp\n"
        "\t#define NO_CLONE\n"
        "#endif\n"
        "#if defined(__GNUC__) && !defined(_MSC_VER)\n"
        "#undef NO_INLINE\n"
        "#define NO_INLINE __attribute__((noinline))\n"
        "#define NO_CLONE __attribute__((noclone))\n"
        "#endif\n\n"
        "#if defined(_MSC_VER) && _MSC_VER < 1900"
    )
    text = replace_once(text, msvc_anchor, gcc_attributes, "GCC no-inline/no-clone definitions")

    required = (
        "#include <cstddef>",
        "#include <sys/types.h>",
        "#define SIZEOF_OFF_T sizeof(off_t)",
        "#define SIZEOF_PTRDIFF_T sizeof(ptrdiff_t)",
        "#define NO_INLINE __attribute__((noinline))",
        "#define NO_CLONE __attribute__((noclone))",
    )
    if not all(text.count(marker) == 1 for marker in required):
        raise SystemExit("postcondition failed: shim definitions are missing or duplicated")

    # Normalize line endings only in the disposable upstream checkout, avoiding
    # fragile patch matching against upstream's platform-specific line endings.
    path.write_text(text, encoding="utf-8", newline="\n")
    print("VH_MAP02_POSIX_COMPILER_SANITY_SHIM_PASS exact_anchors=3 upstream_checkout_only=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
