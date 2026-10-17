#!/usr/bin/env python3
"""Guard the native audout diagnostic's four fixed report screens.

This counts explicit newlines in C printf format literals; it cannot
measure actual console font widths or lines wrapped by unusually large
numeric counters. It does reject accidental growth beyond a conservative
28-line envelope before the next on-device listening session.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "probes" / "audout_audio_smoke.c"
SOURCE = ROOT / "source" / "vh_audio_report_pages.h"

def count_lines(source: str) -> int:
    # Only static literal format strings are accepted on the report.
    formats = re.findall(r'\bprintf\s*\(\s*"((?:\\.|[^"\\])*)"', source, re.S)
    return sum(fmt.count(r"\n") for fmt in formats)


def main() -> None:
    src = PROBE.read_text(encoding="utf-8")
    hdr = SOURCE.read_text(encoding="utf-8")
    assert "#define VH_AUDIO_REPORT_PAGE_COUNT 4u" in hdr
    # A photo of any page identifies the checked-out source. The
    # fourth page must also show the full Git hash and its dirty flag;
    # no source tag means no silent "verified" provenance.
    assert 'VH_AUDIO_BUILD_REV' in src
    assert 'VH_AUDIO_BUILD_STATUS' in src
    assert 'printf("VH audout / %.12s [%s]\\n"' in src
    assert 'printf("Git source: %s [%s]\\n"' in src
    assert '"UNKNOWN"' in src and '"NO-GIT"' in src


    start = src.index("static void vh_audio_show_report(")
    stop = src.index("\nint main(", start)
    report = src[start:stop]
    branch = "    if (page==0u) {"
    assert report.count(branch) == 1
    prefix, rest = report.split(branch, 1)
    pieces = re.split(
        r"    } else if \(page==[12]u\) \{|    } else \{",
        rest,
    )
    assert len(pieces) == 4, f"expected four report branches, got {len(pieces)}"
    footer_anchor = '    printf("\\nLEFT/RIGHT change page; PLUS exit.\\n");'
    assert pieces[-1].count(footer_anchor) == 1
    pieces[-1], footer = pieces[-1].split(footer_anchor, 1)
    footer = footer_anchor + footer
    assert [f"REPORT {i}/4" in p for i, p in enumerate(pieces, 1)] == [
        True, True, True, True,
    ]
    for i, body in enumerate(pieces, 1):
        rows = count_lines(prefix) + count_lines(body) + count_lines(footer)
        assert rows <= 28, f"report page {i} uses {rows} explicit lines (>28)"
        assert rows >= 8, f"report page {i} unexpectedly empty ({rows} lines)"
        print(f"audout report page {i}/4: {rows} explicit lines")
    first, pcm, marks, home = pieces
    for required in ("PCM accounting", "DSP avg/peak", "Calls=", "fake=%llu", "untimed=%llu", "timing=%s", "ZL=%s", "ZR=%s"):
        assert required in first
    for required in ("PCM SEAMS", "Failed logical pages", "Seam audit"):
        assert required in pcm
    for required in ("HUMAN A", "Event overlaps", "A polls"):
        assert required in marks
    for required in (
        "HOME / RETURNED PCM", "First PCM after HOME", "HOME lag bins",
        "Undelivered submits", "HOME focus notify", "PCM accounting",
    ):
        assert required in home
        if required not in ("PCM accounting",):
            assert required not in first
    # Physical ZL must only arm an on-device timing fault; the
    # actual bad clock is injected by native_submit after a returned
    # descriptor and remains visible as a failed telemetry trial.
    assert "HidNpadButton_ZL" in src
    assert "vh_audio_timing_fault_arm(&output.timing_injection)" in src
    assert "vh_audio_timing_fault_frequency(" in src
    assert "result=31;" in src
    # The ZL label must agree with returned descriptors and rejected timing.
    assert "vh_audio_output_verify_timing_injection(" in src
    assert "timing_evidence || injection_evidence<0" in src
    assert "result=32;" in src
    # The physical ZR control rejects a synthetic wrapper-level submit
    # BEFORE leasing PCM or calling the real audout service. The existing
    # recovery path retries exactly the already-rendered PCM page.
    assert "HidNpadButton_ZR" in src
    assert "vh_audio_submit_fault_arm(&output.submit_injection)" in src
    assert "vh_audio_output_record_synthetic_submit_failure(" in src
    assert "vh_audio_submit_fault_consume(&dev->submit_injection)" in src
    assert "vh_audio_output_verify_submit_injection(" in src
    assert "submit_injection_evidence<0" in src
    assert "result=33;" in src
    assert "result=34;" in src
    assert "result=35;" in src
    assert count_lines(footer) >= 3
    print("audout report four-screen structure PASS")


if __name__ == "__main__":
    main()
