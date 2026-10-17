#!/usr/bin/env python3
"""Execute the *original pinned CdRead C function* on an asset-free raw BIN.

Extract only this original function from a separately pinned libcd.c; the C
harness stubs unrelated SDL, XA, boot and audiovisual dependencies. The
actual instrumented original CdRead sector loop and transfer remain intact.
The game core LoadCdFile/ContinueLoadingCdFile is NOT executed in this
isolated CD unit test (its pinned source hooks are verified separately).
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zlib

from tools.instrument_map02_cd_read import instrument_libcd, instrument_core_cd
from tools.check_map02_owned_disc_extent import _bcd, SECTOR_RAW

LBA = 0x1bcc
SECTORS = 12

HEADER = r"""
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <assert.h>
#include "map02_cd_read_probe.h"
typedef unsigned int Uint32;
#define SECTOR_RAW_SIZE 2352
#define SECTOR_DATA_OFFSET 24
#define SECTOR_DATA_SIZE 2048
#define MOTOR_STARTUP_PENALTY_MS 1000.0
#define SECTORS_PER_SEC_1X 75.0
#define CdlModeSpeed 0x80
static unsigned char s_mode = 0;
static FILE *s_disc;
static int s_headLBA = 0, s_targetLBA = 0;
static int s_motorStarted = 0, s_lastReadResult = -1;
static Uint32 s_pendingReadUntilMs = 0;
static double s_pendingPerSectorMs = 0;
static int s_testPatch = 0;
static Uint32 SDL_GetTicks(void) { return 1; }
static int BootGraceActive(void) { return 1; }
static double CalcSeekTimeMs(int a, int b) { (void)a; (void)b; return 1.0; }
static void CdFatalCorrupt(int lba, const char *s) {
    fprintf(stderr, "corrupt synthetic sector %d: %s", lba, s);
    abort();
}
static void CdCheckRawSector(const unsigned char *raw, int lba) {
    int sector = lba + 150;
    unsigned char sync[12] = {0,255,255,255,255,255,255,255,255,255,255,0};
    if (memcmp(raw, sync, 12)) abort();
    if (raw[12] != (unsigned char)(((sector/4500/10)<<4)|(sector/4500%10)) ||
        raw[13] != (unsigned char)((((sector/75%60)/10)<<4)|((sector/75%60)%10)) ||
        raw[14] != (unsigned char)((((sector%75)/10)<<4)|((sector%75)%10)))
        abort();
}
static void PC_LangPatchRead(int lba, int sectors, unsigned char *out) {
    (void)lba; (void)sectors;
    if (s_testPatch) out[0] ^= 1;
}
"""

FOOTER = r"""
int main(int argc, char **argv) {
    unsigned int buffer[12u*2048u/4u];
    char result[512];
    int success;
    if (argc != 3) return 2;
    s_disc = fopen(argv[1], "rb");
    if (!s_disc) return 3;
    s_targetLBA = 0x1bcc;
    vh_map02_cd_loader_claim(42, 42, 0x1bcc, 12);
    if (!strcmp(argv[2], "tamper")) s_testPatch = 1;
    success = CdRead(12, buffer, 0);
    if (!success) return 4;
    if (strcmp(argv[2], "no-completion"))
        vh_map02_cd_loader_complete(42, 42, 99);
    if (!strcmp(argv[2], "duplicate"))
        vh_map02_cd_loader_complete(42, 42, 99);
    int written = vh_map02_cd_probe_format_jsonl(result, sizeof result);
    if (!strcmp(argv[2], "ok")) {
        if (written <= 0) return 5;
        fwrite(result, 1, (size_t)written, stdout);
    } else {
        if (written || (!vh_map02_cd_probe_failed() &&
            strcmp(argv[2], "no-completion"))) return 6;
    }
    return fclose(s_disc) != 0 ? 7 : 0;
}
"""


def check_original_cd_runtime(upstream, compiler="cc"):
    upstream = Path(upstream)
    libcd = (upstream / "platform/pc/src/libcd.c").read_text()
    core = (upstream / "src/core/cd.c").read_text()
    # Both generators must reject source drift, including the original
    # loader transition (even though this isolated test cannot run game core).
    instrument_core_cd(core)
    instrumented = instrument_libcd(libcd)
    before = instrumented.index("int CdRead(int sectors, unsigned int *buf, int mode) {")
    after = instrumented.index("\nint CdReadSync(", before)
    original_function = instrumented[before:after]
    if "vh_map02_cd_read_sector" not in original_function:
        raise ValueError("original CdRead source hooks absent")
    with tempfile.TemporaryDirectory(prefix="vh-map02-original-cd-") as tmp:
        root = Path(tmp)
        image = root / "synthetic.bin"
        with image.open("wb") as f:
            f.truncate((LBA + SECTORS) * SECTOR_RAW)
        expected = bytearray()
        with image.open("r+b") as f:
            for index in range(SECTORS):
                lba = LBA + index
                payload = bytes(((index * 17 + j) & 255)
                                for j in range(2048))
                expected.extend(payload)
                raw = bytearray(SECTOR_RAW)
                raw[:12] = b"\x00" + b"\xff" * 10 + b"\x00"
                frame = lba + 150
                raw[12:15] = bytes(
                    [_bcd(frame // 4500), _bcd(frame // 75 % 60),
                     _bcd(frame % 75)])
                raw[24:2072] = payload
                f.seek(lba * SECTOR_RAW)
                f.write(raw)
        harness = root / "cdread.c"
        harness.write_text(HEADER + original_function + "\n" + FOOTER)
        exe = root / "cdread"
        tools_dir = Path(__file__).resolve().parent
        build = subprocess.run(
            [compiler, "-std=gnu99", "-Wall", "-Wextra", "-Werror",
             "-DVH_MAP02_CD_READ_PROBE", "-Wno-unused-parameter",
             "-I", str(tools_dir), str(harness),
             str(tools_dir / "map02_cd_read_probe.c"),
             str(tools_dir / "map02_capture_session.c"),
             "-o", str(exe)],
            text=True, capture_output=True, timeout=90)
        if build.returncode:
            raise ValueError("original CdRead isolated native build: "
                             + build.stderr[-4000:])
        seen = None
        for mode in ("ok", "tamper", "no-completion", "duplicate"):
            proc = subprocess.run([str(exe), str(image), mode],
                                  capture_output=True, text=True, timeout=30)
            if proc.returncode:
                raise ValueError("original CdRead " + mode +
                                 " exit " + str(proc.returncode) +
                                 ": " + proc.stderr[-2000:])
            if mode == "ok":
                seen = json.loads(proc.stdout)
                if (seen["lba"] != LBA or seen["sectors"] != SECTORS or
                    seen["raw_user_crc32"] != f"{zlib.crc32(expected):08x}" or
                    seen["returned_user_crc32"] != seen["raw_user_crc32"] or
                    seen["loader_completed"] is not True):
                    raise ValueError("original CdRead synthetic CRC disagrees")
            elif proc.stdout.strip():
                raise ValueError("incomplete or modified original CD read was accepted")
    return {
        "original_pinned_cdread_executed": True,
        "original_game_loader_ran": False,
        "map02_lba": LBA,
        "sectors": SECTORS,
        "transfer_crc32_checked": True,
        "incorrect_transfer_rejected": True,
        "missing_loader_completion_rejected": True,
        "original_map02_gameplay_proven": False,
        "raw_game_data_emitted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("original_pc_checkout", type=Path)
    args = p.parse_args()
    try:
        print(json.dumps(check_original_cd_runtime(args.original_pc_checkout),
                         sort_keys=True, indent=2))
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
