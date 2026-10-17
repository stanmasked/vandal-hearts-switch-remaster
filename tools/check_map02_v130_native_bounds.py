#!/usr/bin/env python3
"""Compile original v129 generated C table declarations and reject OOB regressions.

The compiler and UBSan see the *actual* table declarations extracted from
the native emulator oracle, not a hand-written copy of their initializer data.
All files are temporary; no original game EXE, logs, pixels or hashes leave CI.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .apply_map02_v129_pcsx_rearmed import oracle_source
from .make_map02_v129_four_vblank_exe import build

SHAPES = {
    "vh129_boundary_targets": "[5][2]",
    "vh129_adjacent_histograms": "[5][5]",
    "expected_total_edges": "[5]",
    "return_gap": "[5]",
}

class Refused(ValueError):
    """Do not accept incomplete or inconsistent original native table C."""


def extract_declarations(native=None):
    if native is None:
        _,stops,_,_,wait_pc=build()
        native=oracle_source(stops,wait_pc)
    result={}
    for name,shape in SHAPES.items():
        matches=list(re.finditer(
            r"\bstatic\s+const\s+unsigned\s+"+re.escape(name)+
            r"(?P<dims>(?:\[\d+\])+)\s*=\s*\{.*?\};",
            native,re.DOTALL))
        if len(matches)!=1:
            raise Refused(f"expected one unambiguous original C table: {name}")
        if matches[0].group("dims")!=shape:
            raise Refused(f"original C table has wrong dimensions: {name}")
        result[name]=matches[0].group(0)
    if "vh129_boundary_rows_equal_five" not in native:
        raise Refused("original native compile-time boundary size guard absent")
    return result


C_CHECKS = r"""
#include <stdio.h>
#include <stddef.h>

/* Independent expectations authored from the five source-approved VBlank modes. */
static const unsigned expected_splits[5][2] = {
    {0u,4u}, {1u,3u}, {2u,2u}, {3u,1u}, {4u,0u}
};
static const unsigned expected_adjacent[5][5] = {
    {3u,0u,0u,0u,1u}, {2u,1u,0u,1u,0u},
    {2u,0u,2u,0u,0u}, {2u,1u,0u,1u,0u},
    {3u,0u,0u,0u,1u}
};

_Static_assert(sizeof(vh129_boundary_targets) /
               sizeof(vh129_boundary_targets[0]) == 5u,
               "five native boundary rows mandatory");
_Static_assert(sizeof(vh129_boundary_targets[0]) /
               sizeof(vh129_boundary_targets[0][0]) == 2u,
               "two native gap boundaries mandatory");
_Static_assert(sizeof(vh129_adjacent_histograms) /
               sizeof(vh129_adjacent_histograms[0]) == 5u,
               "five native histogram rows mandatory");
_Static_assert(sizeof(vh129_adjacent_histograms[0]) /
               sizeof(vh129_adjacent_histograms[0][0]) == 5u,
               "five sampled gap classes mandatory");
_Static_assert(sizeof(expected_total_edges) /
               sizeof(expected_total_edges[0]) == 5u,
               "five real edge totals mandatory");
_Static_assert(sizeof(return_gap) /
               sizeof(return_gap[0]) == 5u,
               "five four-back return classifications mandatory");

