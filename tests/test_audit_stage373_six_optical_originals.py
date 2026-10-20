#!/usr/bin/env python3
"""Synthetic fail-closed Stage373 tests; never substitute these for guest runs."""
from __future__ import annotations
import copy
import hashlib
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[0]))
import audit_stage373_six_optical_originals as a

def png_chunk(kind,data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))

def synth_packet(offset=0, corrupt_crc=False):
    p=bytearray(924)
    p[:8]=b'VHFBTRC1';p[8]=23
    seq=[]
    for i in range(3):seq.append((1,0,0,1000+i+offset))
    for serial,scene in enumerate((2,1,2,1),1):
        for kind in range(1,6):seq.append((kind,scene,serial,10000*serial+kind*100+offset))
    assert len(seq)==23
    for i,(kind,scene,serial,ts) in enumerate(seq):
        at=13+i*14;p[at]=kind;p[at+1]=scene
        p[at+2:at+6]=serial.to_bytes(4,'little')
        p[at+6:at+14]=ts.to_bytes(8,'little')
    crc=zlib.crc32(p[:909])&0xffffffff
    p[909:913]=((crc ^ 0x01000000) if corrupt_crc else crc).to_bytes(4,'little')
    return bytes(p)

def synth_png(packet, filter_type=0):
    # Synthetic native 1280x720 RGB framebuffer with a magenta calibration
    # border at (250,160), bit modules 7x7. No external image packages.
    assert len(packet)==924
    width,height=1280,720
    frame=bytearray(width*height*3)
    def rect(x0,y0,x1,y1,rgb):
        sample=bytes(rgb)
        stride=width*3
        for y in range(y0,y1):
            start=y*stride+3*x0
            frame[start:start+(x1-x0)*3]=sample*(x1-x0)
    rect(250,160,250+798,160+476,(255,0,255))
    rect(257,167,257+784,167+462,(255,255,255))
    for i,v in enumerate(packet):
        for bit in range(8):
            if v & (128>>bit):
                idx=i*8+bit
                col,row=idx%112,idx//112
                xx,yy=257+col*7,167+row*7
                rect(xx,yy,xx+7,yy+7,(0,0,0))
    compressed=zlib.compress(b''.join(b'\x00'+frame[y*width*3:(y+1)*width*3] for y in range(height)),9)
    return (b'\x89PNG\r\n\x1a\n'+png_chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+
            png_chunk(b'IDAT',compressed)+png_chunk(b'IEND',b''))

def csv_scopes(**kwargs):
    return ('scope,value\n'+''.join(f'{k},{v}\n' for k,v in kwargs.items())).encode()

def fixture(root):
    originals=root/'originals';meta=root/'meta'
    originals.mkdir();meta.mkdir()
    run_id=next(iter(a.RUNS));pin=copy.deepcopy(a.RUNS[run_id])
    pin['optical']=[];pin['reason']=[]
    trial_records=[]
    source=originals/str(run_id);source.mkdir()
    for idx,tag in enumerate(('a','b')):
        folder=source/'stage371-originals'/tag;folder.mkdir(parents=True)
        raw_files={
          'reason':csv_scopes(tail_reason_code=7,abandoned_sessions=0,lease_pages_acquired=100+idx,lease_pages_released=100+idx),
          'result':csv_scopes(stage351_tail_reason_code=7,audout_wait_result_raw=0),
          'descriptor':csv_scopes(stage351_tail_reason_code=7,audout_wait_result_raw=0,released_count_reported=1,returned_pointer_present=1,returned_pointer_matches_submitted=1),
        }
        digests={}
        for kind,content in raw_files.items():
            (folder/a.FILES[kind]).write_bytes(content)
            digests[kind]=a.sha(content)
        pin['reason'].append(digests['reason'])
        optical=synth_png(synth_packet(idx*100))
        (folder/'scene-optical-trace.png').write_bytes(optical)
        pin['optical'].append(a.sha(optical))
        additional={}
        other={
          'audio-exit-probe-context-000.csv':csv_scopes(tail_begin_guest_ns=90000,tail_end_guest_ns=95000,tail_elapsed_ns=5000,stage351_tail_reason_code=7),
          'audio-lease-reconciliation-000.csv':csv_scopes(lease_pages_acquired=100+idx,lease_pages_released=100+idx,abandoned_sessions=0),
        }
        for name,data in other.items():
            (folder/name).write_bytes(data)
            additional[name]={'present':True,'parsed':False,'sha256':a.sha(data)}
        trial_records.append({
          'capture_tag':tag,'exit_dwell_seconds':(6 if tag=='a' else 12),'guest_source_run_id':run_id,
          'source_guest_sd_root':f'/tmp/vh-nexium-stage266-{run_id}-{tag}',
          'source_guest_csv_sha256':digests,'original_optical_frame_sha256':a.sha(optical),
          'optional_original_telemetry':additional,'source_guest_reason_code':7,
          'original_service_result':0,'reported_return_count':1,
          'reported_pointer_matches_submitted':True,'original_guest_speaker_audio_observed':False
        })
    (source/'stage371-two-authentic-guest-exits.json').write_text(json.dumps({
      'result':'STAGE371_TWO_SEPARATE_GUEST_WAIT_TUPLES_FROM_SAME_NRO_RECORDED',
      'source_run_id':run_id,'source_git_sha':pin['merge'],'source_run_attempt':1,
      'single_verified_nro_sha256':a.NRO_SHA,'two_isolated_original_guest_roots':True,
      'old_0xEA01_root_cause_proven':False,'physical_nintendo_switch_audio_tested':False,
      'captures':trial_records}))
    (source/'stage371-nro-preflight.json').write_text(json.dumps({
      'result':'SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED','git_sha':pin['merge'],
      'nro_sha256':a.NRO_SHA,'run_id':run_id,'run_attempt':1,'nro_bytes':299064,'hardware_status':'HARDWARE NOT TESTED'}))
    (meta/f'{run_id}-run.json').write_text(json.dumps({'id':run_id,'status':'completed','conclusion':'success','event':'pull_request','head_sha':pin['head'],'run_attempt':1,'repository':{'full_name':a.REPO}}))
    (meta/f'{run_id}-merge.json').write_text(json.dumps({'sha':pin['merge'],'parents':[{'sha':a.BASE_SHA},{'sha':pin['head']}]}))
    (meta/f'{run_id}-artifact.json').write_text(json.dumps({'id':pin['artifact'],'name':'stage371-two-guest-exit-original-observations','digest':pin['digest'],'expired':False,'workflow_run':{'id':run_id,'head_sha':pin['head']}}))
    (meta/f'{run_id}-jobs.json').write_text(json.dumps({'jobs':[{'name':name,'run_id':run_id,'status':'completed','conclusion':'success','steps':[{'name':x,'conclusion':'success'} for x in a.GUEST_STEPS]} for name in ['Validate Stage371 isolated-source invariants before building NRO','Build one original libnx NRO without SDL2','Run two separate NeXium guest exits and audit original CSV files']]}))
    return run_id,source,meta,pin

