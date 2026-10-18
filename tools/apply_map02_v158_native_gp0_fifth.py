#!/usr/bin/env python3
"""v158: source-bound fifth native MIPS SW to GP0, synthetic-only.

Extends v157's four LUI/ORI instructions with the first self-authored PS1
MMIO store. Requires full v151 RAM SHA-256 and v156 register verification.
The fifth instruction must actually reach PCSX's psxMemWrite32 observer,
while an intentionally changed fifth opcode must be refused beforehand.
No original retail PS1 code, gameplay, or assets are used.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v157_t1_fourth_checkpoint import apply as apply_v157
from .apply_map02_v155_four_instruction_native import four_source_words
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v129_four_vblank_exe import build


def five_source_words():
    source,*_=build()
    if (len(source)!=10240 or source[:8]!=b"PS-X EXE"
            or source[0x4c:0x54]!=b"VH129SY!"):
        raise ValueError("refusing changed synthetic v129 PS-X EXE source")
    words=tuple(int.from_bytes(source[2048+4*i:2052+4*i],"little")
                for i in range(5))
    if words[:4]!=four_source_words():
        raise ValueError("synthetic first four MIPS opcodes have changed")
    fifth=words[4]
    if (fifth>>26)!=0x2b or (fifth>>21)&31!=8 or (fifth>>16)&31!=9 or (fifth&0xffff)!=0:
        raise ValueError("fifth instruction must be MIPS SW t1,0(t0) to GP0")
    return words


def gp0_observer_c():
    if five_source_words()[4]!=0xad090000:
        raise ValueError("source-authored fifth opcode changed")
    return r'''
/* v158 records ONLY the source-authored fifth synthetic MIPS SW
 * reaching the actual native PS1 MMIO write path. No private traces. */
static unsigned vh158_gp0_active, vh158_gp0_count, vh158_gp0_bad;
void vh158_arm_gp0(void) {
    vh158_gp0_active=1u; vh158_gp0_count=0u; vh158_gp0_bad=0u;
}
static void vh158_capture_gp0(psxRegisters *regs,u32 addr,u32 value) {
    if(!vh158_gp0_active) return;
    if((addr&0x1fffffffu)!=0x1f801810u ||
       value!=0xe3000000u ||
       regs->pc!=0x80010014u ||
       regs->code!=0xad090000u) {
        vh158_gp0_bad++;
        return;
    }
    vh158_gp0_count++;
}
unsigned vh158_gp0_writes(void){return vh158_gp0_count;}
unsigned vh158_gp0_faults(void){return vh158_gp0_bad;}
void vh158_disarm_gp0(void){vh158_gp0_active=0u;}

'''


def patch_memory(source: str) -> str:
    if "vh158_capture_gp0" in source:
        raise ValueError("refusing to install native GP0 observer twice")
    source=once(source,
        "void vh140_mmio_enable(unsigned mutate_expected) {\n",
        gp0_observer_c()+"void vh140_mmio_enable(unsigned mutate_expected) {\n",
        "place dedicated source-derived GP0 observer in pinned PS1 memory writer")
    return once(source,
        "    if(vh147_active) vh147_capture(regs,addr,value);\n",
        "    if(vh158_gp0_active) vh158_capture_gp0(regs,addr,value);\n"
        "    if(vh147_active) vh147_capture(regs,addr,value);\n",
        "observe native fifth MIPS SW before MMIO side effects")


def patch_interpreter(source: str) -> str:
    old=four_source_words()
    new=five_source_words()
    source=once(source,
        "static const u32 vh152_words[4]={"+
            ",".join("0x%08xu"%w for w in old)+"};",
        "static const u32 vh152_words[5]={"+
            ",".join("0x%08xu"%w for w in new)+"};",
        "five-word source exact opcode witness")
    source=once(source,
        "static unsigned vh155_four_enabled,vh155_mutate_fourth_word;",
        "static unsigned vh155_four_enabled,vh155_mutate_fourth_word;\n"
        "static unsigned vh158_five_enabled,vh158_mutate_fifth;",
        "test-only fifth native MIPS SW mode")
    anchor="int vh155_enable_four(void){"
    extra=(
        "int vh158_enable_five(void){\n"
        "    if(vh152_state!=1u || !vh155_four_enabled ||\n"
        "       vh152_matches!=0u || vh158_five_enabled) return -1;\n"
        "    vh158_five_enabled=1u;\n"
        "    return 0;\n"
        "}\n"
        "void vh158_arm_fifth_mutation(void){\n"
        "    if(vh158_five_enabled) vh158_mutate_fifth=1u;\n"
        "}\n")
    source=once(source,anchor,extra+anchor,
                "native five-instruction opt-in activation")
    source=once(source,
        "pc>=0x80010000u+(vh155_four_enabled ? 16u : 12u) || (pc&3u) ||",
        "pc>=0x80010000u+(vh158_five_enabled ? 20u :\n"
        "                           vh155_four_enabled ? 16u : 12u) || (pc&3u) ||",
        "fifth guest PC only available with explicit v158 mode")
    source=once(source,
        "idx>=(vh155_four_enabled ? 4u : 3u) ||",
        "idx>=(vh158_five_enabled ? 5u :\n"
        "             vh155_four_enabled ? 4u : 3u) ||",
        "retain third/fourth boundaries by default")
    source=once(source,
        "        vh155_mutate_fourth_word=0u;\n"
        "    }\n"
        "    return 1;",
        "        vh155_mutate_fourth_word=0u;\n"
        "    }\n"
        "    /* Four source-verified opcodes ran. Corrupt only instruction 5\n"
        "     * in guest RAM, just before its native fetch/dispatch. */\n"
        "    if(vh158_five_enabled && vh158_mutate_fifth &&\n"
        "       vh152_matches==4u){\n"
        "        ((unsigned char *)regs->ptrs.psxM)[0x10010u]^=1u;\n"
        "        vh158_mutate_fifth=0u;\n"
        "    }\n"
        "    return 1;",
        "mutate fifth native word only after four valid guest instructions")
    source=once(source,
        "    vh157_corrupt_t1_fourth=0u;}",
        "    vh157_corrupt_t1_fourth=0u;\n"
        "    vh158_five_enabled=0u; vh158_mutate_fifth=0u;}",
        "disarm independent fifth opcode witness")
    source=once(source,
        "    if(pc==0x8001000cu){",
        "    if(pc==0x80010010u)\n"
        "        return regs->GPR.r[8]==0x1f801810u &&\n"
        "               regs->GPR.r[9]==0xe3000000u;\n"
        "    if(pc==0x8001000cu){",
        "confirm source MIPS t0 address and t1 GP0 value before native SW")
    return source


def patch_frontend(source: str) -> str:
    if "VH158_NATIVE_GP0_FIFTH_PASS" in source:
        raise ValueError("v158 already present")
    source=once(source,
        "\tint vh157_corrupt_t1_fourth = 0;\n",
        "\tint vh157_corrupt_t1_fourth = 0;\n"
        "\tint vh158_five_instructions = 0;\n"
        "\tint vh158_mutate_fifth = 0;\n"
        "\textern int vh158_enable_five(void);\n"
        "\textern void vh158_arm_fifth_mutation(void);\n"
        "\textern void vh158_arm_gp0(void);\n"
        "\textern unsigned vh158_gp0_writes(void);\n"
        "\textern unsigned vh158_gp0_faults(void);\n"
        "\textern void vh158_disarm_gp0(void);\n",
        "fifth native test opt-in and GP0 MMIO observer")
    source=once(source,
        '\t\telse if (!strcmp(argv[i], "--vh157-corrupt-t1-fourth"))\n',
        '\t\telse if (!strcmp(argv[i], "--vh158-five-instructions"))\n'
        '\t\t\tvh158_five_instructions=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh158-mutate-fifth"))\n'
        '\t\t\tvh158_mutate_fifth=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh157-corrupt-t1-fourth"))\n',
        "parse fifth native GPU write and negative test flags")
    source=once(source,
        "    if(vh157_corrupt_t1_fourth &&\n",
        "    if((vh158_five_instructions || vh158_mutate_fifth) &&\n"
        "       (!vh158_five_instructions || !vh156_verify_register_effects ||\n"
        "        !vh155_four_instructions || !vh150_bounded_instructions ||\n"
        "        vh129_vblank_mode!=0 || vh152_mutate_post_verify ||\n"
        "        vh153_mutate_second_word || vh154_mutate_third_word ||\n"
        "        vh155_mutate_fourth_word || vh156_corrupt_t0_second ||\n"
        "        vh157_corrupt_t1_fourth)){\n"
        '        SysPrintf("VH158_INVALID_MODE_REFUSED\\n");\n'
        "        ClosePlugins();SysClose();menu_finish();plat_finish();return 62;\n"
        "    }\n"
        "    if(vh157_corrupt_t1_fourth &&\n",
        "reject private/retail and old negative modes before MIPS execution")
    source=once(source,
        "                if(vh157_corrupt_t1_fourth)\n"
        "                    vh157_arm_t1_fourth();\n",
        "                if(vh157_corrupt_t1_fourth)\n"
        "                    vh157_arm_t1_fourth();\n"
        "                if(vh158_five_instructions){\n"
        "                    if(vh158_enable_five()!=0){\n"
        '                        SysPrintf("VH158_ARM_REFUSED\\n");\n'
        "                        ClosePlugins();SysClose();menu_finish();plat_finish();return 62;\n"
        "                    }\n"
        "                    vh158_arm_gp0();\n"
        "                    if(vh158_mutate_fifth) vh158_arm_fifth_mutation();\n"
        "                }\n",
        "arm native GP0 witness after complete guest RAM SHA-256 check")
    source=once(source,
        "vh155_four_instructions ? 4u : 3u",
        "vh158_five_instructions ? 5u :\n"
        "                         vh155_four_instructions ? 4u : 3u",
        "increase bounded execution to five only for synthetic GP0 mode")
    source=once(source,
        "                if(vh156_verify_register_effects){\n"
        "                    if(vh157_corrupt_t1_fourth){",
        "                if(vh158_five_instructions){\n"
        "                    unsigned gp0=vh158_gp0_writes();\n"
        "                    unsigned gp0_bad=vh158_gp0_faults();\n"
        "                    vh158_disarm_gp0();\n"
        "                    if(vh158_mutate_fifth){\n"
        "                        if(!faulted || witnessed!=4u || steps!=5u ||\n"
        "                           reason!=0u || gp0!=0u || gp0_bad!=0u){\n"
        '                            SysPrintf("VH158_FIFTH_FALSE_ACCEPT_REFUSED\\n");\n'
        "                            ClosePlugins();SysClose();menu_finish();plat_finish();return 62;\n"
        "                        }\n"
        '                        SysPrintf("VH158_NATIVE_FIFTH_OPCODE_REFUSED"'
        '" matched=4 attempted=5 gp0_writes=0 original_retail=0\\n");\n'
        "                        ClosePlugins();SysClose();menu_finish();plat_finish();return 62;\n"
        "                    }\n"
        "                    if(faulted || witnessed!=5u || steps!=5u ||\n"
        "                       reason!=1u || gp0!=1u || gp0_bad!=0u ||\n"
        "                       psxRegs.GPR.r[8]!=0x1f801810u ||\n"
        "                       psxRegs.GPR.r[9]!=0xe3000000u){\n"
        '                        SysPrintf("VH158_GP0_FIFTH_DIAG"'
        '" accepted=%u attempts=%u stop=%u fault=%u gp0=%u bad=%u"'
        '" t0_ok=%u t1_ok=%u\\n",\\n"'
        "                            witnessed,steps,reason,faulted,gp0,gp0_bad,\\n"
        "                            psxRegs.GPR.r[8]==0x1f801810u,\\n"
        "                            psxRegs.GPR.r[9]==0xe3000000u);\\n"
        '                        SysPrintf("VH158_GP0_FIFTH_REFUSED\\n");\n'
        "                        ClosePlugins();SysClose();menu_finish();plat_finish();return 62;\n"
        "                    }\n"
        '                    SysPrintf("VH158_NATIVE_GP0_FIFTH_PASS"'
        '" opcodes=5 gp0_writes=1 capped=1 original_retail=0\\n");\n'
        "                    ClosePlugins();SysClose();menu_finish();plat_finish();return 0;\n"
        "                }\n"
        "                if(vh156_verify_register_effects){\n"
        "                    if(vh157_corrupt_t1_fourth){",
        "witness MIPS GP0 store in native memory writer and exactly five opcodes")
    return source


def apply(root: Path):
    result=apply_v157(root)
    base=root.resolve()
    mem=base/"libpcsxcore/psxmem.c"
    interp=base/"libpcsxcore/psxinterpreter.c"
    main=base/"frontend/main.c"
    mem.write_text(patch_memory(mem.read_text()))
    interp.write_text(patch_interpreter(interp.read_text()))
    main.write_text(patch_frontend(main.read_text()))
    return dict(result,
        v158_source_authored_fifth_mips_sw=True,
        v158_gp0_exact_native_memory_writer_witness=True,
        v158_fifth_instruction_mutation_pre_dispatch_refused=True,
        v158_original_four_step_native_tests_preserved=True,
        v158_original_game_execution_enabled=False,
        v158_original_MAP02_rendered=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
