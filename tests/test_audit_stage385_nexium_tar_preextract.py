"""Synthetic TAR adversarial tests; no guest session or signed NeXium is claimed."""
import hashlib,io,json,os,sys,tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import audit_stage385_nexium_tar_preextract as m

def make_archive(entries):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w:gz') as t:
        for name,kind,value in entries:
            ti=tarfile.TarInfo(name)
            if kind=='file':
                dat=value;ti.size=len(dat);t.addfile(ti,io.BytesIO(dat))
            elif kind=='dir': ti.type=tarfile.DIRTYPE;t.addfile(ti)
            elif kind=='link': ti.type=tarfile.SYMTYPE;ti.linkname=value;t.addfile(ti)
            elif kind=='hardlink':ti.type=tarfile.LNKTYPE;ti.linkname=value;t.addfile(ti)
            elif kind=='fifo':ti.type=tarfile.FIFOTYPE;t.addfile(ti)
            else:raise ValueError(kind)
    return out.getvalue()

def manifest(blob,digest=True):
    return json.dumps({'id':123,'tag_name':'nightly','assets':[{
        'id':456,'name':m.ASSET,'state':'uploaded','size':len(blob),
        'digest':f'sha256:{hashlib.sha256(blob).hexdigest()}' if digest else None}]}).encode()

