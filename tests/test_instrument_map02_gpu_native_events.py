"""Pinned-source mutation and opt-in GPU capture injection tests."""
import unittest
from tools.instrument_map02_gpu_native_events import ANCHORS, GUARD, instrument

def minimal_source():
    return r'''
#define VRAM_H 512
unsigned s_drawFrame=0;
static int s_twMaskX=0,s_twMaskY=0,s_twOffX=0,s_twOffY=0;
static int s_drawModeTPage=0,s_drawModeAbr=0,s_drawModeDither=0;
/* ---- GetTPage / GetClut (psx-spx "Texpage Attribute" / "Clut Attribute") */
int LoadImage(RECT *rect,unsigned int *p) {
    unsigned short *src=(unsigned short*)p;
    PC_LangPatchFwdUpload(rect->x,rect->y,rect->w,rect->h,src);
    if (rect->w > 0 && rect->h > 0) TrcWrite('L', rect, 8, src, (u32)(rect->w * rect->h * 2));
    for (y = y0; y < y1; y++) foo();
    for (x = x0; x < x1; x++) foo();
    HiresMirrorRect(rect->x, rect->y, rect->w, rect->h);   /* keep the hi-res FB in sync (backgrounds) */
}
int MoveImage(RECT *rect,int x,int y) {
    { int xy[2]; xy[0] = x; xy[1] = y; TrcWrite('M', rect, 8, xy, 8); }
    for (j = 0; j < rect->h; j++)
      for (i = 0; i < rect->w; i++)
        vram[dy][dx] = vram[sy][sx];
    HiresMirrorRect(x, y, rect->w, rect->h);   /* keep the hi-res FB in sync (VRAM->VRAM blit) */
}
int ClearImage(RECT *rect, u_char r,u_char g,u_char b) {
    { unsigned char rgb[3]; rgb[0] = r; rgb[1] = g; rgb[2] = b; TrcWrite('C', rect, 8, rgb, 3); }
    FillRectRaw(rect->x, rect->y, rect->w, rect->h, r, g, b);
}
void DrawOTag(unsigned int *p) {
    if (!isBucket) {
        int type = PC_GPU_PRIM_TYPE((P_TAG*)cur);
        int semi = 0;
            switch (type) {
            default:
                break;
            }
        }
        nextTok = rawTagOfCur;
    TrcFrameEnd();
}
'''

