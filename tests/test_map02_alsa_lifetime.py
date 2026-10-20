"""ROM-free Stage273 test: real LD_PRELOAD fake ALSA and counter snapshots."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from audit_map02_alsa_lifetime import parse

FAKE=r"""
typedef unsigned long uframes_t;
typedef long sframes_t;
int snd_pcm_hw_params(void *p,void *q) {(void)p;(void)q;return 0;}
int snd_pcm_hw_params_get_channels(const void *p,unsigned *x)
 {(void)p;*x=2;return 0;}
int snd_pcm_hw_params_get_rate(const void *p,unsigned *x,int *d)
 {(void)p;(void)d;*x=48000;return 0;}
int snd_pcm_hw_params_get_buffer_size(const void *p,uframes_t *x)
 {(void)p;*x=1536;return 0;}
int snd_pcm_hw_params_get_period_size(const void *p,uframes_t *x,int *d)
 {(void)p;(void)d;*x=512;return 0;}
sframes_t snd_pcm_writei(void *p,const void *v,uframes_t n)
 {(void)p;(void)v;return (sframes_t)n;}
sframes_t snd_pcm_mmap_commit(void *p,uframes_t o,uframes_t n)
 {(void)p;(void)o;return (sframes_t)n;}
int snd_pcm_close(void *p) {(void)p;return 0;}
"""
HOST=r"""
#include <unistd.h>
typedef unsigned long uframes_t;
typedef long sframes_t;
extern int snd_pcm_hw_params(void*,void*);
extern sframes_t snd_pcm_writei(void*,const void*,uframes_t);
extern sframes_t snd_pcm_mmap_commit(void*,uframes_t,uframes_t);
int main(void) {
 char buffer[256]={0};
 if(snd_pcm_hw_params(buffer,buffer))return 2;
 for(int i=0;i<10;i++) {
   if(snd_pcm_writei(buffer,buffer,512)!=512)return 3;
   if(snd_pcm_mmap_commit(buffer,0,256)!=256)return 4;
   usleep(220000);
 }
 return 0;
}
"""

def sample(path,stream=1,writes=2,frames=1024):
    lines=[]
    for i in range(10):
        t=(i+1)*200000000
        lines.append(f"T,{t},0,0,0,0,0,0,0,0,0\n")
        lines.append(f"S,{t},{stream},48000,2,512,1536,{i*writes},0,{i*frames},0\n")
    path.write_text("".join(lines),encoding="ascii")

class LifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.directory=Path(cls.tmp.name)
        for filename,source in (("fake.c",FAKE),("host.c",HOST)):
            (cls.directory/filename).write_text(source,encoding="ascii")
        cls.shim=cls.directory/"libmap02_alsa_lifetime.so"
        cls.host=cls.directory/"test-host"
        subprocess.run(["gcc","-std=c11","-O2","-fPIC","-shared",
                        "-Wall","-Wextra","-Werror","-pthread",
                        "-o",str(cls.shim),
                        str(ROOT/"tools"/"map02_alsa_lifetime_probe.c"),"-ldl"],
                       check=True,capture_output=True,text=True)
        subprocess.run(["gcc","-std=c11","-O2","-fPIC","-shared",
                        "-Wall","-Wextra","-Werror","-o",
                        str(cls.directory/"libfakealsa.so"),
                        str(cls.directory/"fake.c")],
                       check=True,capture_output=True,text=True)
        subprocess.run(["gcc","-std=c11","-O2","-D_DEFAULT_SOURCE",
                        "-Wall","-Wextra","-Werror",
                        "-o",str(cls.host),str(cls.directory/"host.c"),
                        "-L",str(cls.directory),"-lfakealsa",
                        "-Wl,-rpath,"+str(cls.directory)],
                       check=True,capture_output=True,text=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.tmp_one=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_one.cleanup)
        self.path=Path(self.tmp_one.name)/"trace.csv"

    def test_real_fake_alsa_summarizes_all_ten_transfers_beyond_256_cap(self):
        env=os.environ.copy()
        env["LD_PRELOAD"]=str(self.shim)
        env["VH_MAP02_ALSA_LIFETIME_PATH"]=str(self.path)
        subprocess.run([str(self.host)],env=env,timeout=10,check=True)
        parsed=parse(self.path)
        self.assertGreaterEqual(parsed["heartbeat_count"],8)
        self.assertGreater(parsed["observed_span_ms"],1000)
        streams=list(parsed["per_stream"].values())
        self.assertEqual(len(streams),1)
        self.assertEqual(streams[0]["format_class"],"48k_stereo")
        self.assertEqual(streams[0]["observed_write_calls"],10)
        self.assertEqual(streams[0]["observed_mmap_calls"],10)
        self.assertEqual(streams[0]["observed_positive_frames"],7680)
        self.assertFalse(parsed["direct_cpal_rust_callback_captured"])

    def test_no_opt_in_creates_no_file(self):
        env=os.environ.copy()
        env["LD_PRELOAD"]=str(self.shim)
        env.pop("VH_MAP02_ALSA_LIFETIME_PATH",None)
        subprocess.run([str(self.host)],env=env,timeout=10,check=True)
        self.assertFalse(self.path.exists())

    def test_generated_heartbeat_and_markers(self):
        sample(self.path)
        # The first input must have at least 500ms pre-input snapshots.
        r=parse(self.path,first_input_ns=800000000,
                last_observation_ns=1650000000)
        self.assertTrue(r["guest_input_markers_checked"])
        self.assertEqual(r["per_stream"]["1"]["sampled_first_last_delta_write_calls"],18)

    def test_missing_heartbeat(self):
        self.path.write_text("S,123,1,48000,2,512,1536,1,0,512,0\n")
        with self.assertRaisesRegex(ValueError,"matching heartbeat"):
            parse(self.path)

    def test_negative_cumulative_counter(self):
        sample(self.path)
        text=self.path.read_text().replace(
            "S,800000000,1,48000,2,512,1536,6,0,3072,0",
            "S,800000000,1,48000,2,512,1536,-1,0,3072,0")
        self.path.write_text(text)
        with self.assertRaisesRegex(ValueError,"Impossible ALSA"):
            parse(self.path)

    def test_decreasing_lifetime_counter(self):
        sample(self.path)
        text=self.path.read_text().replace(
            "S,800000000,1,48000,2,512,1536,6,0,3072,0",
            "S,800000000,1,48000,2,512,1536,0,0,3072,0")
        self.path.write_text(text)
        with self.assertRaisesRegex(ValueError,"Decreased counters"):
            parse(self.path)

    def test_missing_post_input_coverage(self):
        sample(self.path)
        with self.assertRaisesRegex(ValueError,"not bracketed"):
            parse(self.path,first_input_ns=400000000,
                  last_observation_ns=4000000000)

    def test_wrong_stream_class_does_not_claim_48k(self):
        sample(self.path)
        self.path.write_text(self.path.read_text().replace(",48000,2,512,1536,",
                                                           ",768000,32,32,96,"))
        result=parse(self.path)
        self.assertEqual(result["per_stream"]["1"]["format_class"],"other_or_unknown")

    def test_reject_giant_snapshot_gap(self):
        sample(self.path)
        self.path.write_text(self.path.read_text().replace(
            "T,1000000000,0,0,0,0,0,0,0,0,0",
            "T,9000000000,0,0,0,0,0,0,0,0,0"))
        with self.assertRaisesRegex(ValueError,"heartbeat|gap"):
            parse(self.path)

if __name__=="__main__":
    unittest.main()
