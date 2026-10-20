"""ROM-free host ALSA preload test, synthetic libasound ABI and fake samples.

No NeXium, Nintendo Switch, ROM, licensed PCM, PulseAudio or ALSA packages.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from audit_map02_alsa_host_trace import parse

FAKE_C=r"""
/* Fake Linux x86_64 ALSA ABI, intentionally no real hardware or game audio. */
typedef unsigned long uframes_t;
typedef long sframes_t;
int snd_pcm_hw_params(void *p, void *q) {(void)p;(void)q;return 0;}
int snd_pcm_hw_params_get_channels(const void *p, unsigned *v)
  {(void)p; *v=2; return 0;}
int snd_pcm_hw_params_get_rate(const void *p, unsigned *v, int *d)
  {(void)p;(void)d;*v=48000;return 0;}
int snd_pcm_hw_params_get_buffer_size(const void *p, uframes_t *v)
  {(void)p;*v=2048;return 0;}
int snd_pcm_hw_params_get_period_size(const void *p, uframes_t *v, int *d)
  {(void)p;(void)d;*v=512;return 0;}
sframes_t snd_pcm_writei(void *pcm, const void *src, uframes_t n)
  {(void)pcm;(void)src;return (sframes_t)n;}
sframes_t snd_pcm_mmap_commit(void *pcm, uframes_t offset, uframes_t n)
  {(void)pcm;(void)offset;return (sframes_t)n;}
