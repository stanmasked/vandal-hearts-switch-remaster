#!/usr/bin/env python3
"""Check the REAL pinned upstream presentation tail after C preprocessing.

Usage: python3 tests/check_pc_gpu_present_exclusive_preprocessed.py patched.c
The selected tail is preprocessed in isolation to avoid unrelated desktop
include dependencies. This is not a full upstream Switch engine build.
"""
import pathlib
import subprocess
import sys

START = "#if defined(VH_SWITCH_EXCLUSIVE_PRESENT)"
END = "#endif /* VH_SWITCH_EXCLUSIVE_PRESENT */"

def select_tail(source):
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError("missing or duplicate exclusive presentation delimiters")
    beginning = source.index(START)
    ending = source.index(END, beginning) + len(END)
    return source[beginning:ending] + "\n"

def preprocess(tail, defines):
    return subprocess.run(
        ["cc", "-E", "-P", "-x", "c", *defines, "-"],
        input=tail, text=True, capture_output=True, check=True,
    ).stdout

def verify(source):
    tail = select_tail(source)
    for defines, is_switch, is_apple in [
        ([], False, False),
        (["-D__APPLE__"], False, True),
        (["-DVH_SWITCH_EXCLUSIVE_PRESENT"], True, False),
        (["-DVH_SWITCH_EXCLUSIVE_PRESENT", "-D__APPLE__"], True, True),
    ]:
        active = preprocess(tail, defines)
        # All direct desktop swaps and draws must be removed in Switch builds.
        expected = {
            "VH_ObserveCompletedRGB24(s_rgbaScratch": is_switch,
            "glDrawPixels(": not is_switch and not is_apple,
            "SDL_GL_SwapWindow(": not is_switch and not is_apple,
            "SDL_RenderPresent(": not is_switch and is_apple,
        }
        for symbol, want in expected.items():
            present = symbol in active
            if present != want:
                raise AssertionError(
                    f"{defines}: {symbol} present={present}, expected={want}"
                )
        if is_switch and active.count("VH_ObserveCompletedRGB24(s_rgbaScratch") != 1:
            raise AssertionError("Switch path must call frame observer once")
        print(f"PASS: defines={defines or ['desktop']} exclusive={is_switch}")
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_pc_gpu_present_exclusive_preprocessed.py patched.c")
    verify(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
