#!/usr/bin/env python3
"""v122 PS1 MIPS CPU -> RAM -> DMA2 -> native Unai return provenance."""
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from tools.make_map02_v122_mips_dma2_gp0_exe import (
    MAGIC,SECTION_SIZE,HEADER_SIZE,MARKERS,MARKER_ADDR,PACKET_ADDR,
    DMA2_MADR,DMA2_BCR,DMA2_CHCR,DMA2_DPCR,
    COLORS,RECT_XY,RECT_SIZE,SETUP,EXPECTED_PIXELS,
    build,stage_body,gpu_writes,set_word,
)
from tools.make_map02_v70_synthetic_psx_exe import START,lui,ori,sw
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v122_mips_dma2_return import summarize

PASS=("VH122_MIPS_DMA2_RETURN_PASS stages=6 dma2_blocks=5 words=15 "
      "native_unai=5 readbacks=5 four_back=1 vblanks=0 erased=1\n")


class MipsDma2Executable(unittest.TestCase):
    def test_self_authored_psx_exe_is_bounded_deterministic_and_signed(self):
        image,stops,ops,starts=build()
        self.assertEqual(len(image),HEADER_SIZE+SECTION_SIZE)
        self.assertEqual(image[:8],b"PS-X EXE")
        self.assertEqual(image[0x4c:0x54],MAGIC)
        self.assertEqual(struct.unpack_from("<I",image,0x10)[0],START)
        self.assertEqual(struct.unpack_from("<I",image,0x1c)[0],SECTION_SIZE)
        self.assertEqual(stops[:-1],starts[1:])
        self.assertEqual(len(stops),6)
        self.assertEqual(tuple(struct.unpack_from("<"+str(len(ops))+"I",
                         image,HEADER_SIZE)),tuple(ops))
        self.assertEqual(build(),(image,stops,ops,starts))

    def test_dma2_register_configuration_follows_pinned_psxdma(self):
        self.assertEqual(DMA2_MADR,0x00012000)
        self.assertEqual(DMA2_BCR,0x00010003)
        self.assertEqual(DMA2_CHCR,0x01000201)
        self.assertEqual(DMA2_DPCR,0x800)
        self.assertEqual(PACKET_ADDR,0x80012000)
        self.assertGreaterEqual(PACKET_ADDR,START+SECTION_SIZE)
        self.assertEqual(RECT_XY,(160<<16)|40)
        self.assertEqual(RECT_SIZE,(4<<16)|4)

    def test_setup_is_interpreted_mips_gp0_and_dpcr_channel_enable(self):
        b=stage_body(0)
        self.assertEqual(b[:2],(lui(8,0x1f80),ori(8,8,0x1810)))
        self.assertEqual(b[2:2+len(SETUP)*3],tuple(gpu_writes(SETUP)))
        self.assertIn(sw(9,0xf0,11),b)
        self.assertEqual(b.count(sw(9,0,8)),len(SETUP))
        self.assertEqual(b[-1],sw(9,0,12))

    def test_five_cpu_stages_author_packet_and_start_dma2_not_direct_gp0(self):
        full=build()[2]
        self.assertEqual(full.count(sw(9,0,8)),len(SETUP))
        for stage,color in enumerate(COLORS,start=1):
            body=stage_body(stage)
            self.assertEqual(body[:2],
                             (lui(10,PACKET_ADDR>>16),
                              ori(10,10,PACKET_ADDR&0xffff)))
            for offset,word in enumerate((color,RECT_XY,RECT_SIZE)):
                triple=set_word(10,4*offset,word)
                self.assertEqual(body[2+offset*3:5+offset*3],triple)
            for offset,value in ((0xa0,DMA2_MADR),(0xa4,DMA2_BCR),
                                 (0xa8,DMA2_CHCR)):
                self.assertIn(tuple(set_word(11,offset,value)),
                              tuple(body[i:i+3] for i in range(len(body)-2)))
            self.assertIn(sw(0,0xa8,11),body)
            self.assertNotIn(sw(9,0,8),body)
            self.assertEqual(body[-1],sw(9,0,12))
        self.assertEqual(full.count(sw(9,0xa8,11)),5)
        self.assertEqual(full.count(sw(0,0xa8,11)),5)
        self.assertEqual(COLORS[0],COLORS[-1])
        self.assertEqual(len(set(COLORS[:4])),4)
        self.assertEqual(EXPECTED_PIXELS,(0x001f,0x03e0,0x7c00,0x03ff,0x001f))

    def test_each_cpu_marker_is_distinct_and_not_dma_payload(self):
        self.assertEqual(len(set(MARKERS)),6)
        for i in range(6):
            b=stage_body(i)
            self.assertIn(lui(12,MARKER_ADDR>>16),b)
            self.assertIn(ori(12,12,(MARKER_ADDR+4*i)&0xffff),b)
            self.assertIn(lui(9,MARKERS[i]>>16),b)
            self.assertEqual(b[-1],sw(9,0,12))

    def test_pinned_dma2_hook_checks_real_psxdma2_branch_and_source(self):
        src=(ROOT/"tools/apply_map02_v122_pcsx_rearmed.py").read_text()
        for term in ('void psxDma2(u32 madr, u32 bcr, u32 chcr)',
                     'case 0x01000201: // mem2vram',
                     "vh122_dma2_blocks++","vh122_dma2_rejected++",
                     "madr==0x00012000u","bcr==0x00010003u",
                     "chcr==0x01000201u",
                     'memcmp(tag,"VH122SY!",sizeof(tag))',
                     "Config.Cpu!=1","psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER)",
                     "GPU_freeze(1,&setup_freeze,&setup_ptr)",
                     "vh80_reset()","vh115_enable(1)",
                     "vh122_dma2_blocks!=phase+1u",
                     "vram[y*1024u+x]!=vh122_colors[phase]",
                     "metrics.handlers!=phase+1u",
                     "five.returned_to_four_back[0]!=1u",
                     "vh115_sample_cache_erased()"):
            self.assertIn(term,src)
        self.assertNotIn("GPU_writeDataMem(",src)
        self.assertNotIn("GPU_writeData(",src)
        self.assertIn("apply_v121(root)",src)

    def test_private_sanitized_aggregate_reports_no_cpu_gpu_words(self):
        report=summarize(PASS)
        self.assertEqual(report["native_dma2_mem_to_gpu_blocks"],5)
        self.assertEqual(report["gpu_packet_words_via_dma2"],15)
        self.assertEqual(report["exact_return_to_four_back"],1)
        self.assertTrue(report["independent_psxdma2_mem_to_gpu_branch_observer_confirmed"])
        self.assertFalse(report["host_submitted_gp0_draw_commands_in_v122"])
        self.assertFalse(report["HD_replacement_approved"])
        wire=json.dumps(report,sort_keys=True)
        for secret in ("0x600000ff","0x1f8010a8",'"pixel_value":',
                       '"raw_gp0":','"raw_bytes":','"hash":'):
            self.assertNotIn(secret,wire)

    def test_fail_closed_missing_duplicate_forged_or_invalid_native_status(self):
        cases=[
            "",PASS+PASS,"VH122_DMA2_COUNT_REFUSED phase=0\n"+PASS,
            PASS.replace("stages=6","stages=5"),
            PASS.replace("dma2_blocks=5","dma2_blocks=4"),
            PASS.replace("words=15","words=14"),
            PASS.replace("native_unai=5","native_unai=4"),
            PASS.replace("readbacks=5","readbacks=4"),
            PASS.replace("four_back=1","four_back=0"),
            PASS.replace("vblanks=0","vblanks=1"),
            PASS.replace("erased=1","erased=0"),
            "VH122_MIPS_DMA2_RETURN_PASS stages=6 dma2_blocks=5\n",
        ]
        for raw in cases:
            with self.subTest(raw=raw),self.assertRaises(Refused):
                summarize(raw)

    def test_ci_requires_separate_interpreted_dma2_exe_and_old_sha256_binding(self):
        flow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        for token in (
            "apply_map02_v122_pcsx_rearmed",
            "make_map02_v122_mips_dma2_gp0_exe",
            "--vh122-mips-dma2-return-smoke",
            "VH122_MIPS_DMA2_RETURN_PASS stages=6",
            "sha256sum -c proof/private/native.sha256",
            "summarize_map02_v122_mips_dma2_return",
            "v122-mips-dma2-return-summary.json",
            "path: proof/public/",
        ):
            self.assertIn(token,flow)


if __name__=="__main__":
    unittest.main()
