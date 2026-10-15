#!/usr/bin/env python3
"""Prepare a locally executable, asset-safe Map02 full-trace session.

Does not compile, run, or alter the upstream checkout when preparing. Only
the user can execute the generated build/capture shell script. The user
supplies legally owned disc, US executable and KROM/BIOS inputs locally.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex

from tools.preflight_map02_pcport import inspect
from tools.prepare_map02_pcport import prepare


def shell_words(parts) -> str:
    return " ".join(shlex.quote(str(item)) for item in parts)


def plan_session(upstream: Path, session_directory: Path, *, disc_image: Path,
                 krom_source: Path | None = None, no_webp=False,
                 no_hdvideo=False) -> dict:
    upstream = upstream.expanduser().resolve()
    session_directory = session_directory.expanduser().resolve()
    disc_image = disc_image.expanduser().resolve()
    if session_directory.exists():
        raise ValueError("session directory already exists; refusing to overwrite")
    if session_directory == upstream or upstream in session_directory.parents:
        raise ValueError("session must be outside the upstream checkout")

    preflight = inspect(
        upstream, disc_image=disc_image, krom_source=krom_source,
        no_webp=no_webp, no_hdvideo=no_hdvideo,
    )
    if preflight["blockers"]:
        raise ValueError("Map02 preflight blocked: " + ", ".join(preflight["blockers"]))

    # The pinned US generator resolves SLUS_004.47 relative to the checkout.
    # Do not silently substitute another location or bypass the hash gate.
    retail = (upstream / "SLUS_004.47").resolve()
    if not retail.is_file():
        raise ValueError("expected original US SLUS_004.47 in pinned checkout root")

    trace_dir = session_directory / "trace"
    capture_dir = session_directory / "capture"
    pc_dir = upstream / "platform/pc"
    build_tag = hashlib.sha256(str(session_directory).encode()).hexdigest()[:12]
    build_dir = "build-map02-" + build_tag
    overlay = prepare(upstream, trace_dir, full_trace=True)

    remaster_root = Path(__file__).resolve().parent.parent
    krom = Path(preflight["checks"]["krom_source_path"]).expanduser().resolve()
    make_command = [
        "make", "-f", "Makefile", "-f", str(overlay), "link",
        f"BUILD_DIR={build_dir}", "REGION=us",
    ]
    if no_webp:
        make_command.append("NO_WEBP=1")
    if no_hdvideo:
        make_command.append("NO_HDVIDEO=1")

    binary = pc_dir / build_dir / "vandalhearts_pc"
    # Recheck the local checkout and owned resources immediately before build:
    # the files may have changed since this session was prepared.
    preflight_command = [
        "python3", "-m", "tools.preflight_map02_pcport", str(upstream),
        "--disc-image", str(disc_image), "--krom-source", str(krom),
    ]
    if no_webp:
        preflight_command.append("--no-webp")
    if no_hdvideo:
        preflight_command.append("--no-hdvideo")

    script = "\n".join((
        "#!/bin/sh",
        "set -eu",
        "# Local, user-initiated build + interactive gameplay capture.",
        "# Does not copy the game image or the original executable.",
        "# Stop if generated diagnostic inputs or user-owned files changed.",
        "cd " + shlex.quote(str(remaster_root)),
        shell_words(("python3", "-m", "tools.verify_map02_session",
                     str(session_directory))),
        shell_words(preflight_command) + " > "
            + shlex.quote(str(session_directory / "preflight_at_build.json")),
        "export VH_KROM_SOURCE=" + shlex.quote(str(krom)),
        "cd " + shlex.quote(str(pc_dir)),
        shell_words(make_command),
        "# VH_DISC_IMAGE is supported by the pinned PC-port bootstrap.",
        "export VH_DISC_IMAGE=" + shlex.quote(str(disc_image)),
        "cd " + shlex.quote(str(remaster_root)),
        "capture_status=0",
        shell_words(("python3", "-m", "tools.capture_map02_runtime",
                     str(binary), str(trace_dir), str(capture_dir)))
            + " || capture_status=$?",
        "# Verify any partial evidence even when the game was interrupted.",
        shell_words(("python3", "-m", "tools.verify_map02_capture",
                     str(capture_dir))),
        "# Preserve an easy-to-review PRS/DAT outcome, even for an incomplete capture.",
        shell_words(("python3", "-m", "tools.report_map02_bridge",
                     str(capture_dir), "--markdown",
                     str(capture_dir / "bridge_review.md"),
                     "--json", str(capture_dir / "bridge_review.json"))),
        'if [ "$capture_status" -ne 0 ]; then exit "$capture_status"; fi',
        shell_words(("python3", "-m", "tools.verify_map02_capture",
                     str(capture_dir), "--require-complete")),
        "",
    ))
    script_path = session_directory / "build_capture_verify.sh"
    script_path.write_text(script, encoding="utf-8")
    script_path.chmod(0o700)
    preflight_file = session_directory / "preflight.json"
    preflight_file.write_text(
        json.dumps(preflight, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    provenance_file = trace_dir / "source_provenance.json"
    # Bind the session plan to the exact generated diagnostic manifest and
    # the preflight snapshot, in addition to the shell script checksum.
    def digest_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    manifest = {
        "kind": "map02_user_executed_session_plan",
        "trace_mode": "full",
        "upstream": str(upstream),
        "trace_dir": str(trace_dir),
        "capture_dir": str(capture_dir),
        "binary": str(binary),
        "build_dir": build_dir,
        "user_shell_script": str(script_path),
        "shell_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
        "preflight_sha256": digest_file(preflight_file),
        "provenance_sha256": digest_file(provenance_file),
        "preflight_complete": True,
        "build_executed": False,
        "game_executed": False,
        "warning": "This creates only local diagnostic files. Run the shell script on your own machine; Map02 visual correctness is not yet established.",
    }
    (session_directory / "session_plan.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path, help="pinned upstream checkout")
    parser.add_argument("new_session_directory", type=Path,
                        help="new directory outside upstream; must not already exist")
    parser.add_argument("--disc-image", type=Path, required=True,
                        help="user-owned raw Vandal Hearts USA/Asia disc BIN")
    parser.add_argument("--krom-source", type=Path,
                        help="KROMDAT.BIN or compatible user-owned BIOS")
    parser.add_argument("--no-webp", action="store_true")
    parser.add_argument("--no-hdvideo", action="store_true")
    args = parser.parse_args()
    try:
        manifest = plan_session(
            args.upstream, args.new_session_directory,
            disc_image=args.disc_image, krom_source=args.krom_source,
            no_webp=args.no_webp, no_hdvideo=args.no_hdvideo,
        )
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