"""
HOST_C=r"""
typedef unsigned long uframes_t;
typedef long sframes_t;
extern int snd_pcm_hw_params(void *,void *);
extern sframes_t snd_pcm_writei(void *,const void *,uframes_t);
extern sframes_t snd_pcm_mmap_commit(void *,uframes_t,uframes_t);
int main(void) {
  char fake_pcm[64]={0};
  if(snd_pcm_hw_params(fake_pcm,fake_pcm))return 5;
  if(snd_pcm_writei(fake_pcm,fake_pcm,512)!=512)return 6;
  if(snd_pcm_mmap_commit(fake_pcm,0,256)!=256)return 7;
  return 0;
}
"""


class Map02HostAlsaProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.work=Path(cls.temp.name)
        paths={"fake":(cls.work/"fake.c",FAKE_C),
               "host":(cls.work/"host.c",HOST_C)}
        for path,src in paths.values():
            path.write_text(src,encoding="ascii")
        cls.shim=cls.work/"libmap02_alsa_trace.so"
        cls.fake=cls.work/"libfakeasound.so"
        cls.host=cls.work/"alsa-test-host"
        subprocess.run(["gcc","-std=c11","-O2","-fPIC","-shared",
                        "-Wall","-Wextra","-Werror",
                        "-o",str(cls.shim),
                        str(ROOT/"tools"/"map02_alsa_host_trace.c"),"-ldl"],
                       check=True,capture_output=True,text=True)
        subprocess.run(["gcc","-std=c11","-O2","-fPIC","-shared",
                        "-Wall","-Wextra","-Werror",
                        "-o",str(cls.fake),str(paths["fake"][0])],
                       check=True,capture_output=True,text=True)
        subprocess.run(["gcc","-std=c11","-O2","-Wall","-Wextra","-Werror",
                        "-o",str(cls.host),str(paths["host"][0]),
                        "-L",str(cls.work),"-lfakeasound",
                        "-Wl,-rpath,"+str(cls.work)],
                       check=True,capture_output=True,text=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.file=self.work/(self.id().rsplit(".",1)[-1]+".csv")

    def test_ld_preload_real_abi_delegation_and_host_probe(self):
        env=os.environ.copy()
        env["LD_PRELOAD"]=str(self.shim)
        env["VH_MAP02_ALSA_TRACE_PATH"]=str(self.file)
        subprocess.run([str(self.host)],env=env,check=True,timeout=10)
        r=parse(self.file)
        self.assertEqual(r["result"],"OBSERVED_ALSA_HW_PARAMS_AND_TRANSFER_CALLS")
        self.assertEqual(r["record_count"],3)
        self.assertEqual(r["valid_48k_stereo_hw_params_count"],1)
        self.assertEqual(r["transfer_call_count"],2)
        self.assertEqual(r["positive_frame_transfer_count"],2)
        self.assertEqual(r["period_frames_values"],[512])
        self.assertEqual(r["buffer_frames_values"],[2048])
        self.assertEqual(r["transfer_kinds"],["MMAP_COMMIT","WRITEI"])
        self.assertEqual(r["other_successful_alsa_hw_params_count"],0)
        self.assertFalse(r["transfer_calls_directly_attributed_to_48k_pcm"])
        self.assertFalse(r["rust_cpal_callback_period_proven"])
        self.assertFalse(r["guest_audout_service_deadlock_proven"])
        self.assertFalse(r["physical_switch_audio_proven"])
        self.assertFalse(r["raw_audio_data_collected"])

    def test_opt_in_absence_records_no_trace(self):
        env=os.environ.copy()
        env["LD_PRELOAD"]=str(self.shim)
        env.pop("VH_MAP02_ALSA_TRACE_PATH",None)
        subprocess.run([str(self.host)],env=env,check=True,timeout=10)
        self.assertFalse(self.file.exists())

    def test_zero_event_trace_rejected(self):
        self.file.write_text("")
        with self.assertRaisesRegex(ValueError,"No host ALSA evidence"):
            parse(self.file)

    def test_ambiguous_invalid_event_rejected(self):
        self.file.write_text("CPAL_CALLBACK,1,2,3,4,5,6,7,8,9\n")
        with self.assertRaisesRegex(ValueError,"Invalid ALSA event"):
            parse(self.file)

    def test_missing_fields_rejected(self):
        self.file.write_text("HW_PARAMS,1,2,3\n")
        with self.assertRaisesRegex(ValueError,"Invalid ALSA event"):
            parse(self.file)

    def test_negative_duration_rejected(self):
        self.file.write_text("HW_PARAMS,22,21,123,0,0,48000,2,512,2048\n")
        with self.assertRaisesRegex(ValueError,"Impossible ALSA"):
            parse(self.file)

    def test_no_transfer_does_not_claim_callback(self):
        self.file.write_text("HW_PARAMS,10,11,123,0,0,48000,2,512,2048\n")
        with self.assertRaisesRegex(ValueError,"No ALSA write"):
            parse(self.file)

    def test_invalid_buffer_geometry_rejected(self):
        self.file.write_text(
            "HW_PARAMS,10,11,123,0,0,48000,2,2048,512\n"
            "WRITEI,12,13,123,512,512,0,0,0,0\n")
        with self.assertRaisesRegex(ValueError,"Target 48k stereo"):
            parse(self.file)

    def test_overreturned_transfer_rejected(self):
        self.file.write_text(
            "HW_PARAMS,10,11,123,0,0,48000,2,512,2048\n"
            "WRITEI,12,13,123,512,513,0,0,0,0\n")
        with self.assertRaisesRegex(ValueError,"more frames"):
            parse(self.file)

    def test_secondary_768k_32ch_alsa_config_not_mislabeled_as_guest_output(self):
        # Found in live NeXium, with *different* ALSA PCM parameters.
        self.file.write_text(
            "HW_PARAMS,10,11,123,0,0,48000,2,512,1536\n"
            "HW_PARAMS,12,13,124,0,0,768000,32,32,32768\n"
            "HW_PARAMS,14,15,124,0,0,768000,32,32,96\n"
            "WRITEI,16,17,125,512,512,0,0,0,0\n")
        report=parse(self.file)
        self.assertEqual(report["period_frames_values"],[512])
        self.assertEqual(report["buffer_frames_values"],[1536])
        self.assertEqual(report["other_successful_alsa_hw_params_count"],2)
        self.assertEqual(report["other_alsa_hw_configurations"],[
            {"rate_hz":768000,"channels":32,"period_frames":32,
             "buffer_frames":96},
            {"rate_hz":768000,"channels":32,"period_frames":32,
             "buffer_frames":32768}])
        self.assertFalse(report["transfer_calls_directly_attributed_to_48k_pcm"])

    def test_hard_upper_bound_event_records(self):
        self.file.write_text(
            "HW_PARAMS,10,11,123,0,0,48000,2,512,2048\n" * 257)
        with self.assertRaisesRegex(ValueError,"Unbounded ALSA trace"):
            parse(self.file)


if __name__=="__main__":
    unittest.main()
