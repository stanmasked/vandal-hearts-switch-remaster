"""Stage380 synthetic fail-closed checks (not a guest/hardware test)."""
from pathlib import Path
from unittest import TestCase
from tempfile import TemporaryDirectory
from unittest import mock
import importlib.util
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import audit_stage380_original_timeout_chronology as audit


def metadata(spec=audit.SOURCE[0]):
    _,rid,_,sha,_,_=spec
    pin=audit.SOURCE_IDENTITY[rid]
    run={'id':rid,'head_sha':pin['head'],'event':'push','run_attempt':1,
         'status':'completed','conclusion':'success',
         'name':'Experimental NRO runtime smoke test',
         'repository':{'full_name':audit.REPO}}
    artifact={'id':pin['artifact'],'name':'nexium-runtime-evidence',
              'digest':'sha256:'+sha,'size_in_bytes':26987,'expired':False,
              'workflow_run':{'id':rid,'head_sha':pin['head']}}
    jobs={'jobs':[{'name':n,'run_id':rid,'status':'completed','conclusion':'success'}
        for n in ('Build libnx NRO for runtime smoke test',
                  'Launch current-workflow audout NRO in NeXium')]}
    return run,artifact,jobs


class Stage380Tests(TestCase):
    def test_original_provenance_positive(self):
        spec=audit.SOURCE[0];run,artifact,jobs=metadata(spec)
        audit.check_origin(run,artifact,jobs,spec,26987)

    def test_original_run_head_or_status_forgery_rejected(self):
        for field,bad in (('head_sha','0'*40),('status','queued'),
                          ('conclusion','failure'),('event','pull_request'),
                          ('run_attempt',2)):
            run,artifact,jobs=metadata();run[field]=bad
            with self.subTest(field=field),self.assertRaises(ValueError):
                audit.check_origin(run,artifact,jobs,audit.SOURCE[0],26987)

    def test_artifact_sha_size_or_identity_substitution_rejected(self):
        for field,bad in (('id',999),('name','some-other-artifact'),
                          ('digest','sha256:'+'f'*64),('size_in_bytes',200),
                          ('expired',True)):
            run,artifact,jobs=metadata();artifact[field]=bad
            with self.subTest(field=field),self.assertRaises(ValueError):
                audit.check_origin(run,artifact,jobs,audit.SOURCE[0],26987)

    def test_original_guest_job_missing_or_failed_rejected(self):
        run,artifact,jobs=metadata();jobs['jobs'][1]['conclusion']='failure'
        with self.assertRaises(ValueError):
            audit.check_origin(run,artifact,jobs,audit.SOURCE[0],26987)
        run,artifact,jobs=metadata();jobs['jobs'].pop()
        with self.assertRaises(ValueError):
            audit.check_origin(run,artifact,jobs,audit.SOURCE[0],26987)

    def test_canonical_two_column_guest_csv(self):
        self.assertEqual(audit.parse_csv(b'scope,value\nwait_result,59905\n'),{'wait_result':59905})

    def test_duplicate_or_non_numeric_guest_csv_rejected(self):
        for raw in (b'scope,value\nx,0\nx,1\n',b'scope,value\nx,-1\n',
                    b'scope,value\nx,abc\n',b'other,header\nx,1\n',b'',
                    b'scope,value\nx,1\r\n'):
            with self.subTest(raw=raw),self.assertRaises((ValueError,UnicodeError)):
                audit.parse_csv(raw)

    def test_canonical_sixteen_guest_buffer_call_rows(self):
        sample=(b'total_attempts,sequence,begin_guest_ns,end_guest_ns,lease_returned\n'
                b'8,7,100,200,1\n8,8,300,400,1\n')
        self.assertEqual(audit.parse_csv(sample),[(8,7,100,200,1),(8,8,300,400,1)])

    def test_truncated_guest_buffer_history_rejected(self):
        with self.assertRaises(ValueError):
            audit.parse_csv(b'total_attempts,sequence,begin_guest_ns,end_guest_ns,lease_returned\n8,7,100\n')

    def test_source_archive_missing_rejected(self):
        with TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                audit.replay(audit.SOURCE[0],Path(folder))

    def test_refuses_report_overwrite_without_writing(self):
        with TemporaryDirectory() as folder:
            destination=Path(folder)/'report.json'
            destination.write_text('already-existing\n')
            status=audit.main(['--originals',folder,'--metadata',folder,
                               '--output',str(destination)])
            self.assertEqual(status,2)
            self.assertEqual(destination.read_text(),'already-existing\n')
