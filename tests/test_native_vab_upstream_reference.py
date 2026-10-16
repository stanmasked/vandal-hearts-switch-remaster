#!/usr/bin/env python3
"""Execute the pinned upstream SeqPickTone C function against native VAB.

The original GPL-2.0 source is downloaded only in CI and never vendored or
published with game assets. This harness extracts the upstream function
verbatim and compiles it with minimal compatible metadata-only Vab/Tone
declarations. This is an algorithm oracle, not the whole PC-port runtime.
"""
from __future__ import annotations

import argparse
import ctypes
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_resolve_vab_note import make_sparse_bank
from test_native_vab_python_reference import SeqTone

UPSTREAM_COMMIT = "17427153fd3560fcb9adf3a8f484d9ff7fc530e9"
FUNCTION_SIGNATURE = "static int SeqPickTone(const Vab *vab, int reqProg, int note, int *outProg)"
LAYOUTS = (
    ("baseline", ((40, 60), (40, 70), (80, 100), (40, 50))),
    ("all_overlap", ((0, 127), (0, 127), (0, 127), (0, 127))),
    ("single_notes", ((0, 0), (127, 127), (64, 64), (65, 65))),
    ("nearest_ties", ((10, 15), (30, 35), (50, 55), (70, 75))),
    ("cross_program", ((0, 30), (80, 100), (40, 60), (20, 45))),
    ("outer_edges", ((0, 0), (0, 0), (127, 127), (127, 127))),
)
TONE_LOCATIONS = ((0, 0, 1, 2080),
                  (0, 1, 2, 2080 + 32),
                  (7, 0, 3, 2080 + 512),
                  (10, 0, 4, 2080 + 1024))
REQUESTED_PROGRAMS = (0, 7, 10, 99, 127)


def extract_function(source: str) -> str:
    """Extract exact upstream C bytes, including internal comments."""
    start = source.find(FUNCTION_SIGNATURE + " {")
    if start < 0 or source.count(FUNCTION_SIGNATURE + " {") != 1:
        raise ValueError("pinned upstream SeqPickTone signature not found uniquely")
    brace = source.index("{", start)
    depth = 0
    for pos in range(brace, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                result = source[start:pos + 1]
                if ("TONES_PER_PROGRAM" not in result or
                        "bestD" not in result or "outProg" not in result):
                    raise ValueError("unexpected upstream SeqPickTone body")
                return result
    raise ValueError("unterminated upstream SeqPickTone")


def build_oracle(upstream_path: Path, out_path: Path) -> None:
    source = upstream_path.read_text(encoding="utf-8")
    original = extract_function(source)
    # Only the fields actually read by SeqPickTone are represented here.
    # The function body itself is not copied, translated, or edited.
    shim = """
#include <stdint.h>
#define TONES_PER_PROGRAM 16
#define MAX_PROGRAMS 128
typedef struct { short vag; unsigned char min, max; } Tone;
typedef struct { short numPrograms; Tone tones[MAX_PROGRAMS][TONES_PER_PROGRAM]; } Vab;
"""
    bridge = """
int upstream_pick(int requested, int note, const unsigned char *vags,
                  const unsigned char *lows, const unsigned char *highs,
                  int *program_out) {
    Vab bank = {0};
    bank.numPrograms = 11; /* highest populated program (10) + 1 */
    for (int p = 0; p < MAX_PROGRAMS; ++p) {
        for (int t = 0; t < TONES_PER_PROGRAM; ++t) {
            int i = p * TONES_PER_PROGRAM + t;
            bank.tones[p][t].vag = vags[i];
            bank.tones[p][t].min = lows[i];
            bank.tones[p][t].max = highs[i];
        }
    }
    return SeqPickTone(&bank, requested, note, program_out);
}
"""
    with tempfile.TemporaryDirectory(prefix="vh-upstream-c-") as folder:
        path = Path(folder) / "seq_pick_tone.c"
        path.write_text(shim + original + "\n" + bridge, encoding="utf-8")
        subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-O2", "-fPIC", "-shared", str(path), "-o", str(out_path)],
            check=True, capture_output=True, text=True,
        )


def check_upstream_inactive_and_gap_slots(pick) -> int:
    """Pin upstream selection of usable records invisible to nTone-only parsers."""
    vags = (ctypes.c_uint8 * (128 * 16))()
    lows = (ctypes.c_uint8 * (128 * 16))()
    highs = (ctypes.c_uint8 * (128 * 16))()
    # p0 has only two declared tones, but upstream scans all 16.
    for program, tone, vag, low, high in (
        (0, 0, 1, 40, 60), (0, 1, 2, 40, 70),
        (0, 2, 2, 115, 120),  # inactive nTone slot
        (1, 0, 3, 80, 100),   # empty p1 inherits p7 packed block
        (7, 0, 3, 80, 100),
        (8, 0, 4, 40, 50),    # empty p8 inherits p10 packed block
        (10, 0, 4, 40, 50),
    ):
        i = program * 16 + tone
        vags[i], lows[i], highs[i] = vag, low, high

    for program, note, expected_program, expected_tone in (
        (0, 117, 0, 2),
        (1, 90, 1, 0),
        (8, 45, 8, 0),
    ):
        selected = ctypes.c_int(-1)
        tone = pick(program, note, vags, lows, highs, ctypes.byref(selected))
        if (selected.value, tone) != (expected_program, expected_tone):
            raise AssertionError(
                f"PC-port inactive/gap slot: {program}/{note} -> "
                f"{selected.value}/{tone}; expected "
                f"{expected_program}/{expected_tone}"
            )
    return 3


