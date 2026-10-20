#!/usr/bin/env python3
"""Private one-command Mac handoff: mounted BIN/CUE -> local digest-only JSON.

Never modifies the mounted Drive files. Original game sectors stay exclusively
in the owner's protected local staging directory, not GitHub or CI. A receipt
is a digest and consistency report, not proof of PS1 gameplay or US EXE parity.
"""
import argparse
import json
from pathlib import Path

from tools.check_map02_local_disc_receipt import (
    validate_receipt, verify_receipt_file,
)
from tools.emit_map02_local_disc_receipt import (
    inspect, publish,
)
from tools.stage_map02_private_disc import (
    BIN_NAME, CUE_NAME, stage_disc,
)


def run_private_audit(mounted_bin, mounted_cue, private_parent):
    """Return a verified owner-only receipt path; no original bytes emitted.

    If CD-XA or the previously pinned MAP02 PRS digest is not verified, do
    NOT publish a receipt. The already-staged local copy remains private for
    deliberate inspection/recovery; mounted source files are never altered.
    """
    folder, copied_sha256 = stage_disc(
        mounted_bin, mounted_cue, private_parent
    )
    image = folder / BIN_NAME
    cue = folder / CUE_NAME
    receipt_dir = folder / "receipt"
    report = inspect(image, cue)

    # Stage SHA is computed on the mounted source and independently checked
    # against the staged local destination. inspect() hashes the private
    # destination a THIRD time, and verifies the pinned boot/MAP02 XA sectors.
    if report["raw_image_sha256"] != copied_sha256:
        raise ValueError("mounted-source SHA-256 and audited-copy SHA-256 differ")

    serialized = (json.dumps(report, sort_keys=True) + "\n").encode("ascii")
    validate_receipt(serialized)
    result = publish(report, receipt_dir)
    verified = verify_receipt_file(result)
    if (not verified["receipt_schema_verified"]
            or verified["reported_raw_image_sha256"] != copied_sha256):
        raise ValueError("published digest-only receipt failed revalidation")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mounted_ru_bin", type=Path)
    parser.add_argument("--cue", required=True, type=Path)
    parser.add_argument("--private-parent", required=True, type=Path)
    options = parser.parse_args()
    try:
        receipt = run_private_audit(
            options.mounted_ru_bin, options.cue, options.private_parent
        )
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    # Deliberately omit the user's mounted path, original sectors and full
    # image SHA from stdout. The only produced shareable payload is a JSON
    # with 15 explicitly bounded digest/consistency fields.
    print("MAP02 PRIVATE AUDIT PASS: digest-only receipt:", receipt.name)
    print("No original game bytes were uploaded or printed.")


if __name__ == "__main__":
    main()
