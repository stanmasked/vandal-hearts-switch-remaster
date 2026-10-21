#!/usr/bin/env python3
"""Create an OWNER-LOCAL, offline PNG contact sheet after verified BK2 capture.

Images stay in the supplied directory. HTML uses no JavaScript, HTTP links,
remote assets, or automatic upload. Movie input positions are NOT MAP02
evidence, actual PS1 video timing, or authenticated GPU/VRAM observations.
"""
from __future__ import annotations

import argparse
from html import escape
import os
from pathlib import Path
import stat

from tools.map02_private_visual_diff_triage import triage

ROLE_LABELS = (
    ("before", "До паузы"),
    ("middle", "Середина паузы"),
    ("after", "После паузы"),
)
MAX_GROUPS = 10
START_LIMIT = 1663
END_LIMIT = 933949
STYLE = """*{box-sizing:border-box}body{margin:0;background:#141820;color:#e9edf4;font:15px system-ui,-apple-system,sans-serif;line-height:1.55}main{max-width:1400px;margin:auto;padding:24px}h1{font-size:1.8rem;margin:0 0 8px}h2{font-size:1.25rem}.intro{max-width:900px;color:#ccd4df}.notice{border-left:4px solid #d0a854;padding:8px 14px;background:#24242c}.group{border:1px solid #414959;border-radius:10px;background:#1e242e;margin:22px 0;padding:18px}.panels{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.frame{margin:0;min-width:0}.frame img{width:100%;max-height:560px;object-fit:contain;background:#000;border:1px solid #515b6e;image-rendering:auto}.frame figcaption{font-size:.92rem;color:#d1d9e5}.small{font-size:.85rem;color:#bac5d4}code{color:#ead6a3}footer{margin:35px 0;color:#bbc6d4}@media(max-width:750px){.panels{grid-template-columns:1fr}.frame img{max-height:none}}@media print{body{background:#fff;color:#000}.group,.notice{background:#fff;border-color:#777}figcaption,.intro,.small,footer{color:#333!important}main{padding:6px}.group{page-break-inside:avoid}}"""


