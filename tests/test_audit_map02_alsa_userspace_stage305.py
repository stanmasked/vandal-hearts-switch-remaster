"""Stage305 generated-only falsifications: no fake real ALSA guest evidence."""
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_map02_alsa_userspace_stage305 import samples
from capture_map02_alsa_userspace_stage305 import (
    initialize,snapshot,MAGIC,SIZE,OPS,KINDS)

def fixture(ticks=24):
    header="kind,monotonic_ns,anonymous_alias,operation,total,success,eio,epipe,eagain,other_negative\n"
    rows=[]
    for tick in range(ticks):
        ns=8_000_000_000+tick*200_000_000
        rows.append(f"P,{ns},-1,sample,1,0,0,0,0,0\n")
        rows.append(f"S,{ns},0,avail_delay,{tick+1},{tick},1,0,0,0\n")
    return header+"".join(rows)

class UserspaceALSAStage305Tests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.path=self.root/"sanitized.csv"
        self.path.write_text(fixture())

    def audit(self,value):
        self.path.write_text(value)
        return samples(self.path)

    def test_bounded_source_shaped_success(self):
        r=samples(self.path)
        self.assertEqual(r["monotonic_sample_instants"],24)
        self.assertEqual(r["distinct_alsa_anonymous_tls_aliases"],1)
        self.assertEqual(r["per_symbol_final_return_class_counts"]["avail_delay"]["eio"],1)
        self.assertEqual(r["total_reported_alsa_function_entries"],24)

    def test_counter_mmap_header_and_size(self):
        p=self.root/"private.bin"
        initialize(p)
        self.assertEqual(p.stat().st_size,SIZE)
        self.assertEqual(p.read_bytes()[:8],MAGIC)
        with p.open("r+b") as f:
            import mmap
            with mmap.mmap(f.fileno(),SIZE) as mm:
                n,rows=snapshot(mm)
                self.assertEqual((n,rows),(0,[]))

    def test_prevent_private_overwrite(self):
        p=self.root/"private.bin"
        initialize(p)
        with self.assertRaises(FileExistsError):initialize(p)

    def test_reject_time_reversal(self):
        self.assertRaisesRegex(ValueError,"unordered",self.audit,
            fixture().replace("8400000000","8100000000",1))

    def test_reject_counter_regression(self):
        old="S,8400000000,0,avail_delay,3,2,1,0,0,0"
        new="S,8400000000,0,avail_delay,1,0,1,0,0,0"
        self.assertRaisesRegex(ValueError,"regressed",self.audit,
            fixture().replace(old,new))

    def test_reject_more_classes_than_total(self):
        self.assertRaisesRegex(ValueError,"classification",self.audit,
            fixture().replace("S,8000000000,0,avail_delay,1,0,1,0,0,0",
                              "S,8000000000,0,avail_delay,1,0,2,0,0,0"))

    def test_reject_raw_linux_thread_id_instead_of_anonymous_alias(self):
        self.assertRaisesRegex(ValueError,"thread alias",self.audit,
            fixture().replace(",0,avail_delay,",",12345,avail_delay,",1))

    def test_reject_unknown_symbol(self):
        self.assertRaisesRegex(ValueError,"operation",self.audit,
            fixture().replace(",avail_delay,",",snd_pcm_secret,",1))

    def test_reject_duplicate_sample(self):
        rows=fixture().splitlines()
        rows.insert(3,rows[2])
        self.assertRaisesRegex(ValueError,"Duplicate",self.audit,"\n".join(rows)+"\n")

    def test_reject_too_few_samples(self):
        self.assertRaisesRegex(ValueError,"Too few",self.audit,fixture(4))

    def test_reject_csv_schema(self):
        self.assertRaisesRegex(ValueError,"header",self.audit,
            fixture().replace("anonymous_alias","thread_pid",1))

    def test_reject_symlink_evidence(self):
        link=self.root/"fake.csv"
        link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError,"missing"):samples(link)

    def test_operation_allowlist_unique(self):
        self.assertEqual(len(OPS),9)
        self.assertEqual(len(set(OPS)),9)
        self.assertEqual(len(KINDS),6)

if __name__=="__main__":unittest.main()
