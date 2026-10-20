#!/usr/bin/env python3
"""Fail-closed comparison of two *published* Stage390/391 CI artifacts.

No NeXium guest executions or physical audio observations take place here.
"""
import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path

REPO = 'stanmasked/vandal-hearts-switch-remaster'
REPORT_NAME = 'stage390-twenty-two-original-optical-report.json'
REPORT_SHA256 = '75c124bce710631ee7469d46159a05b7341382b3135207ffa6f93b30c4b4338d'
REPORT_LENGTH = 21078
SOURCE_RUNS = [39396243731, 39398650528, 39406193313, 39451930021,
               39459228340, 39462294094, 39466729315, 39476667373,
               39479476340, 39489476524, 39494326413]
NEIXUM_SHA256 = '5026f934ed7cd7d81a5901e536f5fe29b00e117861d432f9be351730afc7d964'
PINS = {
  'macos': {
    'run_id': 39504403456,
    'artifact_id': 12302043117,
    'archive_sha256': '0d821384d510449900a3f7b25de8e5fc16bb75534d590a9fad0b9ce393c00d08',
    'artifact_name': 'stage390-macos-intel-twenty-two-original-guest-evidence-summary',
    'run_name': 'Stage390 Intel macOS independently audit twenty-two original NeXium exits',
    'job_name': 'macOS Intel replay of eleven original guest pairs',
  },
  'linux': {
    'run_id': 39506085942,
    'artifact_id': 12303775933,
    'archive_sha256': '8e86f6fb370db1d2532704c8e35350ac00362d0253ba3f245f892856d13cca46',
    'artifact_name': 'stage391-linux-twenty-two-original-guest-evidence-summary',
    'run_name': 'Stage391 Linux independently audit twenty-two original NeXium exits',
    'job_name': 'Linux x86-64 replay of eleven original guest pairs',
  },
}

def need(ok, message):
    if not ok:
        raise ValueError(message)

def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()

def object_pairs_unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate JSON member')
        result[key] = value
    return result

def read_json_file(path):
    return json.loads(Path(path).read_text(encoding='utf-8'),
                      object_pairs_hook=object_pairs_unique)

def check_hex(value):
    return type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None

def verify_metadata(metadata, pin):
    """Verify original GitHub run, artifact and job metadata."""
    run_id = pin['run_id']
    run = read_json_file(metadata / ('%d-run.json' % run_id))
    art = read_json_file(metadata / ('%d-artifact.json' % run_id))
    jobs = read_json_file(metadata / ('%d-jobs.json' % run_id))
    need(type(run) is dict and run.get('id') == run_id and
         run.get('name') == pin['run_name'] and
         run.get('event') == 'pull_request' and
         run.get('status') == 'completed' and run.get('conclusion') == 'success' and
         run.get('repository', {}).get('full_name') == REPO,
         'original workflow run provenance/success mismatch')
    need(type(art) is dict and art.get('id') == pin['artifact_id'] and
         art.get('name') == pin['artifact_name'] and
         art.get('expired') is False and
         art.get('workflow_run', {}).get('id') == run_id and
         type(art.get('size_in_bytes')) is int and
         0 < art['size_in_bytes'] < 2_000_000,
         'original artifact provenance/name/size mismatch')
    need(type(jobs) is dict and type(jobs.get('jobs')) is list and
         len(jobs['jobs']) == 1, 'unexpected workflow jobs')
    job = jobs['jobs'][0]
    need(job.get('run_id') == run_id and job.get('name') == pin['job_name'] and
         job.get('status') == 'completed' and job.get('conclusion') == 'success',
         'original audited platform job was not successful')
    return {'workflow_run_id':run_id, 'artifact_id':pin['artifact_id'],
            'workflow_name':pin['run_name'], 'verified_successful_job':pin['job_name']}

