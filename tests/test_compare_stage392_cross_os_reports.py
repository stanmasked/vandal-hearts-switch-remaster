"""Stage392 synthetic positive/negative controls; no original guest data copied."""
import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'tools'))
import compare_stage392_cross_os_reports as audit

def sha(data):
    return hashlib.sha256(data).hexdigest()

def fake_report():
    rows=[]
    for i,(r,t,d) in enumerate((r,t,d) for r in audit.SOURCE_RUNS
                              for t,d in [('a',6),('b',12)]):
        rows.append({'run_id':r,'trial':t,'dwell_seconds':d,'guest_result':0,
                     'released_descriptors':1,'complete_scene_serials':4,
                     'dropped_guest_events':0,'tail_interval_ms':0.1+i/100,
                     'original_optical_sha256':'%064x'%(i+1),
                     'pixel_packet_sha256':'%064x'%(i+101),
                     'original_reason_sha256':'%064x'%(min(i,19)+201)})
    return {'schema':'vh-stage390-twenty-two-original-audio-exits/v1',
            'result':'STAGE390_TWENTY_TWO_SOURCE_PINNED_NEIXUM_GUEST_EXITS',
            'source_run_ids':audit.SOURCE_RUNS,
            'original_guest_sessions':22,'guest_wait_result_zero':22,
            'exact_returned_descriptors':22,
            'unique_crc_verified_optical_packets':22,
            'distinct_original_optical_pngs':22,
            'complete_music_scene_transitions':88,'dropped_guest_events':0,
            'distinct_reason_counter_csv_sha256_count':20,
            'physical_switch_speaker_audio_tested':False,
            'cause_of_historical_0xEA01_proven':False,
            'new_guest_sessions_created_by_audit':False,
            'last_two_emulator_byte_identity':{'binary_sha256':audit.NEIXUM_SHA256,
               'same_neixum_binary_on_runs_10_and_11':True,
               'same_neixum_binary_on_runs_1_to_9_proven':False},'sessions':rows}

def zip_blob(payload, extra=None):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr(audit.REPORT_NAME,payload)
        if extra is not None:
            z.writestr(extra,b'should be rejected')
    return stream.getvalue()

