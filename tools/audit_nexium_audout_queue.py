#!/usr/bin/env python3
"""Strict stage-269 guest SD audout telemetry audit; no audio-output claims."""
import argparse
import csv
import hashlib
import io
import json
import os
import stat
from pathlib import Path

HEADER = [
    "scope", "second", "attempts", "returns", "failures", "max_call_us",
    "queue_ok", "queue_errors", "queue_min", "queue_max",
    "overwritten_windows", "clock_errors",
]
NUMERIC = HEADER[1:]

MAX_CSV_BYTES = 1024 * 1024

def stable_guest_bytes(path: Path) -> bytes:
    """Refuse symlinks, hardlinks, changed inode/size and oversized evidence."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_size <= 0 or before.st_size > MAX_CSV_BYTES):
            raise ValueError("unsafe guest evidence file")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(MAX_CSV_BYTES + 1)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    current = path.lstat()
    identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns,
                           st.st_ctime_ns)
    if len(raw) != before.st_size or len(raw) > MAX_CSV_BYTES or (
        identity(before) != identity(after)
        or identity(before) != identity(current)
    ):
        raise ValueError("guest evidence changed during read")
    return raw

def bind_original_sd(source: Path, locations: Path, sd_root: Path):
    """Check the actual isolated NeXium SD file, not just its copied CSV."""
    if sd_root.is_symlink():
        raise ValueError("refuse symlinked guest SD root")
    sd_dir = sd_root / "sdmc" / "switch" / "vandal-hearts-remake"
    if not sd_dir.is_dir() or sd_dir.is_symlink():
        raise ValueError("missing or symlinked guest SD directory")
    originals = sorted(sd_dir.glob("audio-audout-queue-*.csv"))
    if len(originals) != 1:
        raise ValueError("expected exactly one original guest audout CSV")
    original = originals[0]
    location_lines = locations.read_text(encoding="utf-8").splitlines()
    if len(location_lines) != 1 or Path(location_lines[0]) != original:
        raise ValueError("capture manifest does not identify original SD CSV")
    if original.is_symlink() or source.is_symlink():
        raise ValueError("symlinked SD evidence forbidden")
    if not source.is_file() or original.resolve() == source.resolve():
        raise ValueError("copied source must be independent regular file")
    orig_raw = stable_guest_bytes(original)
    copy_raw = stable_guest_bytes(source)
    if orig_raw != copy_raw:
        raise ValueError("guest SD source and copied telemetry differ")
    return copy_raw, {
        "sd_binding": "GUEST_ORIGINAL_AND_COPY_BYTE_IDENTICAL",
        "sd_original_name": original.name,
        "sd_original_sha256": hashlib.sha256(orig_raw).hexdigest(),
        "sd_copy_sha256": hashlib.sha256(copy_raw).hexdigest(),
        "sd_copy_bytes": len(copy_raw),
    }

def bind_export_receipt(receipt_path: Path, csv_length: int) -> dict:
    """Require guest writer's exact independent post-join status receipt."""
    raw = stable_guest_bytes(receipt_path)
    expected = (
        f"export_status=0\npath_present=1\nfile_size={csv_length}\n"
    ).encode("ascii")
    if raw != expected:
        raise ValueError(
            "guest audout export status/size not confirmed by receipt"
        )
    return {
        "guest_export_receipt": "GUEST_WRITER_SUCCEEDED_AND_STAT_VISIBLE",
        "guest_export_receipt_sha256": hashlib.sha256(raw).hexdigest(),
    }


def read_telemetry(path: Path) -> dict:
    return parse_telemetry(stable_guest_bytes(path))