def verify_zip(path, pin, expected_report_sha=REPORT_SHA256,
               expected_report_length=REPORT_LENGTH):
    archive = Path(path).read_bytes()
    need(0 < len(archive) < 2_000_000, 'invalid or oversized source ZIP')
    digest = sha256_bytes(archive)
    need(digest == pin['archive_sha256'], 'official original ZIP SHA-256 mismatch')
    try:
        with zipfile.ZipFile(path, 'r') as z:
            files = z.infolist()
            need(len(files) == 1 and files[0].filename == REPORT_NAME and
                 not files[0].is_dir(), 'unexpected ZIP entry, duplicates or paths')
            info = files[0]
            mode = info.external_attr >> 16
            need(not stat.S_ISLNK(mode) and
                 info.file_size == expected_report_length and
                 info.compress_size > 0 and
                 info.compress_size < 1_000_000 and
                 z.testzip() is None, 'ZIP CRC/size/symlink rejection')
            report = z.read(info)
    except (zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        raise ValueError('source ZIP corrupt') from exc
    need(len(report) == expected_report_length and
         sha256_bytes(report) == expected_report_sha,
         'source JSON exact length/SHA-256 mismatch')
    return report, digest

def verify_report(value):
    need(type(value) is dict and
         value.get('schema') == 'vh-stage390-twenty-two-original-audio-exits/v1' and
         value.get('result') == 'STAGE390_TWENTY_TWO_SOURCE_PINNED_NEIXUM_GUEST_EXITS' and
         value.get('source_run_ids') == SOURCE_RUNS and
         value.get('original_guest_sessions') == 22 and
         value.get('guest_wait_result_zero') == 22 and
         value.get('exact_returned_descriptors') == 22 and
         value.get('unique_crc_verified_optical_packets') == 22 and
         value.get('distinct_original_optical_pngs') == 22 and
         value.get('complete_music_scene_transitions') == 88 and
         value.get('dropped_guest_events') == 0 and
         value.get('distinct_reason_counter_csv_sha256_count') == 20 and
         value.get('physical_switch_speaker_audio_tested') is False and
         value.get('cause_of_historical_0xEA01_proven') is False and
         value.get('new_guest_sessions_created_by_audit') is False,
         'report semantics inconsistent with authentic Stage390 source replay')
    em = value.get('last_two_emulator_byte_identity')
    need(type(em) is dict and em.get('binary_sha256') == NEIXUM_SHA256 and
         em.get('same_neixum_binary_on_runs_10_and_11') is True and
         em.get('same_neixum_binary_on_runs_1_to_9_proven') is False,
         'overstated historical emulator identity')
    sessions = value.get('sessions')
    need(type(sessions) is list and len(sessions) == 22, 'original sessions missing')
    expected = [(run, trial, sec) for run in SOURCE_RUNS
                for trial, sec in [('a',6), ('b',12)]]
    need([(s.get('run_id'),s.get('trial'),s.get('dwell_seconds')) for s in sessions]
         == expected, 'original guest order/dwell substitution')
    for s in sessions:
        need(s.get('guest_result') == 0 and
             s.get('released_descriptors') == 1 and
             s.get('complete_scene_serials') == 4 and
             s.get('dropped_guest_events') == 0 and
             type(s.get('tail_interval_ms')) in (int,float) and
             0 < s['tail_interval_ms'] < 12 and
             all(check_hex(s.get(k)) for k in ('original_optical_sha256',
                  'pixel_packet_sha256', 'original_reason_sha256')),
             'source session consistency failure')
    need(len({s['original_optical_sha256'] for s in sessions}) == 22 and
         len({s['pixel_packet_sha256'] for s in sessions}) == 22 and
         len({s['original_reason_sha256'] for s in sessions}) == 20,
         'reused source pixels or unexpected reason CSV count')

def compare(macos_zip, linux_zip, metadata, pins=PINS,
            expected_report_sha=REPORT_SHA256, expected_report_length=REPORT_LENGTH):
    metadata = Path(metadata)
    receipts = {}
    reports = {}
    for platform, path in (('macos',macos_zip), ('linux',linux_zip)):
        pin = pins[platform]
        receipt = verify_metadata(metadata, pin)
        report, zip_sha = verify_zip(path, pin, expected_report_sha,
                                     expected_report_length)
        parsed = json.loads(report.decode('utf-8'),
                            object_pairs_hook=object_pairs_unique)
        verify_report(parsed)
        receipt['original_zip_sha256'] = zip_sha
        receipts[platform] = receipt
        reports[platform] = report
    need(reports['macos'] == reports['linux'],
         'cross-OS original JSON differs byte-for-byte')
    return {'schema':'vh-stage392-original-ci-archive-cross-os-equality/v1',
            'result':'STAGE392_BOTH_ORIGINAL_PLATFORM_REPORTS_IDENTICAL',
            'original_json_filename':REPORT_NAME,
            'original_json_bytes':len(reports['linux']),
            'original_json_sha256':sha256_bytes(reports['linux']),
            'original_guest_sessions':22,
            'original_source_runs':11,
            'complete_music_scene_transitions':88,
            'macos':receipts['macos'],'linux':receipts['linux'],
            'new_guest_sessions_created':False,
            'emulator_executed_on_mac':False,
            'physical_switch_speaker_tested':False,
            'cause_of_historical_0xEA01_proven':False}

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--macos-zip', type=Path, required=True)
    ap.add_argument('--linux-zip', type=Path, required=True)
    ap.add_argument('--metadata', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        need(not args.output.exists() and not args.output.is_symlink(),
             'will not overwrite a previous report')
        result = compare(args.macos_zip,args.linux_zip,args.metadata)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x',encoding='utf-8') as f:
            json.dump(result,f,sort_keys=True,indent=2)
            f.write('\n')
        print(json.dumps({'result':result['result'],
                          'report_sha256':result['original_json_sha256']},sort_keys=True))
        return 0
    except (ValueError,OSError,UnicodeError,TypeError,KeyError,IndexError) as exc:
        print(json.dumps({'result':'STAGE392_CROSS_OS_SOURCE_NOT_VERIFIED',
                          'error':str(exc)},sort_keys=True))
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