int main(void) {
    unsigned mode,bin;
    for(mode=0u;mode<5u;mode++) {
        unsigned a=vh129_boundary_targets[mode][0];
        unsigned b=vh129_boundary_targets[mode][1];
        if(a!=expected_splits[mode][0] || b!=expected_splits[mode][1] ||
           a+b!=4u) return 11;
        if(expected_total_edges[mode]!=4u || return_gap[mode]!=4u)
            return 12;
        for(bin=0u;bin<5u;bin++) {
            if(vh129_adjacent_histograms[mode][bin]!=
               expected_adjacent[mode][bin]) return 13;
        }
    }
    puts("VH130_NATIVE_VBLANK_TABLE_BOUNDS_PASS modes=5 "
         "edges=4 max_gap=4 negative_controls=7");
    return 0;
}
"""


def make_c(declarations):
    if set(declarations)!=set(SHAPES):
        raise Refused("native table set incomplete")
    return "\n".join(declarations[name] for name in SHAPES)+"\n"+C_CHECKS


def replace_exact(source,old,new):
    if source.count(old)!=1:
        raise Refused("native C mutation target missing or ambiguous")
    return source.replace(old,new)


def negative_cases(good):
    """Three compile-time bounds failures, four independent runtime failures."""
    cases={}
    cases["four_boundary_rows"]=(
        replace_exact(good,"vh129_boundary_targets[5][2]",
                           "vh129_boundary_targets[4][2]"),"compile")
    cases["four_histogram_rows"]=(
        replace_exact(good,"vh129_adjacent_histograms[5][5]",
                           "vh129_adjacent_histograms[4][5]"),"compile")
    cases["four_return_rows"]=(
        replace_exact(good,"return_gap[5]","return_gap[4]"),"compile")
    cases["wrong_fifth_boundary"]=(
        replace_exact(good,"{4u,0u}", "{3u,0u}"),"runtime")
    cases["wrong_histogram"]=(
        replace_exact(good,"{3u,0u,0u,0u,1u}",
                           "{2u,0u,0u,0u,1u}"),"runtime")
    cases["wrong_expected_total"]=(
        replace_exact(good,
           "expected_total_edges[5]={4u,4u,4u,4u,4u}",
           "expected_total_edges[5]={4u,4u,4u,4u,3u}"),"runtime")
    cases["wrong_four_back_return"]=(
        replace_exact(good,
           "return_gap[5]={4u,4u,4u,4u,4u}",
           "return_gap[5]={4u,4u,4u,4u,3u}"),"runtime")
    if len(cases)!=7:
        raise Refused("seven independent negative native controls required")
    return cases


def compile_and_run(cc,source,temp_dir,name):
    cfile=temp_dir/(name+".c")
    binary=temp_dir/(name+".bin")
    cfile.write_text(source,encoding="utf-8")
    result=subprocess.run(
        [cc,"-std=c11","-O1","-g","-Wall","-Wextra","-Wpedantic",
         "-Werror","-fno-omit-frame-pointer",
         "-fsanitize=undefined,bounds",str(cfile),"-o",str(binary)],
        text=True,capture_output=True,timeout=45,check=False)
    if result.returncode:
        return False,None
    execution=subprocess.run([str(binary)],text=True,capture_output=True,
                             timeout=15,check=False,
                             env={**os.environ,
                                  "UBSAN_OPTIONS":"halt_on_error=1:print_stacktrace=0"})
    return True,execution


def verify(cc):
    if cc not in ("gcc","clang") or shutil.which(cc) is None:
        raise Refused("explicit available GCC or Clang compiler required")
    good=make_c(extract_declarations())
    with tempfile.TemporaryDirectory(prefix="vh130-native-bounds-") as directory:
        root=Path(directory)
        built,execution=compile_and_run(cc,good,root,"control")
        if not built or execution is None or execution.returncode or (
            execution.stdout.strip()!=
            "VH130_NATIVE_VBLANK_TABLE_BOUNDS_PASS modes=5 "
            "edges=4 max_gap=4 negative_controls=7"
        ):
            raise Refused("unmodified original five-mode native C refused")
        results={}
        for name,(bad,expect) in negative_cases(good).items():
            compiled,result=compile_and_run(cc,bad,root,name)
            if expect=="compile":
                if compiled:
                    raise Refused(f"undersized native C array compiled: {name}")
            elif not compiled or result is None or result.returncode==0:
                raise Refused(f"corrupted native C profile passed: {name}")
            results[name]=expect
    return results


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--cc",choices=("gcc","clang"),required=True)
    args=parser.parse_args()
    try:
        result=verify(args.cc)
    except (Refused,OSError,subprocess.TimeoutExpired) as exc:
        parser.exit(2,f"VH130_NATIVE_BOUNDS_REFUSED {exc}\n")
    print(f"VH130_NATIVE_BOUNDS_VERIFIED compiler={args.cc} "
          f"positive=1 compile_refusals=3 runtime_refusals=4")


if __name__=="__main__":
    main()
