import unittest
from tools.instrument_map02_putpixel_scope import scope_raster
from tools.instrument_map02_raster_skips import instrument_raster_skips
from tools.instrument_map02_dda_span import instrument_span, FLAG, prepare_span
from test_instrument_map02_raster_skips import FAKE

class SpanInstrumentationTests(unittest.TestCase):
    def test_one_exact_executed_span_hook(self):
        src = instrument_span(instrument_raster_skips(scope_raster(FAKE)))
        self.assertEqual(src.count("VH_Map02SpanObserve(cx, y, x_start, x_bound);"), 1)
        self.assertIn("cx->rc->target != 0", src)
        self.assertIn("y != vh_pixel_sample_y", src)
        self.assertIn("dda-native-spans.jsonl", src)
        self.assertIn("#error \"DDA span trace requires", src)
        self.assertIn("vh_map02_span_count >= VH_MAP02_SPAN_CAP", src)
        self.assertIn(FLAG, src)

    def test_pinned_generator_rejects_wrong_sources_and_overwrite(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            gpu, raster, dest = root/"gpu.c", root/"raster.c", root/"overlay"
            gpu.write_text("not pinned")
            raster.write_text(FAKE)
            with self.assertRaisesRegex(ValueError, "pinned original"):
                prepare_span(gpu, raster, dest)
            self.assertFalse(dest.exists())
            dest.mkdir()
            with self.assertRaisesRegex(ValueError, "refusing overwrite"):
                prepare_span(gpu, raster, dest)

    def test_failed_second_overlay_write_rolls_back(self):
        import tempfile
        from contextlib import ExitStack
        from pathlib import Path
        from unittest.mock import patch
        from tools.prepare_map02_pcport import git_blob_sha1

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            gpu, raster, dest = root / "libgpu.c", root / "pc_raster.c", root / "out"
            gpu.write_text("fake gpu")
            raster.write_text("fake raster")
            native_open = Path.open

            def reject_second(file, mode="r", *args, **kwargs):
                if file.name == "pc_raster.span.c" and mode == "x":
                    raise OSError("injected second-file write failure")
                return native_open(file, mode, *args, **kwargs)

            # Exercise publication/rollback with controlled input transforms;
            # do not mistake synthetic input for the pinned original GPU.
            with ExitStack() as stack:
                stack.enter_context(patch(
                    "tools.instrument_map02_putpixel_scope.GPU_BLOB",
                    git_blob_sha1(gpu.read_bytes())))
                stack.enter_context(patch(
                    "tools.instrument_map02_putpixel_scope.RASTER_BLOB",
                    git_blob_sha1(raster.read_bytes())))
                for symbol in (
                    "tools.instrument_map02_gpu_native_events.instrument",
                    "tools.instrument_map02_putpixel_scope.scope_gpu",
                    "tools.instrument_map02_putpixel_scope.scope_raster",
                    "tools.instrument_map02_raster_skips.instrument_raster_skips",
                    "tools.instrument_map02_vertical_dda.instrument_vertical",
                    "tools.instrument_map02_dda_span.instrument_span",
                ):
                    stack.enter_context(patch(symbol, side_effect=lambda src: src))
                stack.enter_context(patch.object(Path, "open", new=reject_second))
                with self.assertRaisesRegex(OSError, "injected second-file"):
                    prepare_span(gpu, raster, dest)
            self.assertFalse(dest.exists())
            self.assertTrue(gpu.exists())
            self.assertTrue(raster.exists())

    def test_partial_first_overlay_file_is_removed(self):
        import tempfile
        from contextlib import ExitStack
        from pathlib import Path
        from unittest.mock import patch
        from tools.prepare_map02_pcport import git_blob_sha1

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            gpu, raster, dest = root / "gpu.c", root / "raster.c", root / "out"
            gpu.write_text("sample gpu")
            raster.write_text("sample raster")
            real_open = Path.open

            class PartialWriter:
                def __init__(self, wrapped):
                    self.wrapped = wrapped
                def __enter__(self):
                    self.wrapped.__enter__()
                    return self
                def write(self, content):
                    self.wrapped.write(content[:3])
                    raise OSError("injected partial first-file write")
                def __exit__(self, *args):
                    return self.wrapped.__exit__(*args)

            def inject(file, mode="r", *args, **kwargs):
                stream = real_open(file, mode, *args, **kwargs)
                if file.name == "libgpu.span.c" and mode == "x":
                    return PartialWriter(stream)
                return stream

            with ExitStack() as stack:
                stack.enter_context(patch(
                    "tools.instrument_map02_putpixel_scope.GPU_BLOB",
                    git_blob_sha1(gpu.read_bytes())))
                stack.enter_context(patch(
                    "tools.instrument_map02_putpixel_scope.RASTER_BLOB",
                    git_blob_sha1(raster.read_bytes())))
                for symbol in (
                    "tools.instrument_map02_gpu_native_events.instrument",
                    "tools.instrument_map02_putpixel_scope.scope_gpu",
                    "tools.instrument_map02_putpixel_scope.scope_raster",
                    "tools.instrument_map02_raster_skips.instrument_raster_skips",
                    "tools.instrument_map02_vertical_dda.instrument_vertical",
                    "tools.instrument_map02_dda_span.instrument_span",
                ):
                    stack.enter_context(patch(symbol, side_effect=lambda src: src))
                stack.enter_context(patch.object(Path, "open", new=inject))
                with self.assertRaisesRegex(OSError, "injected partial first-file"):
                    prepare_span(gpu, raster, dest)
            self.assertFalse(dest.exists())
            self.assertEqual(gpu.read_text(), "sample gpu")
            self.assertEqual(raster.read_text(), "sample raster")

    def test_offline_cli_refuses_unpinned_inputs(self):
        import os
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            gpu, raster, dest = root/"gpu.c", root/"raster.c", root/"out"
            gpu.write_text("not original", encoding="utf-8")
            raster.write_text("not original", encoding="utf-8")
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
            run = subprocess.run(
                [sys.executable, "-m", "tools.instrument_map02_dda_span",
                 str(gpu), str(raster), "--output-dir", str(dest)],
                cwd=str(root), env=env, capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("pinned original PC GPU", run.stderr)
            self.assertFalse(dest.exists())

    def test_refuse_double_install(self):
        src = instrument_span(instrument_raster_skips(scope_raster(FAKE)))
        with self.assertRaisesRegex(ValueError, "already installed"):
            instrument_span(src)

    def test_refuse_unscoped_source(self):
        with self.assertRaisesRegex(ValueError, "requires existing"):
            instrument_span(FAKE)

    def test_refuse_missing_or_duplicate_anchor(self):
        src = instrument_raster_skips(scope_raster(FAKE))
        from tools.instrument_map02_raster_skips import SPAN_ANCHOR
        with self.assertRaises(ValueError): instrument_span(src.replace(SPAN_ANCHOR, "/* drift */"))
        with self.assertRaises(ValueError): instrument_span(src + SPAN_ANCHOR)

if __name__ == "__main__":
    unittest.main()
