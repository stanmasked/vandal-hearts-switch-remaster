#!/usr/bin/env python3
"""Fail-closed self-authored MIPS GPU DMA2 linked-list test and proof audit."""
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from tools.make_map02_v123_mips_dma2_linkedlist_exe import (
    MAGIC,SECTION_SIZE,HEADER_SIZE,MARKERS,MARKER_ADDR,PACKET_ADDR,
    DMA2_MADR,DMA2_BCR,DMA2_CHCR,DMA2_DPCR,
    NODE_FIRST,NODE_DRAW,NODE_END,HEAD_FIRST,HEAD_DRAW,HEAD_END,
    COLORS,RECT_XY,RECT_SIZE,SETUP,EXPECTED_PIXELS,
    build,stage_body,gpu_writes,set_word,
)
from tools.make_map02_v70_synthetic_psx_exe import START,lui,ori,sw
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v123_mips_dma2_linkedlist import summarize

PASS=("VH123_MIPS_GPU_LIST_RETURN_PASS stages=6 lists=5 nodes=15 words=15 "
      "native_unai=5 readbacks=5 four_back=1 vblanks=0 erased=1\n")


class RealGpuLinkedListTest(unittest.TestCase):
    def test_original_self_authored_exe_and_six_bounded_mips_stages(self):
        data,stops,words,starts=build()
        self.assertEqual(len(data),HEADER_SIZE+SECTION_SIZE)
        self.assertEqual(data[:8],b"PS-X EXE")
        self.assertEqual(data[0x4c:0x54],MAGIC)
        self.assertEqual(struct.unpack_from("<I",data,0x10)[0],START)
        self.assertEqual(struct.unpack_from("<I",data,0x1c)[0],SECTION_SIZE)
        self.assertEqual(len(stops),6)
        self.assertEqual(stops[:-1],starts[1:])
        self.assertEqual(tuple(struct.unpack_from(
            "<"+str(len(words))+"I",data,HEADER_SIZE)),tuple(words))
        self.assertEqual(build(),(data,stops,words,starts))

    def test_three_distinct_nodes_correct_headers_and_end_marker(self):
        self.assertEqual((NODE_FIRST,NODE_DRAW,NODE_END),
                         (0x12000,0x12100,0x12200))
        self.assertEqual((HEAD_FIRST,HEAD_DRAW,HEAD_END),
                         (0x12100,0x03012200,0x00800000))
        self.assertEqual(DMA2_MADR,0x12000)
        self.assertEqual(DMA2_BCR,0)
        self.assertEqual(DMA2_CHCR,0x01000401)
        self.assertEqual(DMA2_DPCR,0x800)
        self.assertEqual(PACKET_ADDR,0x80012000)
        self.assertEqual(COLORS[0],COLORS[-1])
        self.assertEqual(len(set(COLORS[:4])),4)
        self.assertEqual(EXPECTED_PIXELS,(0x001f,0x03e0,0x7c00,0x03ff,0x001f))

    def test_cpu_writes_all_three_headers_and_draw_packet_in_ram(self):
        ops=build()[2]
        self.assertEqual(ops.count(sw(9,0,8)),len(SETUP))
        self.assertEqual(ops.count(sw(9,0xa8,11)),5)
        self.assertEqual(ops.count(sw(0,0xa8,11)),5)
        for stage,col in enumerate(COLORS,start=1):
            b=stage_body(stage)
            self.assertEqual(b[:2],
                             (lui(10,PACKET_ADDR>>16),
                              ori(10,10,PACKET_ADDR&0xffff)))
            payload=(
                (0,HEAD_FIRST),(0x100,HEAD_DRAW),(0x104,col),
                (0x108,RECT_XY),(0x10c,RECT_SIZE),(0x200,HEAD_END),
            )
            for index,(offset,value) in enumerate(payload):
                self.assertEqual(b[2+3*index:5+3*index],
                                 tuple(set_word(10,offset,value)))
            for offset,val in ((0xa0,DMA2_MADR),(0xa4,DMA2_BCR),
                               (0xa8,DMA2_CHCR)):
                self.assertIn(tuple(set_word(11,offset,val)),
                              tuple(b[i:i+3] for i in range(len(b)-2)))
            self.assertNotIn(sw(9,0,8),b)
            self.assertEqual(b[-1],sw(9,0,12))
        self.assertEqual(len(set(MARKERS)),6)

    def test_stage_zero_sets_gpu_and_enables_dma2_from_mips(self):
        b=stage_body(0)
        self.assertEqual(b[:2],(lui(8,0x1f80),ori(8,8,0x1810)))
        self.assertEqual(b[2:2+len(SETUP)*3],tuple(gpu_writes(SETUP)))
        self.assertIn(tuple(set_word(11,0xf0,DMA2_DPCR)),
                      tuple(b[i:i+3] for i in range(len(b)-2)))
        self.assertEqual(b[-1],sw(9,0,12))
        for k in range(6):
            body=stage_body(k)
            self.assertIn(ori(12,12,(MARKER_ADDR+4*k)&0xffff),body)
            self.assertIn(lui(9,MARKERS[k]>>16),body)

    def test_real_native_dma2_and_gpu_chain_are_both_observed(self):
        src=(ROOT/"tools/apply_map02_v123_pcsx_rearmed.py").read_text()
        required=(
            'case 0x01000401: // dma chain',
            'unsigned int vh122_dma2_rejected;',
            'long GPUdmaChain(uint32_t *rambase, uint32_t start_addr,',
            'addr = LE32TOH(list[0]) & 0xffffff;',
            'const unsigned expected_addr[3]={0x12000u,0x12100u,0x12200u}',
            'const unsigned expected_len[3]={0u,3u,0u}',
            'const unsigned expected_next[3]={0x12100u,0x12200u,0x800000u}',
            'vh123_nodes_seen++','vh123_words_seen+=(unsigned)len',
            'vh123_dma2_blocks++','vh123_dma2_rejected++',
            'Config.Cpu!=1','GPU_freeze(1,&setup_freeze,&setup_ptr)',
            'memcmp(tag,"VH123SY!",sizeof(tag))',
            'unsigned int off=0x11160u;',
            'unsigned int at=0x11160u+4u*(phase+1u);',
            'psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER)',
            'vh123_nodes_seen!=3u*(phase+1u)',
            'vh123_words_seen!=3u*(phase+1u)',
            'five.returned_to_four_back[0]!=1u',
            'vh115_sample_cache_erased()',
        )
        for term in required:
            with self.subTest(term=term):
                self.assertIn(term,src)
        self.assertIn('apply_v122(root)',src)
        self.assertNotIn('GPU_writeDataMem(',src)
        self.assertNotIn('GPU_writeData(',src)

    def test_only_coarse_aggregate_public_metrics(self):
        r=summarize(PASS)
        self.assertEqual(r["native_dma2_linked_list_dispatches"],5)
        self.assertEqual(r["native_linked_list_nodes_visited"],15)
        self.assertEqual(r["native_gp0_words_traversed"],15)
        self.assertEqual(r["exact_return_to_four_back"],1)
        self.assertTrue(r["native_gpu_dma_chain_three_node_traversal_confirmed"])
        self.assertFalse(r["host_submitted_gp0_draw_commands_in_v123"])
        self.assertFalse(r["HD_replacement_approved"])
        dumped=json.dumps(r,sort_keys=True)
        for forbidden in ('"pixel_value":','"gp0_bytes":',
                          "0x600000ff","vram_address",'"sha256":'):
            self.assertNotIn(forbidden,dumped)

    def test_native_marker_refuses_partial_forged_duplicate_or_error(self):
        wrong=(
            "",PASS+PASS,"VH123_RETURN_REFUSED\n"+PASS,
            PASS.replace("stages=6","stages=5"),
            PASS.replace("lists=5","lists=4"),
            PASS.replace("nodes=15","nodes=14"),
            PASS.replace("words=15","words=14"),
            PASS.replace("native_unai=5","native_unai=4"),
            PASS.replace("readbacks=5","readbacks=4"),
            PASS.replace("four_back=1","four_back=0"),
            PASS.replace("vblanks=0","vblanks=1"),
            PASS.replace("erased=1","erased=0"),
            "VH123_MIPS_GPU_LIST_RETURN_PASS stages=6\n",
        )
        for text in wrong:
            with self.subTest(text=text),self.assertRaises(Refused):
                summarize(text)

    def test_full_pinned_ci_keeps_prior_v122_and_journal_integrity(self):
        flow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        for expected in (
            'apply_map02_v123_pcsx_rearmed',
            'make_map02_v123_mips_dma2_linkedlist_exe',
            '--vh123-mips-gpu-list-return-smoke',
            'VH123_MIPS_GPU_LIST_RETURN_PASS stages=6',
            'summarize_map02_v123_mips_dma2_linkedlist',
            'v123-mips-gpu-linked-list-summary.json',
            'sha256sum -c proof/private/native.sha256',
            'VH122_MIPS_DMA2_RETURN_PASS stages=6',
            'path: proof/public/',
        ):
            self.assertIn(expected,flow)


if __name__=="__main__":
    unittest.main()
