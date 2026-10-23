"""Regression tests for the isolated POSIX Octoshock header shim."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHIM = PROJECT_ROOT / "tools" / "map02_linux_octoshock" / "apply_posix_compiler_sanity.py"

# Minimal fixture preserving the relevant lines from the pinned upstream header,
# including its commented-out NO_INLINE example and platform-specific PTRDIFF_T.
UPSTREAM_HEADER = """#pragma once

#include <inttypes.h>
#include <stdint.h>
#include <cstdlib>

#ifdef _MSC_VER
#define SIZEOF_CHAR sizeof(char)
#define SIZEOF_SHORT sizeof(short)
#define SIZEOF_INT sizeof(int)
#define SIZEOF_LONG sizeof(long)
#define SIZEOF_LONG_LONG sizeof(long long)
#define SIZEOF_OFF_T sizeof(off_t)
#define SIZEOF_PTRDIFF_T sizeof(void*)
#define SIZEOF_SIZE_T sizeof(size_t)
#define SIZEOF_VOID_P sizeof(void*)
typedef __int64 s64;
#else
typedef __int64_t s64;
#endif

//#define NO_INLINE __attribute__((noinline))
#define NO_INLINE

#if defined(_MSC_VER)
\t#define strncasecmp _strnicmp
\t#define NO_CLONE
#endif

#if defined(_MSC_VER) && _MSC_VER < 1900
  #define snprintf _snprintf
#endif

#define EW_EXPORT extern "C" __attribute__((visibility("default")))
"""


class PosixCompilerSanityShimTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.header = Path(tmp.name) / "emuware.h"
        self.header.write_text(UPSTREAM_HEADER, encoding="utf-8")

    def run_shim(self):
        return subprocess.run(
            [sys.executable, str(SHIM), str(self.header)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_applies_to_upstream_shape_and_ignores_commented_macro_example(self):
        result = self.run_shim()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("VH_MAP02_POSIX_COMPILER_SANITY_SHIM_PASS", result.stdout)
        text = self.header.read_text(encoding="utf-8")
        active = [line.strip() for line in text.splitlines()]
        self.assertEqual(active.count("#define SIZEOF_PTRDIFF_T sizeof(void*)"), 1)
        self.assertEqual(active.count("#define SIZEOF_PTRDIFF_T sizeof(ptrdiff_t)"), 1)
        self.assertEqual(active.count("#define NO_INLINE __attribute__((noinline))"), 1)
        self.assertEqual(active.count("#define NO_CLONE __attribute__((noclone))"), 1)
        self.assertIn("//#define NO_INLINE __attribute__((noinline))", text)

    def test_refuses_unexpected_upstream_anchor(self):
        self.header.write_text(UPSTREAM_HEADER.replace(
            '#include <cstdlib>', '#include <stdlib.h>'
        ), encoding="utf-8")
        result = self.run_shim()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("standard-header insertion", result.stderr)
        self.assertNotIn("#include <cstddef>", self.header.read_text(encoding="utf-8"))

    def test_refuses_partial_or_repeated_shim(self):
        self.header.write_text(
            UPSTREAM_HEADER + "\n#include <cstddef>\n", encoding="utf-8"
        )
        result = self.run_shim()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing partial or repeated", result.stderr)


if __name__ == "__main__":
    unittest.main()
