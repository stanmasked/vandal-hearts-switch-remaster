#!/usr/bin/env python3
"""Self-authored MIPS variable GPU DMA2: 1 + 2 + 2 real drawings."""
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from tools.make_map02_v125_variable_gpu_dma_exe import (
    MAGIC,MARKERS,MARKER_ADDR,BASES,DMA2_BCR,DMA2_CHCR,DMA2_DPCR,
    RECT_XY,RECT_SIZE,COLORS,SETUP,HEADER_SIZE,SECTION_SIZE,START,
    chain_entries,stage_body,build,set_word,gpu_writes,
)
from tools.make_map02_v70_synthetic_psx_exe import lui,ori,sw
from tools.summarize_map02_v125_variable_dma import summarize
from tools.verify_map02_v82_native_trace import Refused

PASS=("VH125_VARIABLE_DMA_PASS stages=4 dma=3 nodes=10 words=15 "
      "unai=5 intermediate=5 readbacks=1 four_back=1 vblanks=0 erased=1\n")


class ThreeVariableMipsGpuDmaTests(unittest.TestCase):
    def test_bounded_self_authored_mips_exe_has_four_cpu_stages(self):
        data,stops,ops,starts=build()
        self.assertEqual(len(data),HEADER_SIZE+SECTION_SIZE)
        self.assertEqual(data[:8],b"PS-X EXE")
        self.assertEqual(data[0x4c:0x54],MAGIC)
        self.assertEqual(struct.unpack_from("<I",data,0x10)[0],START)
        self.assertEqual(struct.unpack_from("<I",data,0x1c)[0],SECTION_SIZE)
        self.assertEqual(stops[:-1],starts[1:])
        self.assertEqual(len(stops),4)
        self.assertEqual(tuple(struct.unpack_from(
            "<"+str(len(ops))+"I",data,HEADER_SIZE)),tuple(ops))
        self.assertEqual(build(),(data,stops,ops,starts))

    def test_real_dma_starts_and_packet_lengths_distinct(self):
        self.assertEqual(BASES,(0x12000,0x13000,0x14000))
        self.assertEqual((DMA2_BCR,DMA2_CHCR,DMA2_DPCR),
                         (0,0x01000401,0x800))
        self.assertEqual(COLORS[0],COLORS[-1])
        self.assertEqual(len(set(COLORS[:4])),4)
        for n in range(3):
            self.assertEqual(chain_entries(n)[0],(0,BASES[n]+0x100))
        self.assertEqual(chain_entries(0)[1],(0x100,(3<<24)|0x12200))
        self.assertEqual(chain_entries(1)[1],(0x100,(6<<24)|0x13200))
        self.assertEqual(chain_entries(2)[1],(0x100,(3<<24)|0x14200))
        self.assertIn((0x200,(3<<24)|0x14300),chain_entries(2))
        for phase,last_offset in enumerate((0x200,0x200,0x300)):
            self.assertEqual(chain_entries(phase)[-1],
                             (last_offset,0x00800000))

    def test_six_word_node_contains_exactly_B_then_C_draws(self):
        entries=dict(chain_entries(1))
        expected=(COLORS[1],RECT_XY,RECT_SIZE,
                  COLORS[2],RECT_XY,RECT_SIZE)
        self.assertEqual(tuple(entries[0x104+4*i] for i in range(6)),expected)
        self.assertEqual(sum(
            1 for off,_ in chain_entries(1) if off in
            (0x104,0x108,0x10c,0x110,0x114,0x118)),6)

    def test_third_chain_contains_two_distinct_draw_nodes_D_then_A(self):
        entries=dict(chain_entries(2))
        self.assertEqual((entries[0x104],entries[0x108],entries[0x10c]),
                         (COLORS[3],RECT_XY,RECT_SIZE))
        self.assertEqual((entries[0x204],entries[0x208],entries[0x20c]),
                         (COLORS[4],RECT_XY,RECT_SIZE))
        self.assertEqual(entries[0x200],(3<<24)|0x14300)

    def test_interpreted_cpu_writes_all_nodes_and_three_DMA_starts(self):
        ops=build()[2]
        self.assertEqual(ops.count(sw(9,0,8)),len(SETUP))
        self.assertEqual(ops.count(sw(9,0xa8,11)),3)
        self.assertEqual(ops.count(sw(0,0xa8,11)),3)
        for phase,base in enumerate(BASES,1):
            instructions=stage_body(phase)
            self.assertEqual(instructions[:2],
                             (lui(10,0x8001),ori(10,10,base&0xffff)))
            entries=chain_entries(phase-1)
            for i,(off,word) in enumerate(entries):
                self.assertEqual(instructions[2+3*i:5+3*i],
                                 tuple(set_word(10,off,word)))
            for address,value in ((0xa0,base),(0xa4,0),(0xa8,DMA2_CHCR)):
                self.assertIn(tuple(set_word(11,address,value)),
                              tuple(instructions[i:i+3] for i in
                                    range(len(instructions)-2)))
            self.assertNotIn(sw(9,0,8),instructions)
            self.assertEqual(instructions[-1],sw(9,0,12))

    def test_cpu_setup_commands_outside_sampled_five_draw_window(self):
        s=stage_body(0)
        self.assertEqual(s[:2],(lui(8,0x1f80),ori(8,8,0x1810)))
        self.assertEqual(s[2:2+3*len(SETUP)],tuple(gpu_writes(SETUP)))
        self.assertIn(tuple(set_word(11,0xf0,DMA2_DPCR)),
                      tuple(s[i:i+3] for i in range(len(s)-2)))
        self.assertEqual(MARKERS,tuple(0x12500000+i for i in range(4)))
        for stage in range(4):
            self.assertIn(ori(12,12,(MARKER_ADDR+4*stage)&0xffff),
                          stage_body(stage))

    def test_genuine_psxdma2_and_gpu_dma_chain_per_phase_observers(self):
        source=(ROOT/"tools/apply_map02_v125_pcsx_rearmed.py").read_text()
        tokens=(
            "apply_v124(root)",
            "case 0x01000401: // dma chain",
            "vh125_dma_count++",
            "vh125_node_count++",
            "vh125_node_words+=(unsigned)len",
            "madr==start[vh125_dma_count]",
            "unsigned words_required[10]",
            "0u,3u,0u,0u,6u,0u,0u,3u,3u,0u",
            "vh125_node_count!=cumulative_nodes[phase]",
            "vh125_node_words!=cumulative_words[phase]",
            "vh124_intermediate_seen!=cumulative_draws[phase]",
            "vh124_intermediate_rejected!=0u",
            "vh119_get_quintuplet_metrics(&quints)",
            "quints.returned_to_four_back[0]!=1u",
            'memcmp(tag,"VH125SY!",sizeof(tag))',
            "vh115_sample_cache_erased()",
        )
        for t in tokens:
            with self.subTest(t=t):self.assertIn(t,source)
        self.assertNotIn("GPU_writeDataMem(",source)
        self.assertNotIn("GPU_writeData(",source)

    def test_public_report_sanitized_and_correct(self):
        r=summarize(PASS)
        self.assertEqual(r["gpu_dma2_linked_list_transfers"],3)
        self.assertEqual(r["native_gpu_chain_nodes_visited"],10)
        self.assertEqual(r["gpu_command_words_traversed"],15)
        self.assertEqual(r["ordered_native_intermediate_vram_checks"],5)
        self.assertEqual(r["exact_return_to_four_back"],1)
        self.assertFalse(r["gpu_draw_words_submitted_by_host"])
        self.assertFalse(r["HD_replacement_approved"])
        published=json.dumps(r,sort_keys=True)
        for unwanted in ('"raw_pixels":','"pixel_value":','"raw_gp0":',
                         "0x600000ff","private_jsonl",'"sha256":'):
            self.assertNotIn(unwanted,published)

    def test_bad_duplicate_missing_partial_or_native_refusal_fails_closed(self):
        cases=(
            "",PASS+PASS,"VH125_DMA_CHAIN_REFUSED phase=2\n"+PASS,
            PASS.replace("stages=4","stages=3"),
            PASS.replace("dma=3","dma=2"),
            PASS.replace("nodes=10","nodes=9"),
            PASS.replace("words=15","words=14"),
            PASS.replace("unai=5","unai=4"),
            PASS.replace("intermediate=5","intermediate=4"),
            PASS.replace("readbacks=1","readbacks=5"),
            PASS.replace("four_back=1","four_back=0"),
            PASS.replace("vblanks=0","vblanks=1"),
            PASS.replace("erased=1","erased=0"),
            "VH125_VARIABLE_DMA_PASS stages=4\n",
        )
        for value in cases:
            with self.subTest(value=value),self.assertRaises(Refused):
                summarize(value)

    def test_pinned_workflow_preserves_v124_and_original_private_journal(self):
        flow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        for token in (
            "apply_map02_v125_pcsx_rearmed",
            "make_map02_v125_variable_gpu_dma_exe",
            "--vh125-mips-variable-dma-smoke",
            "VH125_VARIABLE_DMA_PASS stages=4",
            "summarize_map02_v125_variable_dma",
            "v125-variable-dma-summary.json",
            "VH124_ONE_LIST_FIVE_GP0_PASS stages=2",
            "sha256sum -c proof/private/native.sha256",
            "path: proof/public/",
        ):
            self.assertIn(token,flow)


if __name__=="__main__":
    unittest.main()