class Stage392Test(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.meta=self.base/'metadata'
        self.meta.mkdir()
        self.report=json.dumps(fake_report(),sort_keys=True,indent=2).encode()+b'\n'
        self.pins=copy.deepcopy(audit.PINS)
        for os_name,pin in self.pins.items():
            b=zip_blob(self.report)
            pin['archive_sha256']=sha(b)
            (self.base/(os_name+'.zip')).write_bytes(b)
            self.write_meta(os_name)

    def write_meta(self,os_name,run_override=None,art_override=None,jobs_override=None):
        pin=self.pins[os_name]
        n=pin['run_id']
        run={'id':n,'name':pin['run_name'],'event':'pull_request',
             'status':'completed','conclusion':'success',
             'repository':{'full_name':audit.REPO}}
        art={'id':pin['artifact_id'],'name':pin['artifact_name'],
             'expired':False,'workflow_run':{'id':n},'size_in_bytes':4000}
        jobs={'jobs':[{'run_id':n,'name':pin['job_name'],
                       'status':'completed','conclusion':'success'}]}
        for obj,override in ((run,run_override),(art,art_override),(jobs,jobs_override)):
            if override: obj.update(override)
        for key,obj in [('run',run),('artifact',art),('jobs',jobs)]:
            (self.meta/('%d-%s.json'%(n,key))).write_text(json.dumps(obj))

    def call_compare(self):
        return audit.compare(self.base/'macos.zip',self.base/'linux.zip',self.meta,
                             self.pins,sha(self.report),len(self.report))

    def test_original_equality_synthetic(self):
        result=self.call_compare()
        self.assertEqual(result['original_guest_sessions'],22)
        self.assertEqual(result['original_json_sha256'],sha(self.report))
        self.assertFalse(result['physical_switch_speaker_tested'])

    def test_mutated_official_zip_hash_rejected(self):
        with (self.base/'linux.zip').open('ab') as f:f.write(b'tamper')
        with self.assertRaisesRegex(ValueError,'ZIP SHA-256'):self.call_compare()

    def test_cross_os_difference_rejected_even_if_re_pinned(self):
        changed=self.report.replace(b'"tail_interval_ms": 0.1',b'"tail_interval_ms": 0.2',1)
        self.assertEqual(len(changed),len(self.report))
        b=zip_blob(changed)
        (self.base/'linux.zip').write_bytes(b)
        self.pins['linux']['archive_sha256']=sha(b)
        with self.assertRaisesRegex(ValueError,'source JSON exact'):self.call_compare()

    def test_extra_zip_member_rejected(self):
        b=zip_blob(self.report,extra='../evil')
        (self.base/'macos.zip').write_bytes(b)
        self.pins['macos']['archive_sha256']=sha(b)
        with self.assertRaisesRegex(ValueError,'unexpected ZIP'):self.call_compare()

    def test_duplicate_zip_member_rejected(self):
        b=zip_blob(self.report,extra=audit.REPORT_NAME)
        (self.base/'macos.zip').write_bytes(b)
        self.pins['macos']['archive_sha256']=sha(b)
        with self.assertRaisesRegex(ValueError,'unexpected ZIP'):self.call_compare()

    def test_non_success_run_rejected(self):
        self.write_meta('macos',run_override={'conclusion':'failure'})
        with self.assertRaisesRegex(ValueError,'workflow run'):self.call_compare()

    def test_not_completed_run_rejected(self):
        self.write_meta('linux',run_override={'status':'queued'})
        with self.assertRaisesRegex(ValueError,'workflow run'):self.call_compare()

    def test_wrong_repo_rejected(self):
        self.write_meta('macos',run_override={'repository':{'full_name':'attacker/fork'}})
        with self.assertRaisesRegex(ValueError,'workflow run'):self.call_compare()

    def test_wrong_artifact_source_rejected(self):
        self.write_meta('macos',art_override={'workflow_run':{'id':1}})
        with self.assertRaisesRegex(ValueError,'artifact provenance'):self.call_compare()

    def test_artifact_expired_rejected(self):
        self.write_meta('linux',art_override={'expired':True})
        with self.assertRaisesRegex(ValueError,'artifact provenance'):self.call_compare()

    def test_unexpected_job_rejected(self):
        self.write_meta('linux',jobs_override={'jobs':[{'run_id':39506085942,
                   'name':'other','status':'completed','conclusion':'success'}]})
        with self.assertRaisesRegex(ValueError,'job was not successful'):self.call_compare()

    def test_failed_job_rejected(self):
        self.write_meta('macos',jobs_override={'jobs':[{'run_id':39504403456,
                   'name':self.pins['macos']['job_name'],
                   'status':'completed','conclusion':'failure'}]})
        with self.assertRaisesRegex(ValueError,'job was not successful'):self.call_compare()

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate JSON member'):
            json.loads('{"a":1,"a":1}',object_pairs_hook=audit.object_pairs_unique)

    def test_overstated_emulator_history_rejected(self):
        v=fake_report()
        v['last_two_emulator_byte_identity']['same_neixum_binary_on_runs_1_to_9_proven']=True
        with self.assertRaisesRegex(ValueError,'historical emulator'):
            audit.verify_report(v)

    def test_guest_failure_rejected(self):
        v=fake_report();v['sessions'][1]['guest_result']=0xEA01
        with self.assertRaisesRegex(ValueError,'session consistency'):
            audit.verify_report(v)

    def test_duplicate_optical_source_rejected(self):
        v=fake_report()
        v['sessions'][1]['pixel_packet_sha256']=v['sessions'][0]['pixel_packet_sha256']
        with self.assertRaisesRegex(ValueError,'reused source pixels'):
            audit.verify_report(v)

    def test_invalid_dwell_order_rejected(self):
        v=fake_report();v['sessions'][0]['dwell_seconds']=12
        with self.assertRaisesRegex(ValueError,'guest order'):
            audit.verify_report(v)

if __name__=='__main__':
    unittest.main()
