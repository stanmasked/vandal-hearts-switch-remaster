"""Mutation tests for PC-port VRAM transfer ledger and fail-closed replay."""
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

import test_verify_map02_vram_timeline as timeline_fixture
from tools.export_map02_verified_vram_ledger import (
    HEADER, RECORD, export_verified_ledger, pack_verified_events,
)
from tools.verify_map02_gpu_write_ledger import (
    VRAM_BYTES, apply_transfer, audit_original_source,
    verify_write_ledger,
)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def word(vram,x,y,value):
    struct.pack_into("<H",vram,2*(y*1024+x),value)

def get(vram,x,y):
    return struct.unpack_from("<H",vram,2*(y*1024+x))[0]


class GpuWriteLedgerTests(unittest.TestCase):
    def setUp(self):
        self.base = timeline_fixture.Map02TimelineTests(
            methodName="test_two_original_source_keys_and_independent_changed_clut")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.root=self.base.root
        self.events=[
            {"step":0,"before_submission":1,"op":"clear",
             "rect":[0,0,1,1],"rgb":[160,136,32]},
            {"step":1,"before_submission":1,"op":"clear",
             "rect":[690,499,1,1],"rgb":[0,248,0]},
        ]
        self.write()

    def write(self):
        self.base.save()
        stream=b"".join((json.dumps(ev,sort_keys=True)+"\n").encode()
                        for ev in self.events)
        (self.root/"gpu-writes.jsonl").write_bytes(stream)
        (self.root/"write-ledger.json").write_text(json.dumps({
            "schema":"vh.map02.gpu.transfer-ledger.v1",
            "frame":self.base.frame,
            "pc_source_commit":timeline_fixture.fixture.PINNED_PC_SOURCE,
            "timeline_sha256":sha((self.root/"timeline.json").read_bytes()),
            "transfers_sha256":sha(stream),
        },sort_keys=True),encoding="utf-8")

    def test_private_packet_export_runs_full_ledger_verification(self):
        output = self.root / "private-transfers.bin"
        report = export_verified_ledger(self.root, output)
        raw = output.read_bytes()
        self.assertEqual(report["schema"], "vh.map02.transfer-packet.v1")
        self.assertEqual(report["packet_sha256"], sha(raw))
        self.assertEqual(report["gpu_transfer_events_replayed"], 2)
        self.assertFalse(report["pc_gameplay_authenticated"])
        self.assertEqual(
            HEADER.unpack_from(raw),
            (b"VHMAPGL1", self.base.frame, 2, 2, len(raw), bytes(8)))
        first = RECORD.unpack_from(raw, HEADER.size)
        second = RECORD.unpack_from(raw, HEADER.size + RECORD.size)
        self.assertEqual(first, (0,1,3,0,0,1,1,0,0,160,136,32,0))
        self.assertEqual(second, (1,1,3,690,499,1,1,0,0,0,248,0,0))
        self.assertEqual(len(raw), HEADER.size + 2 * RECORD.size)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            export_verified_ledger(self.root, output)

    def test_private_export_refuses_git_worktree_and_symlinked_parent(self):
        repository=self.root / "sample-git-repository"
        private=repository / "captures"
        private.mkdir(parents=True)
        (repository / ".git").mkdir()
        output=private / "sensitive-transfers.bin"
        with self.assertRaisesRegex(ValueError, "outside a Git worktree"):
            export_verified_ledger(self.root,output)
        self.assertFalse(output.exists())

        # A worktree may use a .git FILE rather than a directory.
        (repository / ".git").rmdir()
        (repository / ".git").write_text(
            "gitdir: /tmp/fake-worktree-meta",encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "outside a Git worktree"):
            export_verified_ledger(self.root,output)
        self.assertFalse(output.exists())

        link=self.root / "aliased-private-path"
        link.symlink_to(private, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "outside a Git worktree"):
            export_verified_ledger(self.root,link / "sensitive-transfers.bin")
        self.assertFalse(output.exists())

    def test_private_packet_export_rejects_unexplained_write(self):
        self.events = self.events[:1]
        self.write()
        output = self.root / "no-export.bin"
        with self.assertRaisesRegex(ValueError, "missing/rasterized GPU write"):
            export_verified_ledger(self.root, output)
        self.assertFalse(output.exists())

    def test_python_packet_roundtrips_through_compiled_c_decoder(self):
        output = self.root / "checked-transfers.bin"
        export_verified_ledger(self.root, output)
        packet = output.read_bytes()
        source = r"""
#include <stddef.h>
#include <stdint.h>
#include "map02_vram4_transfer_import.h"
int verify_packet(const uint8_t *buffer, size_t bytes,
                  uint32_t frame, size_t submissions) {
    VhMap02VramTransfer ev[4];
    size_t n = 777u;
    if (!vh_map02_vram_ledger_import_packet(
            buffer,bytes,frame,submissions,ev,4u,&n))
        return 0;
    return n == 2u &&
           ev[0].operation == VH_MAP02_VRAM_OP_CLEAR &&
           ev[0].x == 0 && ev[0].y == 0 &&
           ev[0].red == 160 && ev[0].green == 136 &&
           ev[1].before_submission == 1u &&
           ev[1].x == 690 && ev[1].y == 499 &&
           ev[1].green == 248 && ev[1].load_le == NULL;
}
"""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "packet.c").write_text(source, encoding="utf-8")
            include = Path(__file__).resolve().parent.parent / "source"
            compiled = subprocess.run(
                ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-O2", "-fPIC", "-shared", "-I", str(include),
                 str(root / "packet.c"), "-o", str(root / "packet.so")],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            library = ctypes.CDLL(str(root / "packet.so"))
            check = library.verify_packet
            check.argtypes = [ctypes.POINTER(ctypes.c_uint8),
                              ctypes.c_size_t, ctypes.c_uint32,
                              ctypes.c_size_t]
            check.restype = ctypes.c_int
            def call(raw):
                data = (ctypes.c_uint8 * len(raw)).from_buffer_copy(raw)
                return check(data,len(raw),self.base.frame,2)
            self.assertEqual(call(packet),1)
            altered = bytearray(packet)
            altered[0] = ord("!")
            self.assertEqual(call(altered),0)
            altered = bytearray(packet)
            altered[20] ^= 1
            self.assertEqual(call(altered),0)

    def test_private_packet_load_payload_is_canonical(self):
        payload = struct.pack("<HH", 0x001f, 0x03e0)
        events = [({
            "step": 0, "before_submission": 1, "op": "load",
            "rect": [-1, 0, 2, 1],
        }, payload)]
        data = pack_verified_events(42, 2, events)
        self.assertEqual(HEADER.unpack_from(data),
                         (b"VHMAPGL1", 42, 2, 1, len(data), bytes(8)))
        self.assertEqual(RECORD.unpack_from(data, HEADER.size),
                         (0,1,1,-1,0,2,1,0,0,0,0,0,4))
        self.assertEqual(data[-4:], payload)
        with self.assertRaisesRegex(ValueError, "payload"):
            pack_verified_events(42, 2, [(events[0][0], payload[:-1])])

    def test_clear_operations_account_for_all_vram_mutations(self):
        result=verify_write_ledger(self.root)
        self.assertEqual(result["snapshot_transitions_replayed"],1)
        self.assertEqual(result["load_image_events"],0)
        self.assertEqual(result["move_image_events"],0)
        self.assertEqual(result["clear_image_events"],2)
        self.assertEqual(result["changed_vram_words_explained"],2)
        self.assertEqual(result["vram_word_assignments"],2)
        self.assertEqual(result["changed_current_face_clut_words"],1)
        self.assertTrue(result["every_supplied_snapshot_matches_transfer_replay"])
        for flag in ("all_vram_writes_captured","rasterized_gpu_writes_modeled",
                     "pc_gameplay_authenticated","ps1_hardware_pixels_verified",
                     "raw_game_bytes_emitted"):
            self.assertFalse(result[flag])
        serialized=json.dumps(result)
        for secret in ("perimeter_xy","vertices","bgr555","raw_otz","rgb"):
            self.assertNotIn(secret,serialized)

    def test_load_image_payload_with_digest_and_clipping(self):
        self.events[1]={"step":1,"before_submission":1,"op":"load",
                        "rect":[690,499,1,1],
                        "payload_sha256":sha(struct.pack("<H",0x03e0))}
        (self.root/"load-0001.bin").write_bytes(struct.pack("<H",0x03e0))
        self.write()
        result=verify_write_ledger(self.root)
        self.assertEqual(result["load_image_events"],1)
        path=self.root/"load-0001.bin"
        path.write_bytes(b"\x00\x00")
        with self.assertRaisesRegex(ValueError,"SHA-256 mismatch"):
            verify_write_ledger(self.root)
        data=bytearray(VRAM_BYTES)
        payload=struct.pack("<HH",0x7c00,0x03e0)
        self.assertEqual(apply_transfer(data,{"op":"load","rect":[-1,0,2,1]},payload),1)
        self.assertEqual(get(data,0,0),0x03e0)

    def test_original_move_image_is_in_place_forward_not_memmove(self):
        # Overlap: moving three words one to the right repeats the first
        # source word across the destination in the real PC-port.
        start=bytearray(self.base.vrams[0])
        for x,c in zip((10,11,12,13),(0x001f,0x03e0,0x7c00,0)):
            word(start,x,12,c)
        target=bytearray(start)
        copy={"step":0,"before_submission":1,"op":"move",
              "rect":[10,12,3,1],"dest":[11,12]}
        self.assertEqual(apply_transfer(target,copy,None),3)
        self.assertEqual([get(target,x,12) for x in (10,11,12,13)],
                         [0x001f]*4)
        self.base.vrams=[bytes(start),bytes(target)]
        for probe in self.base.events[1]["texture"]["probes"]:
            probe["bgr555"]=0x7c00
        self.events=[copy]
        self.write()
        result=verify_write_ledger(self.root)
        self.assertEqual(result["move_image_events"],1)
        self.assertEqual(result["changed_vram_words_explained"],3)
        self.assertEqual(result["changed_current_face_clut_words"],0)

    def test_missing_transfer_cannot_be_silently_attributed_to_raster(self):
        self.events=self.events[:1]  # The changed CLUT has no explanation.
        self.write()
        with self.assertRaisesRegex(ValueError,"missing/rasterized GPU write"):
            verify_write_ledger(self.root)

    def test_unaccounted_texture_write_and_raster_write_rejected(self):
        self.events=self.events[:1]
        self.events[0]["rgb"]=[0,248,0] # changes a different color at (0,0)
        self.write()
        with self.assertRaisesRegex(ValueError,"VRAM differs"):
            verify_write_ledger(self.root)
        self.events[0]["rgb"]=[160,136,32]
        self.write()
        with self.assertRaisesRegex(ValueError,"VRAM differs"):
            verify_write_ledger(self.root)

    def test_source_audit_requires_true_pinned_git_blobs(self):
        with self.assertRaisesRegex(ValueError,"not the pinned revision"):
            audit_original_source(b"synthetic libgpu",b"synthetic raster")

    def test_invalid_payload_timeline_hash_and_event_order_refused(self):
        self.events[1]["before_submission"]=0
        self.write()
        with self.assertRaisesRegex(ValueError,"submission boundary"):
            verify_write_ledger(self.root)
        self.events[1]["before_submission"]=1
        self.events[1]["step"]=7
        self.write()
        with self.assertRaisesRegex(ValueError,"order is not contiguous"):
            verify_write_ledger(self.root)
        self.events[1]["step"]=1
        self.write()
        manifest=self.root/"write-ledger.json"
        m=json.loads(manifest.read_text())
        m["timeline_sha256"]="0"*64
        manifest.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,"timeline manifest: SHA-256 mismatch"):
            verify_write_ledger(self.root)

    def test_unsupported_write_ops_and_symlink_payload_rejected(self):
        self.events[1]["op"]="gp0-raster-quad"
        self.write()
        with self.assertRaisesRegex(ValueError,"unsupported transfer API"):
            verify_write_ledger(self.root)
        self.events[1]={"step":1,"before_submission":1,"op":"load",
                        "rect":[690,499,1,1],
                        "payload_sha256":sha(struct.pack("<H",0x03e0))}
        file=self.root/"load-0001.bin"
        file.symlink_to(self.root/"gpu-vram-000.bin")
        self.write()
        with self.assertRaisesRegex(ValueError,"missing, linked or non-regular"):
            verify_write_ledger(self.root)

    def test_clear_clip_and_bgr555_truncation(self):
        raw=bytearray(VRAM_BYTES)
        self.assertEqual(apply_transfer(raw,{"op":"clear",
             "rect":[-1,-1,3,3],"rgb":[255,128,8]},None),4)
        packed=(31)|((128>>3)<<5)|((8>>3)<<10)
        for x,y in ((0,0),(1,0),(0,1),(1,1)):
            self.assertEqual(get(raw,x,y),packed)
        self.assertEqual(get(raw,2,2),0)


if __name__=="__main__":
    unittest.main()