class Stage373OpticalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_packet=synth_packet()
        cls.fixture_png=synth_png(cls.fixture_packet)

    def test_original_synthetic_optical_packet_decoded(self):
        report=a.optical_decode(self.fixture_png)
        self.assertEqual(report['guest_event_rows'],23)
        self.assertEqual(report['complete_scene_serials'],4)
        self.assertEqual(report['dropped_guest_events'],0)
        self.assertEqual(report['pixel_packet_sha256'],a.sha(self.fixture_packet))

    def test_crc_corrupt_image_rejected(self):
        raw=bytearray(self.fixture_png)
        raw[-10]^=1
        with self.assertRaises(ValueError):a.optical_decode(bytes(raw))

    def test_payload_crc_mismatch_rejected(self):
        bad=synth_png(synth_packet(corrupt_crc=True))
        with self.assertRaisesRegex(ValueError,'packet CRC'):a.optical_decode(bad)

    def test_wrong_dimensions_rejected(self):
        raw=bytearray(self.fixture_png)
        raw[16:20]=(1279).to_bytes(4,'big')
        raw[29:33]=zlib.crc32(raw[12:29]).to_bytes(4,'big')
        with self.assertRaisesRegex(ValueError,'dimensions'):a.png_pixels(bytes(raw))

    def test_bad_csv_duplicate_and_noncanonical_rejected(self):
        for bad in (b'scope,value\nfoo,1\nfoo,2\n',b'scope,value\nfoo,01\n',b'scope,value\nfoo,1\r\n'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):a.scopes(bad)

    def test_synthetic_originals_and_provenance_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id,original,meta,pin=fixture(Path(tmp))
            old=a.RUNS[run_id]
            try:
                a.RUNS[run_id]=pin  # Synthetic test only. Production CLI has immutable pins.
                good=a.verify(run_id,original,meta)
                self.assertEqual(len(good),2)
                self.assertEqual([x['guest_result'] for x in good],[0,0])
                p=meta/f'{run_id}-run.json';v=json.loads(p.read_text());v['conclusion']='failure';p.write_text(json.dumps(v))
                with self.assertRaises(ValueError):a.verify(run_id,original,meta)
            finally:a.RUNS[run_id]=old

    def test_guest_source_swap_and_dwell_forgery_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_id,original,meta,pin=fixture(Path(tmp))
            old=a.RUNS[run_id]
            try:
                a.RUNS[run_id]=pin
                p=original/'stage371-two-authentic-guest-exits.json'
                v=json.loads(p.read_text());v['captures'][1]['exit_dwell_seconds']=6;p.write_text(json.dumps(v))
                with self.assertRaises(ValueError):a.verify(run_id,original,meta)
            finally:a.RUNS[run_id]=old

if __name__=='__main__':unittest.main()
