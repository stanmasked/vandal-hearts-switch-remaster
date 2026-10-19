"""Synthetic regressions for MAP02 immutable in-process receipt chain."""
import copy
from contextlib import ExitStack
import hashlib
import os
import sys
import unittest
from unittest.mock import patch
from tools import run_map02_sealed_gpu_receipt_chain as chain

@unittest.skipUnless(sys.platform == "linux", "Linux memfd required")
class ReceiptChainTests(unittest.TestCase):
    def setUp(self):
        self.a = {"schema":"vh.map02.sealed-gpu-make-objects.v1",
                  "objects_sha256":{"libgpu.o":"1"*64,"pc_raster.o":"2"*64},
                  "actual_make_children_kernel_attested":True,
                  "hd_replacement_authorized":False}
        self.b = {"schema":"vh.map02.sealed-linked-gpu-object.v1",
                  "source_objects_sha256":dict(self.a["objects_sha256"]),
                  "linked_object_sha256":"3"*64,
                  "binutils_consumed_sealed_objects":True,
                  "hd_replacement_authorized":False}
        self.c = {"schema":"vh.map02.sealed-linked-gpu-consumption.v1",
                  "source_objects_sha256":dict(self.a["objects_sha256"]),
                  "linked_object_sha256":"3"*64,
                  "linked_hash_verified_against_receipt":True,
                  "linked_bytes_sealed_before_binutils":True,
                  "hd_replacement_authorized":False}

    def run_mock(self, link_hook=None, inspect_hook=None):
        def make(*args, **kwargs):
            return copy.deepcopy(self.a)
        def link(pc, build, primary):
            if link_hook: link_hook(primary)
            return copy.deepcopy(self.b)
        def inspect(pc, build, primary, linked):
            if inspect_hook: inspect_hook(primary, linked)
            return copy.deepcopy(self.c)
        with patch.object(chain.primary_builder,"compile_overlay",side_effect=make),\
             patch.object(chain.linker,"verify_and_link",side_effect=link),\
             patch.object(chain.inspector,"verify_and_inspect",side_effect=inspect):
            return chain.run_chain("/tmp/synthetic-pc", "/tmp/synthetic-overlay",
                                   "/tmp/synthetic-manifest",build_dir="build-map02-fixture")

    def test_three_sealed_receipts_without_intermediate_files(self):
        x=self.run_mock()
        self.assertEqual(x["schema"],chain.SCHEMA)
        self.assertTrue(x["receipt_chain_consistent"])
        self.assertEqual(x["sealed_receipt_snapshots"],3)
        self.assertFalse(x["intermediate_receipt_files_written"])
        self.assertFalse(x["externally_authenticated"])
        for name in ("primary","linked","inspection"):
            self.assertEqual(x["receipt_sha256"][name],
                hashlib.sha256(chain._canonical(x[name])).hexdigest())

    def test_linker_mutates_received_copy_rejected(self):
        with self.assertRaisesRegex(ValueError,"primary receipt modified"):
            self.run_mock(link_hook=lambda a:a["objects_sha256"].update({"libgpu.o":"e"*64}))

    def test_inspector_mutates_received_linked_receipt_rejected(self):
        with self.assertRaisesRegex(ValueError,"receipt modified by inspection"):
            self.run_mock(inspect_hook=lambda a,b:b.update({"linked_object_sha256":"e"*64}))

    def test_replaced_both_later_object_hashes_rejected(self):
        self.b["source_objects_sha256"]["libgpu.o"]="a"*64
        self.c["source_objects_sha256"]["libgpu.o"]="a"*64
        with self.assertRaisesRegex(ValueError,"hashes inconsistent"):
            self.run_mock()

    def test_forged_linked_sha_rejected(self):
        self.c["linked_object_sha256"]="b"*64
        with self.assertRaisesRegex(ValueError,"hashes inconsistent"):
            self.run_mock()

    def test_missing_provenance_rejected(self):
        self.c["linked_bytes_sealed_before_binutils"]=False
        with self.assertRaisesRegex(ValueError,"provenance incomplete"):
            self.run_mock()

    def test_hd_enabled_rejected(self):
        self.b["hd_replacement_authorized"]=True
        with self.assertRaisesRegex(ValueError,"HD gate"):
            self.run_mock()

    def test_duplicate_keys_rejected(self):
        raw=b'{"a":1,"a":2}'
        with ExitStack() as stack:
            fd=chain.primary_builder._sealed_fd(raw,"duplicate-receipt")
            stack.callback(os.close,fd)
            with self.assertRaisesRegex(ValueError,"duplicate JSON"):
                chain._read_pin((fd,len(raw),hashlib.sha256(raw).hexdigest()))

    def test_unsealed_receipt_rejected(self):
        raw=b'{"a":1}'
        with ExitStack() as stack:
            fd=os.memfd_create("unsafe-receipt",flags=os.MFD_ALLOW_SEALING)
            stack.callback(os.close,fd)
            os.write(fd,raw)
            with self.assertRaisesRegex(ValueError,"not sealed"):
                chain._read_pin((fd,len(raw),hashlib.sha256(raw).hexdigest()))

if __name__=="__main__":
    unittest.main()
