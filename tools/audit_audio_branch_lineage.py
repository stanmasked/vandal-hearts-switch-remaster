#!/usr/bin/env python3
"""Conservative, asset-free readiness inventory for parallel Switch branches.

This is a *preflight inventory*, NOT a git merge or proof of mergeability.
It fails closed when the destination branch lacks the audio foundation.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

CORE = (
    'source/vh_audio_stream.c',
    'source/vh_audio_resample.c',
    'source/vh_native_vab.c',
    'source/vh_native_spu.c',
    'source/vh_native_seq.c',
    'source/vh_spu_reverb.c',
    'source/vh_music_scene.c',
    'source/vh_switch_game_audio.c',
    'source/vh_game_music_mailbox.c',
    'source/vh_game_music_banks.c',
)


class BranchAuditError(ValueError):
    pass


def git(repo: Path, *arguments: str) -> str:
    proc = subprocess.run(
        ['git', '-C', str(repo), *arguments],
        text=True, capture_output=True, check=False,
    )
    if proc.returncode:
        raise BranchAuditError('Git operation failed (ref absent, shallow history, '
                               'or unreadable tree): ' + ' '.join(arguments) +
                               '\n' + proc.stderr.strip()[:320])
    return proc.stdout.strip()


def audit(repo: Path, destination: str, audio: str) -> dict:
    """Describe two refs; never assert a merge is safe just from file names."""
    dest_sha = git(repo, 'rev-parse', '--verify', destination + '^{commit}')
    audio_sha = git(repo, 'rev-parse', '--verify', audio + '^{commit}')
    common = git(repo, 'merge-base', dest_sha, audio_sha)
    ahead_behind = git(repo, 'rev-list', '--left-right', '--count',
                       dest_sha + '...' + audio_sha).split()
    if len(ahead_behind) != 2:
        raise BranchAuditError('Unexpected ahead/behind format')
    destination_only_commits, audio_only_commits = map(int, ahead_behind)
    dest_files = set(git(repo, 'ls-tree', '-r', '--name-only', dest_sha,
                         '--', 'source').splitlines())
    audio_files = set(git(repo, 'ls-tree', '-r', '--name-only', audio_sha,
                          '--', 'source').splitlines())
    absent_from_audio = sorted(set(CORE) - audio_files)
    absent_from_main = sorted(set(CORE) - dest_files)
    if absent_from_audio:
        status = 'INVALID_AUDIO_BRANCH_MISSING_REQUIRED_FOUNDATION'
    elif absent_from_main:
        status = 'BLOCKED_DESTINATION_MISSING_AUDIO_FOUNDATION'
    elif destination_only_commits and audio_only_commits:
        status = 'BLOCKED_DIVERGENT_HISTORY_NEEDS_INTEGRATION_REVIEW'
    else:
        status = 'READY_FOR_REVIEW_NOT_MERGE_APPROVAL'
    return {
        'schema': 'vh-audio-branch-prerequisites/v1',
        'status': status,
        'destination_ref': destination, 'destination_sha': dest_sha,
        'audio_ref': audio, 'audio_sha': audio_sha,
        'merge_base_sha': common,
        'destination_only_commits': destination_only_commits,
        'audio_only_commits': audio_only_commits,
        'destination_source_file_count': len(dest_files),
        'audio_source_file_count': len(audio_files),
        'required_audio_foundation': list(CORE),
        'missing_in_destination': absent_from_main,
        'missing_in_audio': absent_from_audio,
        'audio_only_source_paths': sorted(audio_files - dest_files),
        'destination_only_source_paths': sorted(dest_files - audio_files),
        'git_merge_tested': False,
        'full_build_tested': False,
        'physical_switch_audio_tested': False,
        'safe_to_merge_asserted': False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--destination', default='origin/main')
    parser.add_argument('--audio', default='origin/test/cdxa-extract-decode-pipeline')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--expect-status',
                        help='Explicitly expected gate status; require review when changed')
    args = parser.parse_args()
    try:
        result = audit(args.repo, args.destination, args.audio)
    except BranchAuditError as exc:
        print(json.dumps({'status': 'AUDIT_FAILED_CLOSED', 'error': str(exc)},
                         sort_keys=True))
        return 2
    rendered = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding='utf-8')
    print(rendered, end='')
    # Without an explicitly expected status, a blocked status is an error.
    if args.expect_status:
        return 0 if result['status'] == args.expect_status else 3
    return 0 if result['status'] == 'READY_FOR_REVIEW_NOT_MERGE_APPROVAL' else 4


if __name__ == '__main__':
    raise SystemExit(main())
