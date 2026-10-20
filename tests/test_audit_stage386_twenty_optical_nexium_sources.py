"""Synthetic anti-substitution cases. These are not actual guest executions."""
from pathlib import Path
from unittest import TestCase,mock
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import audit_stage373_six_optical_originals as original
import audit_stage383_eighteen_optical_originals as prior
import audit_stage386_twenty_optical_nexium_sources as m


def scenario():
    rows=[]
    for i,(run,tag) in enumerate((r,t) for r in m.ALL_RUNS for t in ('a','b')):
        rows.append(dict(run_id=run,trial=tag,dwell_seconds=6 if tag=='a' else 12,
                         guest_result=0,released_descriptors=1,
                         pcm_pages_acquired_and_released=2000+i,
                         tail_interval_ms=5.0,complete_scene_serials=4,guest_event_rows=23,
                         dropped_guest_events=0,original_reason_sha256=f'{i+201:064x}',
                         original_optical_sha256=f'{i+101:064x}',pixel_packet_sha256=f'{i+1:064x}'))
    rows[13]['original_reason_sha256']=rows[11]['original_reason_sha256']
    old={'result':prior.RESULT,'source_run_ids':list(prior.ALL_RUNS),
         'original_guest_sessions':18,'successful_software_wait_results':18,
         'distinct_original_optical_pngs':18,'distinct_crc_checked_optical_packets':18,
         'physical_switch_speaker_audio_tested':False,'cause_of_historical_0xEA01_proven':False,
         'sessions':rows[:18]}
    emulator={'archive_sha256':m.EXPECTED_EMULATOR_TAR,'binary_sha256':m.EXPECTED_EMULATOR_BIN,
         'same_binary_in_earlier_nine_runs_proven':False,
         'binary_unchanged_between_tenth_guest_runs_proven_by_original_ci_step':True,
         'physical_switch_audio_tested':False}
    return old,rows[18:],emulator

class Stage386Tests(TestCase):
    def test_accept_20_originals_distinct_optical_and_repeated_counters(self):
        r=m.combine(*scenario())
        self.assertEqual((r['original_guest_sessions'],r['complete_music_scene_transitions']),(20,80))
        self.assertEqual(r['distinct_reason_counter_csv_sha256_count'],19)
        self.assertFalse(r['physical_switch_speaker_audio_tested'])

    def test_reject_reused_png_and_pixel_packet(self):
        for field in ('original_optical_sha256','pixel_packet_sha256'):
            p,q,e=scenario();q[0][field]=p['sessions'][0][field]
            with self.subTest(field=field),self.assertRaises(ValueError): m.combine(p,q,e)

    def test_reject_bad_audio_results_and_lease(self):
        for field,val in (('guest_result',59905),('released_descriptors',0),
                          ('pcm_pages_acquired_and_released',0),
                          ('pcm_pages_acquired_and_released',True),('tail_interval_ms',12),
                          ('complete_scene_serials',3),('guest_event_rows',22),('dropped_guest_events',1)):
            p,q,e=scenario();q[0][field]=val
            with self.subTest(field=field),self.assertRaises(ValueError): m.combine(p,q,e)

    def test_reject_swap_missing_extra_and_wrong_guest(self):
        for kind in ('swap','missing','extra','wrong'):
            p,q,e=scenario()
            if kind=='swap': q.reverse()
            if kind=='missing':q.pop()
            if kind=='extra':q.append(q[1])
            if kind=='wrong':q[0]['run_id']=0
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.combine(p,q,e)

    def test_reject_prior_receipt_tampering(self):
        for field,val in (('result','forged'),('original_guest_sessions',19),
                          ('source_run_ids',[0]),('physical_switch_speaker_audio_tested',True)):
            p,q,e=scenario();p[field]=val
            with self.subTest(field=field),self.assertRaises(ValueError):m.combine(p,q,e)

    def test_reject_emulator_binary_tar_and_hardware_forgery(self):
        for field,val in (('archive_sha256','0'*64),('binary_sha256','0'*64),
                          ('same_binary_in_earlier_nine_runs_proven',True),
                          ('binary_unchanged_between_tenth_guest_runs_proven_by_original_ci_step',False),
                          ('physical_switch_audio_tested',True)):
            p,q,e=scenario();e[field]=val
            with self.subTest(field=field),self.assertRaises(ValueError):m.combine(p,q,e)

    def test_reject_malformed_original_source_digest(self):
        p,q,e=scenario();q[1]['pixel_packet_sha256']='bad'
        with self.assertRaises(ValueError):m.combine(p,q,e)

    def test_invalid_source_cleanup_ensures_no_fake_pin_left(self):
        p,q,e=scenario();before=dict(original.RUNS)
        with mock.patch.object(prior,'audit',return_value=p),\
             mock.patch.object(original,'verify',side_effect=ValueError('missing')):
            with self.assertRaises(ValueError):m.audit(Path('/absent'),Path('/absent'))
        self.assertEqual(original.RUNS,before)

    def test_reject_original_pin_collision(self):
        with mock.patch.dict(original.RUNS,{m.TENTH_RUN:{'forged':True}}):
            with self.assertRaises(ValueError):m.audit(Path('/absent'),Path('/absent'))

    def test_reject_bad_tenth_emulator_source_receipt(self):
        # Patch only filesystem opening; test exact nested source-binding predicates.
        with mock.patch.object(original,'metadata',side_effect=[
          {'schema':'vh-stage384-nexium-runtime-bytes/v1','result':'STAGE384_ONE_GUEST_RUN_NEXIUM_BYTES_PINN',
           'source_run_id':m.TENTH_RUN,'source_head_sha':m.PIN['merge'],'release_id':340509243,
           'release_asset_id':658656899,'asset_name':'nexium-linux-x86_64.tar.gz',
           'asset_sha256':m.EXPECTED_EMULATOR_TAR,'asset_size_bytes':114182978,
           'advertised_asset_digest_checked':True,'binary_sha256':'0'*64,'binary_name':'nexium',
           'binary_size_bytes':304888160,'hardware_status':'HARDWARE NOT TESTED',
           'physical_audio_output_tested':False,'same_binary_in_historical_runs_proven':False},
          {'release_id':340509243,'release_asset_id':658656899,'asset_name':'nexium-linux-x86_64.tar.gz',
           'archive_sha256':m.EXPECTED_EMULATOR_TAR,'archive_bytes':114182978,
           'hardware_status':'HARDWARE NOT TESTED','result':'STAGE385_RELEASE_ARCHIVE_BYTES_AND_TAR_PATHS_VERIFIED',
           'ready_for_controlled_extraction':True,'github_advertised_sha256_checked':True,
           'binary_authenticity_signed':False,'member_count':15,'symbolic_links':0}]):
            with self.assertRaises(ValueError):m.check_provenance(Path('/fake'))
