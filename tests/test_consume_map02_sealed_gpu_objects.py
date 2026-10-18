"""Asset-free checks of immutable MAP02 GPU object consumption."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import consume_map02_sealed_gpu_objects as consumer


@unittest.skipUnless(sys.platform == "linux" and all(
    shutil.which(name) for name in ("gcc", "ld", "nm", "strings")),
    "Linux memfd and GCC/binutils required")
class SealedObjectConsumerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-map02-object-consumer-")
        self.addCleanup(self.tmp.cleanup)
        self.pc = Path(self.tmp.name)
        self.folder = self.pc / "build-map02-consumer"
        self.folder.mkdir()
        (self.folder / "libgpu.c").write_text(
            "void VH_CaptureEvent(void){}\n"
            "void VH_Map02PixelScopeSet(void){}\n"
            "void VH_Map02PixelScopeClear(void){}\n")
        (self.folder / "pc_raster.c").write_text(
            "void VH_PixelSampleRecord(void){}\n"
            "void VH_Map02SkipAt(void){}\n"
            "void VH_Map02SpanObserve(void){}\n"
            "const char *markers[]={\"VH_MAP02_PUTPIXEL_X2\","
            "\"VH_MAP02_PUTPIXEL_Y2\"};\n")
        for unit in ("libgpu", "pc_raster"):
            subprocess.run(["gcc", "-c", str(self.folder / (unit + ".c")),
                            "-o", str(self.folder / (unit + ".o"))], check=True)
        self.receipt = {
            "schema": "vh.map02.sealed-gpu-make-objects.v1",
            "objects_sha256": {
                name: hashlib.sha256((self.folder / name).read_bytes()).hexdigest()
                for name in consumer.OBJECT_NAMES},
            "actual_make_children_kernel_attested": True,
            "kernel_make_primary_executables_match_sha256": True,
            "compiled_from_sealed_preprocessor_output": True,
            "hd_replacement_authorized": False,
        }

    def consume(self):
        return consumer.verify_and_link(self.pc, "build-map02-consumer", self.receipt)

    def test_receipt_verified_and_linked_from_sealed_descriptors(self):
        result = self.consume()
        self.assertEqual(result["sealed_object_inputs"], 2)
        self.assertTrue(result["binutils_consumed_sealed_objects"])
        self.assertEqual(result["source_objects_sha256"], self.receipt["objects_sha256"])
        linked = self.folder / consumer.LINKED_NAME
        self.assertEqual(hashlib.sha256(linked.read_bytes()).hexdigest(),
                         result["linked_object_sha256"])

    def test_modified_object_refused_without_tool_execution(self):
        path = self.folder / "pc_raster.o"
        path.write_bytes(path.read_bytes() + b"modified")
        with patch.object(consumer, "_run_binary") as command:
            with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
                self.consume()
            command.assert_not_called()
        self.assertFalse((self.folder / consumer.LINKED_NAME).exists())

    def test_symlinked_compiled_object_refused(self):
        path = self.folder / "libgpu.o"
        other = self.folder / "replacement"
        path.rename(other)
        path.symlink_to(other)
        with self.assertRaises((OSError, ValueError)):
            self.consume()

    def test_false_kernel_provenance_refused(self):
        self.receipt["actual_make_children_kernel_attested"] = False
        with self.assertRaisesRegex(ValueError, "provenance not confirmed"):
            self.consume()

    def test_source_swap_after_memfd_seal_cannot_affect_link(self):
        actual = consumer._run_binary
        mutations = []
        def mutate(tool, *args, **kwargs):
            if tool == "nm":
                (self.folder / "libgpu.o").write_bytes(b"not an ELF")
                mutations.append(True)
            return actual(tool, *args, **kwargs)
        with patch.object(consumer, "_run_binary", side_effect=mutate):
            report = self.consume()
        self.assertTrue(mutations)
        self.assertTrue(report["binutils_consumed_sealed_objects"])
        self.assertEqual((self.folder / consumer.LINKED_NAME).read_bytes()[:4],
                         b"\x7fELF")

    def test_link_output_cannot_overwrite_existing_target(self):
        target = self.folder / consumer.LINKED_NAME
        target.write_text("keep")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.consume()
        self.assertEqual(target.read_text(), "keep")

    def test_missing_required_symbol_refuses_publication(self):
        source = self.folder / "libgpu.c"
        source.write_text("int unrelated_symbol(void){return 5;}\n")
        subprocess.run(["gcc", "-c", str(source), "-o",
                        str(self.folder / "libgpu.o")], check=True)
        self.receipt["objects_sha256"]["libgpu.o"] = hashlib.sha256(
            (self.folder / "libgpu.o").read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "required GPU symbol absent"):
            self.consume()
        self.assertFalse((self.folder / consumer.LINKED_NAME).exists())


if __name__ == "__main__":
    unittest.main()