def run(source_path: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="vh-upstream-exec-") as folder:
        root = Path(folder)
        oracle_so = root / "upstream.so"
        native_so = root / "native.so"
        build_oracle(source_path, oracle_so)
        subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
             "-fPIC", "-shared", "-Isource", "source/vh_native_vab.c",
             "source/vh_spu_adpcm.c", "-lm", "-o", str(native_so)],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        oracle = ctypes.CDLL(str(oracle_so))
        pick = oracle.upstream_pick
        ptr8 = ctypes.POINTER(ctypes.c_uint8)
        pick.argtypes = [
            ctypes.c_int, ctypes.c_int, ptr8, ptr8, ptr8,
            ctypes.POINTER(ctypes.c_int),
        ]
        pick.restype = ctypes.c_int

        shadow_cases = check_upstream_inactive_and_gap_slots(pick)
        print(f"Pinned upstream inactive/gap tone behaviour: PASS {shadow_cases} cases")

        native = ctypes.CDLL(str(native_so))
        load = native.vh_native_vab_load
        load.argtypes = [
            ctypes.c_void_p, ptr8, ctypes.c_size_t,
            ptr8, ctypes.c_size_t, ctypes.POINTER(ctypes.c_int16),
            ctypes.c_size_t,
        ]
        load.restype = ctypes.c_int
        resolve = native.vh_native_vab_resolve
        resolve.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
            ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(SeqTone),
        ]
        resolve.restype = ctypes.c_int

        vh_base, vb = make_sparse_bank()
        sample_vb = (ctypes.c_uint8 * len(vb)).from_buffer_copy(vb)
        count = 0
        for label, ranges in LAYOUTS:
            vh = bytearray(vh_base)
            vags = (ctypes.c_uint8 * (128 * 16))()
            lows = (ctypes.c_uint8 * (128 * 16))()
            highs = (ctypes.c_uint8 * (128 * 16))()
            for (program, slot, vag, offset), (low, high) in zip(
                    TONE_LOCATIONS, ranges):
                vh[offset + 6] = low
                vh[offset + 7] = high
                i = program * 16 + slot
                vags[i], lows[i], highs[i] = vag, low, high
            source_vh = (ctypes.c_uint8 * len(vh)).from_buffer_copy(vh)
            # These are opaque native structs; space is deliberately ample.
            bank = (ctypes.c_longdouble * 16384)()
            pcm = (ctypes.c_int16 * 112)()
            result = load(
                bank, source_vh, len(vh), sample_vb, len(vb),
                pcm, len(pcm),
            )
            if result != 0:
                raise AssertionError(f"{label}: native bank import failed ({result})")
            pcm_base = ctypes.addressof(pcm)
            for program in REQUESTED_PROGRAMS:
                for note in range(128):
                    chosen_program = ctypes.c_int(-1)
                    slot = pick(
                        program, note, vags, lows, highs,
                        ctypes.byref(chosen_program),
                    )
                    if slot < 0 or chosen_program.value < 0:
                        raise AssertionError(
                            f"{label} program={program} note={note}: upstream returned no tone"
                        )
                    mapping = {
                        (p, t): vag for p, t, vag, _ in TONE_LOCATIONS
                    }
                    chosen_vag = mapping.get((chosen_program.value, slot))
                    if chosen_vag is None:
                        raise AssertionError(
                            f"{label} program={program} note={note}: "
                            f"unexpected upstream program/tone "
                            f"{chosen_program.value}/{slot}"
                        )
                    tone = SeqTone()
                    native_rc = resolve(
                        bank, program, note, 127, 127, 64,
                        ctypes.byref(tone),
                    )
                    expected_addr = (
                        pcm_base + (chosen_vag - 1) * 28
                        * ctypes.sizeof(ctypes.c_int16)
                    )
                    actual_addr = ctypes.cast(
                        tone.pcm, ctypes.c_void_p
                    ).value
                    if native_rc or actual_addr != expected_addr:
                        raise AssertionError(
                            f"{label} program={program} note={note}: "
                            f"upstream chose {chosen_program.value}/{slot}/"
                            f"VAG{chosen_vag}; native returned rc={native_rc}, "
                            f"PCM address={actual_addr}, expected={expected_addr}"
                        )
                    count += 1
        expected = len(LAYOUTS) * len(REQUESTED_PROGRAMS) * 128
        if count != expected:
            raise AssertionError(f"compared {count} cases, expected {expected}")
        print(
            f"Executed pinned PC-port SeqPickTone ({UPSTREAM_COMMIT[:12]}) "
            f"vs native C resolver: PASS {count} cases across "
            f"{len(LAYOUTS)} synthetic banks"
        )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "upstream_libsnd", type=Path,
        help="local libsnd.c downloaded from the pinned upstream commit",
    )
    args = parser.parse_args()
    return run(args.upstream_libsnd)


if __name__ == "__main__":
    raise SystemExit(main())