def _integer(value: object, *, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError("private review data outside supported integer range")
    return value


def _number(value: object, *, maximum: float) -> float:
    if type(value) not in (float, int) or not 0 <= value <= maximum:
        raise ValueError("private review metric outside supported numeric range")
    return float(value)


def render_private_html(report: dict) -> str:
    """Render a static file only from bounded internally-computed metrics."""
    candidates = report.get("private_visual_review_candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= MAX_GROUPS:
        raise ValueError("review contact sheet requires 1..10 capture groups")
    if report.get("map02_identified") is not False or report.get("bizhawk_replay_authenticated") is not False:
        raise ValueError("contact sheet must not elevate PS1 provenance")
    if report.get("screenshot_count") != 3 * len(candidates):
        raise ValueError("screenshot count does not match three image positions per group")
    markup = []
    seen_groups = set()
    for ordinal, entry in enumerate(candidates, 1):
        group = _integer(entry.get("review_group"), low=1, high=MAX_GROUPS)
        if group in seen_groups:
            raise ValueError("duplicate capture group")
        seen_groups.add(group)
        frames = entry.get("zero_based_input_indices")
        dims = entry.get("screenshot_dimensions")
        if not isinstance(frames, list) or len(frames) != 3:
            raise ValueError("capture group must contain three input positions")
        b, m, a = [_integer(i, low=START_LIMIT, high=END_LIMIT - 1) for i in frames]
        if not b < m < a:
            raise ValueError("capture frames are misordered")
        if not isinstance(dims, list) or len(dims) != 2:
            raise ValueError("screenshot dimensions unavailable")
        width = _integer(dims[0], low=1, high=8192)
        height = _integer(dims[1], low=1, high=8192)
        if width * height > 4_000_000:
            raise ValueError("unsupported screenshot size")
        cards = []
        for (role, name), frame in zip(ROLE_LABELS, (b, m, a)):
            filename = "vh_review_w%02d_%s_counter_%07d.png" % (
                group, role, frame + 1)
            cards.append(
                '<figure class="frame"><img src="' + escape(filename, quote=True) +
                '" alt="' + escape(name, quote=True) +
                '" loading="lazy"><figcaption><strong>' + escape(name) +
                '</strong> · BK2 ввод: <code>' + str(frame) +
                '</code> · счётчик-кандидат: <code>' + str(frame + 1) +
                '</code></figcaption></figure>'
            )
        before_middle = entry.get("before_to_middle")
        middle_after = entry.get("middle_to_after")
        if not isinstance(before_middle, dict) or not isinstance(middle_after, dict):
            raise ValueError("RGB comparison data missing")
        fraction1 = _number(before_middle.get("fraction_pixels_above_threshold"), maximum=1)
        fraction2 = _number(middle_after.get("fraction_pixels_above_threshold"), maximum=1)
        mean1 = _number(before_middle.get("mean_absolute_rgb_channel_delta"), maximum=255)
        mean2 = _number(middle_after.get("mean_absolute_rgb_channel_delta"), maximum=255)
        if type(entry.get("prominent_unmasked_pixel_difference")) is not bool:
            raise ValueError("unverified pixel-difference label")
        prominent = "Да" if entry["prominent_unmasked_pixel_difference"] else "Нет"
        markup.append(
            '<section class="group"><h2>Группа ' + str(group) +
            " · порядок просмотра " + str(ordinal) +
            '</h2><p class="small">Различие до → середина: ' +
            "%.1f" % (100 * fraction1) + "% пикселей (RGB " +
            "%.2f" % mean1 + "); середина → после: " +
            "%.1f" % (100 * fraction2) + "% (RGB " +
            "%.2f" % mean2 + "). Выраженное отличие: " + prominent +
            '. Это не означает переход карты.</p><div class="panels">' +
            "".join(cards) + "</div></section>"
        )
    header = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' file:; style-src 'unsafe-inline'; script-src 'none'; connect-src 'none'; form-action 'none'; base-uri 'none'"><title>Vandal Hearts — приватный просмотр кадров BK2</title><style>"""
    tail = """</style></head><body><main><h1>Vandal Hearts — локальный просмотр кадров</h1><p class="intro">Три PNG на группу: до периода без нажатий, его середина и следующий кадр с вводом. Сравнивайте содержание вручную. Кадры обозначены индексами ввода BK2, а не доказанными кадрами видеовывода.</p><p class="notice"><strong>Не доказано:</strong> запуск оригинального PS1, синхронизация входного кадра и изображения, начало MAP02, GPU/VRAM. Значительные изменения пикселей могут быть вызваны меню, курсором, анимацией или эффектами.</p>"""
    footer = """<footer>Локальный файл без JavaScript, внешних ресурсов и передачи изображений. Не добавляйте HTML, PNG, BK2, журналы или планы кадров в публичный GitHub.</footer></main></body></html>"""
    return header + STYLE + tail + "".join(markup) + footer


def write_private_contact_sheet(report: dict, image_root: Path,
                                output_html: Path) -> int:
    root, output = Path(image_root), Path(output_html)
    if (not output.is_absolute() or output.exists() or output.is_symlink()
            or not root.is_absolute() or root.is_symlink() or not root.is_dir()
            or output.parent.is_symlink() or output.parent.resolve() != root.resolve()):
        raise ValueError("HTML must be new and adjacent to private PNGs")
    if output.suffix.lower() != ".html":
        raise ValueError("offline image viewer requires an HTML filename")
    if any((part / ".git").exists() for part in (root, *root.parents)):
        raise ValueError("never write private screenshot viewer inside Git")
    data = render_private_html(report)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(output, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(data)
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    if not stat.S_ISREG(output.stat().st_mode):
        raise ValueError("private HTML not a regular file")
    return len(report["private_visual_review_candidates"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_private_bk2", type=Path)
    parser.add_argument("owner_private_capture_plan", type=Path)
    parser.add_argument("owner_private_bizhawk_log", type=Path)
    parser.add_argument("owner_private_png_directory", type=Path)
    parser.add_argument("--private-html-output", required=True, type=Path)
    parser.add_argument("--pixel-change-threshold", type=int, default=32)
    parser.add_argument("--min-neutral-frames", type=int, default=180)
    parser.add_argument("--max-neutral-frames", type=int, default=1800)
    parser.add_argument("--after-input-frame", type=int, default=1663)
    parser.add_argument("--before-input-frame", type=int, default=933949)
    args = parser.parse_args()
    try:
        report = triage(
            args.owner_private_bk2, args.owner_private_capture_plan,
            args.owner_private_bizhawk_log, args.owner_private_png_directory,
            minimum=args.min_neutral_frames, maximum=args.max_neutral_frames,
            after=args.after_input_frame, before=args.before_input_frame,
            pixel_threshold=args.pixel_change_threshold,
        )
        count = write_private_contact_sheet(
            report, args.owner_private_png_directory, args.private_html_output,
        )
    except (OSError, ValueError, TypeError, UnicodeError, RuntimeError):
        parser.error("private offline BK2 image contact sheet unavailable")
    print("VH_MAP02_PRIVATE_OFFLINE_REVIEW_READY groups=%d original_ps1_verified=0 map02_identified=0" % count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
