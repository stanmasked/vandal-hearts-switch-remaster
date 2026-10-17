#!/usr/bin/env python3
"""One MIPS GPU DMA2 linked list contains all five ordered GP0 draws."""
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from tools.make_map02_v124_mips_single_list_return_exe import (
    MAGIC,MARKERS,MARKER_ADDR,PACKET_ADDR,START,HEADER_SIZE,SECTION_SIZE,
    NODE_FIRST,NODE_DRAWS,NODE_END,NODE_ADDRS,
    HEAD_FIRST,HEAD_DRAWS,HEAD_END,COLORS,RECT_XY,RECT_SIZE,
    DMA2_CHCR,DMA2_MADR,DMA2_BCR,DMA2_DPCR,SETUP,
    EXPECTED_PIXELS,stage_body,build,set_word,gpu_writes,
)
from tools.make_map02_v70_synthetic_psx_exe import lui,ori,sw
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v124_one_list_five_draws import summarize

PASS=("VH124_ONE_LIST_FIVE_GP0_PASS stages=2 lists=1 nodes=7 "
      "words=15 unai=5 intermediate=5 readbacks=1 four_back=1 "
      "vblanks=0 erased=1\n")


class OneGpuListFiveOrderedDraws(unittest.TestCase):
    def test_authentic_new_synthetic_exe_and_exactly_two_bounded_cpu_stages(self):
        data,stops,ops,starts=build()
        self.assertEqual(len(data),HEADER_SIZE+SECTION_SIZE)
        self.assertEqual(data[:8],b"PS-X EXE")
        self.assertEqual(data[0x4c:0x54],MAGIC)
        self.assertEqual(struct.unpack_from("<I",data,0x10)[0],START)
        self.assertEqual(struct.unpack_from("<I",data,0x1c)[0],SECTION_SIZE)
        self.assertEqual(len(stops),2)
        self.assertEqual(stops[:-1],starts[1:])
        self.assertEqual(tuple(struct.unpack_from(
            "<"+str(len(ops))+"I",data,HEADER_SIZE)),tuple(ops))
        self.assertEqual(build(),(data,stops,ops,starts))

    def test_seven_exact_nodes_and_one_linked_list_dma(self):
        self.assertEqual(NODE_FIRST,0x12000)
        self.assertEqual(NODE_DRAWS,tuple(0x12100+0x100*i for i in range(5)))
        self.assertEqual(NODE_END,0x12600)
        self.assertEqual(len(NODE_ADDRS),7)
        self.assertEqual(HEAD_FIRST,NODE_DRAWS[0])
        self.assertEqual(HEAD_DRAWS,
                         tuple((3<<24)|NODE_ADDRS[i+2] for i in range(5)))
        self.assertEqual(HEAD_END,0x00800000)
        self.assertEqual((DMA2_MADR,DMA2_BCR,DMA2_CHCR,DMA2_DPCR),
                         (0x12000,0,0x01000401,0x800))

    def test_original_mips_authors_every_header_packet_and_single_chcr(self):
        stage=stage_body(1)
        self.assertEqual(stage[:2],
                         (lui(10,PACKET_ADDR>>16),
                          ori(10,10,PACKET_ADDR&0xffff)))
        entries=[(0,HEAD_FIRST)]
        for i,color in enumerate(COLORS):
            off=0x100*(i+1)
            entries.extend(((off,HEAD_DRAWS[i]),
                            (off+4,color),
                            (off+8,RECT_XY),
                            (off+12,RECT_SIZE)))
        entries.append((0x600,HEAD_END))
        for i,(off,value) in enumerate(entries):
            self.assertEqual(stage[2+3*i:5+3*i],
                             tuple(set_word(10,off,value)))
        self.assertEqual(stage.count(sw(9,0xa8,11)),1)
        self.assertEqual(stage.count(sw(0,0xa8,11)),1)
        for offset,val in ((0xa0,DMA2_MADR),(0xa4,DMA2_BCR),
                           (0xa8,DMA2_CHCR)):
            self.assertIn(tuple(set_word(11,offset,val)),
                          tuple(stage[i:i+3] for i in range(len(stage)-2)))
        self.assertNotIn(sw(9,0,8),stage)
        self.assertEqual(stage[-1],sw(9,0,12))
        self.assertEqual(len(set(MARKERS)),2)
        self.assertEqual(COLORS[0],COLORS[-1])
        self.assertEqual(len(set(COLORS[:4])),4)

    def test_setup_not_in_native_five_draw_window(self):
        s=stage_body(0)
        self.assertEqual(s[:2],(lui(8,0x1f80),ori(8,8,0x1810)))
        self.assertEqual(s[2:2+3*len(SETUP)],tuple(gpu_writes(SETUP)))
        self.assertIn(tuple(set_word(11,0xf0,DMA2_DPCR)),
                      tuple(s[i:i+3] for i in range(len(s)-2)))
        self.assertEqual(s[-1],sw(9,0,12))
        self.assertIn(ori(12,12,MARKER_ADDR&0xffff),s)

    def test_native_unai_checks_all_intermediate_4x4_pixels_after_each_draw(self):
        src=(ROOT/"tools/apply_map02_v124_pcsx_rearmed.py").read_text()
        for term in (
            "vh115_note(vh115_post,24u,changed);",
            "if(vh124_intermediate_enabled)",
            "static const uint16_t colors[5]",
            "vh124_intermediate_seen>=5u",
            "for(unsigned int y=160u;y<164u;y++)",
            "for(unsigned int x=40u;x<44u;x++)",
            "gpu_unai.vram[y*1024u+x]",
            "colors[vh124_intermediate_seen]",
            "vh124_intermediate_rejected++",
            "vh124_intermediate_seen++",
            "extern \"C\"",
            "GPUFreeze_t final_vram={0}",
            "five.returned_to_four_back[0]!=1u",
            "samples.handlers!=5u",
            "vh115_sample_cache_erased()",
        ):
            with self.subTest(term=term):
                self.assertIn(term,src)
        self.assertEqual(EXPECTED_PIXELS,(0x001f,0x03e0,0x7c00,0x03ff,0x001f))

    def test_native_dma_and_gpulib_traversal_one_list_only(self):
        src=(ROOT/"tools/apply_map02_v124_pcsx_rearmed.py").read_text()
        for term in (
            "apply_v123(root)",
            "case 0x01000401: // dma chain",
            "vh124_dma_dispatches==0u",
            "vh124_dma_dispatches++",
            "vh124_nodes_seen++",
            "vh124_words_seen+=(unsigned)len",
            "vh124_dma_dispatches!=1u",
            "vh124_nodes_seen!=7u",
            "vh124_words_seen!=15u",
            "vh124_intermediate_seen!=5u",
            "vh124_intermediate_rejected!=0u",
            "vh124_mips_one_list_smoke",
            'memcmp(tag,"VH124SY!",sizeof(tag))',
        ):
            self.assertIn(term,src)
        self.assertNotIn("GPU_writeDataMem(",src)
        self.assertNotIn("GPU_writeData(",src)

    def test_only_sanitized_aggregate_published(self):
        result=summarize(PASS)
        self.assertEqual(result["linked_list_dma_dispatches"],1)
        self.assertEqual(result["native_gpu_chain_nodes"],7)
        self.assertEqual(result["ordered_intermediate_vram_checks"],5)
        self.assertEqual(result["exact_four_back_returns"],1)
        self.assertFalse(result["host_submitted_gpu_draw_packets"])
        self.assertFalse(result["HD_replacement_approved"])
        text=json.dumps(result,sort_keys=True)
        for secret in ('"pixel_value":','"raw_gpu_words":','"sha256":',
                       "0x600000ff","private_jsonl","vram_address"):
            self.assertNotIn(secret,text)

    def test_marker_rejects_wrong_order_counts_missing_duplicate_or_native_failure(self):
        for sample in (
            "",PASS+PASS,"VH124_CHAIN_COUNTS_REFUSED\n"+PASS,
            PASS.replace("stages=2","stages=6"),
            PASS.replace("lists=1","lists=5"),
            PASS.replace("nodes=7","nodes=6"),
            PASS.replace("words=15","words=14"),
            PASS.replace("unai=5","unai=4"),
            PASS.replace("intermediate=5","intermediate=4"),
            PASS.replace("readbacks=1","readbacks=5"),
            PASS.replace("four_back=1","four_back=0"),
            PASS.replace("vblanks=0","vblanks=1"),
            PASS.replace("erased=1","erased=0"),
            "VH124_ONE_LIST_FIVE_GP0_PASS stages=2\n",
        ):
            with self.subTest(sample=sample),self.assertRaises(Refused):
                summarize(sample)

    def test_pinned_ci_runs_one_dma_and_preserves_original_private_journal(self):
        yaml=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        for term in (
            "apply_map02_v124_pcsx_rearmed",
            "make_map02_v124_mips_single_list_return_exe",
            "--vh124-mips-one-list-return-smoke",
            "VH124_ONE_LIST_FIVE_GP0_PASS stages=2",
            "summarize_map02_v124_one_list_five_draws",
            "v124-single-dma-five-gp0-summary.json",
            "VH123_MIPS_GPU_LIST_RETURN_PASS stages=6",
            "sha256sum -c proof/private/native.sha256",
            "path: proof/public/",
        ):
            self.assertIn(term,yaml)


if __name__=="__main__":
    unittest.main()