class NativeGpuProbeTests(unittest.TestCase):
    def test_every_source_backed_hook_injected(self):
        rendered=instrument(minimal_source())
        self.assertEqual(rendered.count('VH_CaptureEvent("before"'),4)
        self.assertEqual(rendered.count('VH_CaptureEvent("after"'),4)
        self.assertIn('PC_GPU_PRIM_POLY_FT4 ? (POLY_FT4 *)cur',rendered)
        self.assertEqual(rendered.count('type == PC_GPU_PRIM_POLY_FT4 ? (POLY_FT4 *)cur : NULL'),2)
        self.assertIn('s_drawModeTPage, s_drawModeAbr, s_drawModeDither',rendered)
        self.assertIn('vh_capture_seq >= VH_CAPTURE_LIMIT',rendered)
        self.assertIn('getenv("VH_MAP02_GPU_CAPTURE_DIR")',rendered)
        self.assertIn('getenv("VH_MAP02_GPU_CAPTURE_FRAME")',rendered)
        self.assertIn('if (!vh_capture_frame',rendered)
        self.assertIn('PC_GpuVramBytes(&bytes)',rendered)
        self.assertEqual(rendered.count('#if defined(VH_MAP02_GPU_CAPTURE)'),10)
        self.assertIn('type == PC_GPU_PRIM_DR_MODE', rendered)
        self.assertEqual(rendered.count('type == PC_GPU_PRIM_DR_MODE'), 2)
        self.assertIn('VH_CaptureFinish(s_drawFrame, nextTok == 0)', rendered)
        self.assertIn('gpu-native-capture-status.json', rendered)
        self.assertIn('observed_window_closed_without_detected_loss', rendered)
        self.assertIn('s_drawEnv.clip.x, s_drawEnv.clip.y', rendered)
        self.assertIn('s_drawEnv.clip.w, s_drawEnv.clip.h', rendered)
        self.assertIn('s_drawEnv.ofs[0], s_drawEnv.ofs[1]', rendered)
        self.assertIn('draw_env', rendered)
        self.assertIn('vh_capture_seen < 0xffffffffUL', rendered)
        self.assertIn('fwrite(vram, 1u, bytes, file)',rendered)
        self.assertIn('ft4',rendered)

    def test_native_loadimage_upload_limit_is_per_dimension(self):
        # Keep the offline validator's mandatory-payload rule aligned
        # with the actual source-pinned C observer's after-hook.
        rendered=instrument(minimal_source())
        self.assertIn('rect->w > 0 && rect->h > 0 && rect->w <= 128 && rect->h <= 128',rendered)
        self.assertIn('(size_t)rect->w*(size_t)rect->h : 0u',rendered)
        self.assertIn('if (upload && upload_words > 0u && upload_words <= 16384u)',rendered)
        self.assertIn('fwrite(upload, sizeof(unsigned short), upload_words, file)',rendered)

    def test_two_window_loadimage_filename_uses_local_record_index(self):
        # At global step 65 the recorder has local step 1 in window-001.
        # Native JSONL and VRAM snapshot names are already local, so the
        # upload must NOT be called gpu-0065-upload.bin.
        rendered = instrument(minimal_source())
        self.assertIn('local_seq = seq % VH_CAPTURE_LIMIT;', rendered)
        self.assertIn('"gpu-%04u-vram.bin", local_seq', rendered)
        self.assertIn('"gpu-%04u-upload.bin", local_seq', rendered)
        self.assertIn('local_seq, s_drawFrame, phase, operation, snapshot_name', rendered)
        self.assertNotIn('"gpu-%04u-upload.bin", seq', rendered)
        self.assertIn('VH_MAP02_GPU_CAPTURE_WINDOW_COUNT', rendered)
        self.assertIn('gpu-native-window-index.json', rendered)

    def test_private_window_file_writer_ignores_permissive_umask(self):
        rendered = instrument(minimal_source())
        self.assertIn('VH_CapturePrivateWindowFile(snapshot_path, 0)', rendered)
        self.assertIn('VH_CapturePrivateWindowFile(upload_path, 0)', rendered)
        self.assertIn('VH_CapturePrivateWindowFile(log_path, 1)', rendered)
        self.assertIn('VH_CapturePrivateWindowFile(status_path, 0)', rendered)
        self.assertIn('O_NOFOLLOW | O_CLOEXEC', rendered)
        self.assertIn('open(path, flags, 0600)', rendered)
        self.assertIn('st.st_nlink != 1', rendered)
        # The standalone legacy observer and combined joint probe
        # retain their original compile-time guarded call-site anchors.
        self.assertEqual(rendered.count('file = fopen(status_path, "wx");'), 2)

    def test_injection_is_fail_closed_and_unique(self):
        once=instrument(minimal_source())
        with self.assertRaisesRegex(ValueError,'already instrumented'):
            instrument(once)
        for label, anchor in ANCHORS.items():
            if label=='helpers':
                continue
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError,'expected one pinned source anchor'):
                    instrument(minimal_source().replace(anchor,'/* removed */'))
        with self.assertRaisesRegex(ValueError,'capture helpers'):
            instrument(minimal_source().replace(
                '/* ---- GetTPage / GetClut (psx-spx "Texpage Attribute" / "Clut Attribute") */',
                '/* wrong pinned source */'))

    def test_no_leaking_runtime_capture_into_baseline(self):
        source=instrument(minimal_source())
        # Every callsite and helper exists exclusively inside #if guards.
        lines=source.splitlines()
        for i,line in enumerate(lines):
            if 'VH_CaptureEvent("before"' in line or 'VH_CaptureEvent("after"' in line:
                nearest='\n'.join(lines[max(0,i-3):i+1])
                self.assertIn('#if defined(VH_MAP02_GPU_CAPTURE)',nearest)

if __name__=='__main__':
    unittest.main()