class ArchiveTests(TestCase):
    def setUp(self):
        self.blob=make_archive([('nexium-gui','file',b'fake-executable'),
                                ('lib','dir',b''),('lib/readme','file',b'data')])
    def test_normal_safe_tar_and_release_sha(self):
        out=m.audit(manifest(self.blob),self.blob)
        self.assertEqual(out['result'],m.RESULT)
        self.assertEqual((out['member_count'],out['regular_files']),(3,2))
        self.assertTrue(out['github_advertised_sha256_checked'])
        self.assertFalse(out['binary_authenticity_signed'])
    def test_missing_github_digest_is_observational_only(self):
        self.assertFalse(m.audit(manifest(self.blob,False),self.blob)['github_advertised_sha256_checked'])
    def test_mutated_bytes_wrong_hash_rejected(self):
        doc=json.loads(manifest(self.blob))
        doc['assets'][0]['digest']='sha256:'+'0'*64
        with self.assertRaises(m.UnsafeTarError):m.audit(json.dumps(doc).encode(),self.blob)
    def test_mismatched_asset_size_rejected(self):
        doc=json.loads(manifest(self.blob));doc['assets'][0]['size']+=1
        with self.assertRaises(m.UnsafeTarError):m.audit(json.dumps(doc).encode(),self.blob)
    def test_wrong_tag_duplicate_asset_missing_metadata_rejected(self):
        for variant in ('wrong_tag','duplicate','missing'):
            with self.subTest(variant=variant):
                doc=json.loads(manifest(self.blob))
                if variant=='wrong_tag':doc['tag_name']='stable'
                elif variant=='duplicate':doc['assets'].append(doc['assets'][0])
                else:doc['assets']=[]
                with self.assertRaises(m.UnsafeTarError):m.audit(json.dumps(doc).encode(),self.blob)
    def test_tarbomb_path_parent_and_absolute_rejected(self):
        for name in ('../escaping','/abs/escape','folder/../../escape','a//file','a/./file','foo\\bar'):
            with self.subTest(name=name):
                blob=make_archive([(name,'file',b'X')])
                with self.assertRaises(m.UnsafeTarError):m.audit(manifest(blob),blob)
    def test_gnu_tar_leading_dot_directory_supported(self):
        blob=make_archive([('./','dir',b''),('./nexium-gui','file',b'x'),
                           ('./runtime','dir',b''),('./runtime/lib','file',b'y')])
        got=m.audit(manifest(blob),blob)
        self.assertEqual((got['member_count'],got['regular_files']),(4,2))
    def test_normalized_duplicate_aliased_names_rejected(self):
        blob=make_archive([('./x','file',b'a'),('x','file',b'b')])
        with self.assertRaises(m.UnsafeTarError):m.audit(manifest(blob),blob)
    def test_symlink_to_parent_or_absolute_rejected(self):
        for target in ('../../etc/passwd','/etc/passwd','..','a\\b'):
            with self.subTest(target=target):
                blob=make_archive([('nested/link','link',target),('foo','file',b'x')])
                with self.assertRaises(m.UnsafeTarError):m.audit(manifest(blob),blob)
    def test_symlink_internal_valid_if_not_followed_by_tar_members(self):
        blob=make_archive([('shared/file','file',b'abc'),('lib/copy','link','../shared/file')])
        out=m.audit(manifest(blob),blob)
        self.assertEqual(out['symbolic_links'],1)
    def test_symlink_member_parent_rejected(self):
        blob=make_archive([('link','link','real'),('link/hijack','file',b'bytes'),('real','file',b'x')])
        with self.assertRaises(m.UnsafeTarError):m.audit(manifest(blob),blob)
    def test_symlink_declared_after_its_child_rejected(self):
        blob=make_archive([('link/hijack','file',b'bytes'),('link','link','real'),('real','file',b'x')])
        with self.assertRaises(m.UnsafeTarError):m.audit(manifest(blob),blob)
    def test_hardlink_target_must_be_original_regular_file(self):
        blob=make_archive([('file','file',b'abc'),('alias','hardlink','file')])
        self.assertEqual(m.audit(manifest(blob),blob)['regular_files'],1)
        for target in ('missing','../escape'):
            with self.subTest(target=target):
                b=make_archive([('file','file',b'abc'),('alias','hardlink',target)])
                with self.assertRaises(m.UnsafeTarError):m.audit(manifest(b),b)
    def test_symlink_chains_rejected(self):
        blob=make_archive([('real','file',b'abc'),('s1','link','real'),('s2','link','s1')])
        with self.assertRaises(m.UnsafeTarError):m.audit(manifest(blob),blob)
    def test_duplicate_tar_entry_rejected(self):
        blob=make_archive([('same','file',b'1'),('same','file',b'2')])
        with self.assertRaises(m.UnsafeTarError):m.audit(manifest(blob),blob)
    def test_device_fifo_rejected(self):
        blob=make_archive([('file','file',b'1'),('pipe','fifo',b'')])
        with self.assertRaises(m.UnsafeTarError):m.audit(manifest(blob),blob)
    def test_truncated_or_invalid_gzip_rejected(self):
        for blob in (b'abc',self.blob[:23]):
            with self.subTest(len=len(blob)),self.assertRaises(m.UnsafeTarError):m.audit(manifest(blob),blob)
    def test_cli_does_not_overwrite_existing_receipt(self):
        with TemporaryDirectory() as d:
            root=Path(d); rel=root/'release.json';arc=root/'archive.tar.gz'; rec=root/'receipt.json'
            rel.write_bytes(manifest(self.blob));arc.write_bytes(self.blob);rec.write_text('keep')
            self.assertEqual(m.main(['--release',str(rel),'--archive',str(arc),'--receipt',str(rec)]),2)
            self.assertEqual(rec.read_text(),'keep')
    def test_cli_reports_safe_preextract_rejection_reason(self):
        with TemporaryDirectory() as d:
            root=Path(d);release=root/'release.json';arc=root/'archive.tar.gz'
            receipt=root/'receipt.json'
            release.write_bytes(manifest(self.blob));arc.write_bytes(self.blob)
            receipt.write_text('immutable')
            stream=io.StringIO()
            with patch('sys.stderr',stream):
                exit_code=m.main(['--release',str(release),'--archive',str(arc),
                                  '--receipt',str(receipt)])
            self.assertEqual(exit_code,2)
            rejected=json.loads(stream.getvalue())
            self.assertEqual(rejected['validation_reason'],'refuse to overwrite pre-extract receipt')
            self.assertEqual(receipt.read_text(),'immutable')
    def test_symlink_input_rejected(self):
        with TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.write_bytes(self.blob)
            linked=root/'link';linked.symlink_to(source)
            with self.assertRaises(m.UnsafeTarError):m.data_from_file(linked,m.MAX_ARCHIVE)