def parse_telemetry(raw: bytes, *, phase: int = 0) -> dict:
    # Stage296: an explicit phase8 query is not owed until attempt9,
    # even if the capture ends at attempts 1..8 of its last 16-call
    # block. Phase0 remains the default for all historical audits.
    if type(phase) is not int or not 0 <= phase < 16:
        raise ValueError("invalid pre-submit query phase")
    if b"\r" in raw or not raw.endswith(b"\n"):
        raise ValueError("noncanonical audout CSV line endings")
    rows = list(csv.reader(io.StringIO(raw.decode("ascii"), newline=""),
                           strict=True))
    if not rows or rows[0] != HEADER or len(rows) < 3:
        raise ValueError("invalid audout telemetry header/row count")
    if any(len(row) != len(HEADER) or any(not cell for cell in row)
           for row in rows[1:]):
        raise ValueError("missing fields or unexpected columns")
    parsed = []
    for row in rows[1:]:
        item = {"scope": row[0]}
        for key, cell in zip(NUMERIC, row[1:]):
            if key == "second" and row[0] == "TOTAL" and cell == "-1":
                item[key] = -1
            elif not cell.isascii() or not cell.isdecimal():
                raise ValueError("invalid numeric field " + key)
            else:
                item[key] = int(cell)
        parsed.append(item)
    total, *windows = parsed
    if total["scope"] != "TOTAL" or total["second"] != -1:
        raise ValueError("first row must be TOTAL")
    if any(w["scope"] != "SECOND" for w in windows):
        raise ValueError("unexpected window type or duplicate TOTAL")
    if total["overwritten_windows"] or total["clock_errors"]:
        raise ValueError("capture incomplete: evicted windows/clock reversal")
    if any(w["overwritten_windows"] or w["clock_errors"] for w in windows):
        raise ValueError("invalid per-second metadata")
    seconds = [w["second"] for w in windows]
    if seconds != list(range(len(windows))):
        raise ValueError("missing, duplicated or disordered second")
    if len(windows) < 50:
        raise ValueError("not a sustained full-session run")
    for row in parsed:
        if row["returns"] + row["failures"] != row["attempts"]:
            raise ValueError("audout release/error accounting mismatch")
        if row["queue_ok"] == 0 and (row["queue_min"] or row["queue_max"]):
            raise ValueError("unmeasured queue count cannot be nonzero")
        if row["queue_ok"] and row["queue_min"] > row["queue_max"]:
            raise ValueError("reversed queue sample extrema")
    for key in ["attempts", "returns", "failures", "queue_ok", "queue_errors"]:
        if sum(w[key] for w in windows) != total[key]:
            raise ValueError("window totals mismatch: " + key)
    if total["attempts"] < 100:
        raise ValueError("insufficient audout attempts for 50-second test")
    expected_probes = max(0, (total["attempts"] + 15 - phase) // 16)
    if total["queue_ok"] + total["queue_errors"] != expected_probes:
        raise ValueError("expected 1/16 pre-submit service queries")
    if max(w["max_call_us"] for w in windows) != total["max_call_us"]:
        raise ValueError("maximum call-duration summary mismatch")
    return {
        "result": "GUEST_SD_AUDOUT_TELEMETRY_CONSISTENT",
        "scope": "guest-internal pre-submit queue probes and buffer returns",
        "windows": len(windows),
        "attempts": total["attempts"],
        "releases": total["returns"],
        "failed_attempts": total["failures"],
        "max_call_us": total["max_call_us"],
        "queue_probes_ok": total["queue_ok"],
        "queue_probes_failed": total["queue_errors"],
        "queue_min_pre_submit": total["queue_min"] if total["queue_ok"] else None,
        "queue_max_pre_submit": total["queue_max"] if total["queue_ok"] else None,
        "overwritten_windows": 0,
        "clock_errors": 0,
        "underruns_measured": False,
        "hardware_tested": False,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--locations", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--sd-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw, binding = bind_original_sd(args.source, args.locations, args.sd_root)
    receipt_binding = bind_export_receipt(args.receipt, len(raw))
    report = parse_telemetry(raw)
    report.update(binding)
    report.update(receipt_binding)
    if args.output.exists():
        raise FileExistsError("refuse overwrite of telemetry audit")
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
