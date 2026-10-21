"""Stage303 synthetic-only falsifications for raw strace and clock bridge.

Positive tests validate a parser shape only; do not claim actual NeXium traces.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_alsa_syscalls_stage303 import clockbridge,parse_raw_strace,TRACE_RE

CLOCK_OFFSET=1_790_000_000_000_000_000
GUEST_INPUT=100_000_000_000
GUEST_LAST=110_000_000_000

def line(seconds,syscall,text):
    return f"{seconds:.6f} {syscall}({text}\n"

class Stage303SyscallTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.raw=self.root/"raw-strace-private.txt"
        before={
            "offset_low_ns":CLOCK_OFFSET-1000,
            "offset_high_ns":CLOCK_OFFSET+1000,
            "paired_wall_uncertainty_ns":2000,
            "pair_monotonic_ns":95_000_000_000,
        }
        self.before=before
        self.after=dict(before,pair_monotonic_ns=115_000_000_000)
        self.lines=[
          f"[pid 100] 1790000102.000001 ioctl(3, SNDRV_PCM_IOCTL_STATUS, {{...}}) = -1 EIO (Input/output error)\n",
          f"[pid 101] 1790000102.000050 ioctl(4, DRM_IOCTL_SYNCOBJ, {{...}}) = 0\n",
          f"[pid 101] 1790000102.001000 ppoll([], 0, NULL, NULL, 8) = 0\n",
        ]+[f"[pid 101] 1790000102.{2000+i:06d} poll([], 0, 0) = 0\n" for i in range(8)]
        self.raw.write_text("".join(self.lines))

    def test_bounded_strace_recognizes_kernel_alsa_pcm_ioctl_and_eio(self):
        r=parse_raw_strace(self.raw,self.before,self.after,GUEST_INPUT,GUEST_LAST)
        self.assertEqual(r["selected_syscall_counts"]["ioctl"],2)
        self.assertEqual(r["selected_syscall_counts"]["poll"],8)
        self.assertEqual(r["selected_error_code_counts"]["EIO"],1)
        self.assertEqual(r["audio_kernel_ioctl_categories"]["recognized_kernel_alsa_pcm_ioctl"],1)
        self.assertEqual(r["audio_kernel_ioctl_categories"]["recognized_kernel_alsa_pcm_ioctl_error"],1)
        self.assertFalse(r["raw_trace_is_uploaded"])

    def test_pid_prefix_and_no_pid_regex(self):
        self.assertIsNotNone(TRACE_RE.search(self.lines[0]))
        self.assertIsNotNone(TRACE_RE.search("1790000102.000001 poll([], 0, 0) = 0"))
        self.assertIsNotNone(TRACE_RE.search("1790000102.000001 [pid 42] poll([], 0, 0) = 0"))
        self.assertIsNotNone(TRACE_RE.search("42 1790000102.000001 poll([], 0, 0) = 0"))

    def test_missing_alsa_ioctl_is_not_a_false_cause(self):
        s=self.raw.read_text().replace("SNDRV_PCM_IOCTL_STATUS","DRM_IOCTL_VERSION")
        self.raw.write_text(s)
        r=parse_raw_strace(self.raw,self.before,self.after,GUEST_INPUT,GUEST_LAST)
        self.assertNotIn("recognized_kernel_alsa_pcm_ioctl",r["audio_kernel_ioctl_categories"])
        self.assertEqual(r["selected_error_code_counts"]["EIO"],1)

    def test_unknown_syscall_lines_are_not_interpreted_as_audio(self):
        self.raw.write_text(self.raw.read_text()+"[pid 101] 1790000103.1 write(1, \"secret\", 6) = 6\n")
        r=parse_raw_strace(self.raw,self.before,self.after,GUEST_INPUT,GUEST_LAST)
        self.assertEqual(r["raw_trace_unparsed_lines"],1)

    def test_bounded_realtime_does_not_assert_exact_alsa_clock(self):
        r=parse_raw_strace(self.raw,self.before,self.after,GUEST_INPUT,GUEST_LAST)
        self.assertTrue(r["approximate_guest_window_syscall_counts"])
        self.assertTrue(all("WELL_INSIDE_GUEST_WINDOW" in k
                            for k in r["approximate_guest_window_syscall_counts"]))

    def test_reject_strace_missing_rows(self):
        self.raw.write_text("1790000102.000001 ioctl(3, DRM_IOCTL_VERSION) = 0\n")
        with self.assertRaisesRegex(ValueError,"No useful"):
            parse_raw_strace(self.raw,self.before,self.after,GUEST_INPUT,GUEST_LAST)

    def test_clock_bridge_bounded_uncertainty(self):
        path=self.root/"clock.json"
        path.write_text(json.dumps({
          "wall_before_ns":CLOCK_OFFSET+1000,
          "monotonic_ns":1000,
          "wall_after_ns":CLOCK_OFFSET+3000}))
        r=clockbridge(path)
        self.assertEqual(r["offset_low_ns"],CLOCK_OFFSET)

    def test_reject_clock_bridge_bad_skew(self):
        p=self.root/"clock.json"
        p.write_text(json.dumps({
            "wall_before_ns":CLOCK_OFFSET,
            "monotonic_ns":100,
            "wall_after_ns":CLOCK_OFFSET+60_000_000}))
        with self.assertRaisesRegex(ValueError,"uncertainty"):
            clockbridge(p)

    def test_raw_trace_symlink_refused(self):
        link=self.root/"symlink.txt";link.symlink_to(self.raw)
        with self.assertRaisesRegex(ValueError,"missing"):
            parse_raw_strace(link,self.before,self.after,GUEST_INPUT,GUEST_LAST)

    def test_reject_wall_clock_regression(self):
        self.raw.write_text(self.raw.read_text()+"1790000099.000000 poll([], 0, 0) = 0\n")
        with self.assertRaisesRegex(ValueError,"regressed"):
            parse_raw_strace(self.raw,self.before,self.after,GUEST_INPUT,GUEST_LAST)

if __name__=="__main__":
    unittest.main()
