#!/usr/bin/env python3
"""v153: synthetic mutation after instruction one, before instruction two.

Only opt-in v129 synthetic v150/v152 bounded native interpreter test. The
native v152 witness mutates the SECOND source-generated MIPS word after the
first one is checked; the next fetch must refuse without dispatch. This
does not turn v148 original boot plans into runtime authorization.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v152_fetch_opcode_witness import apply as apply_v152
from .apply_map02_v69_pcsx_rearmed import once


def patch_interpreter(source:str)->str:
    source=once(source,
        "static unsigned vh152_state,vh152_matches,vh152_fault;",
        "static unsigned vh152_state,vh152_matches,vh152_fault;\n"
        "static unsigned vh153_mutate_second_word;",
        "separate source-authored second-step mutation state")
    source=once(source,
        "static int vh152_before_dispatch(psxRegisters *regs,u32 pc,u32 fetched) {",
        "void vh153_arm_second_word_mutation(void){ vh153_mutate_second_word=1u; }\n"
        "static int vh152_before_dispatch(psxRegisters *regs,u32 pc,u32 fetched) {",
        "synthetic second-word mutation control")
    source=once(source,
        "    vh152_matches++;\n    return 1;",
        "    vh152_matches++;\n"
        "    /* The first word was verified. Change the SECOND word in PS1 RAM\n"
        "     * immediately before the first opcode is dispatched; the next\n"
        "     * real interpreter fetch must catch this changed guest code. */\n"
        "    if(vh153_mutate_second_word && vh152_matches==1u){\n"
        "        ((unsigned char *)regs->ptrs.psxM)[0x10004u]^=1u;\n"
        "        vh153_mutate_second_word=0u;\n"
        "    }\n"
        "    return 1;",
        "first success triggers one isolated second-word RAM mutation")
    source=once(source,
        "void vh152_disarm(void) {vh152_state=0u;}",
        "void vh152_disarm(void) {vh152_state=0u; vh153_mutate_second_word=0u;}",
        "clear mutation switch after native test")
    return source


def patch_frontend(source:str)->str:
    if "VH153_NATIVE_SECOND_WORD_REFUSED" in source:
        raise ValueError("v153 already applied")
    source=once(source,
        "\tint vh152_mutate_post_verify = 0;\n",
        "\tint vh152_mutate_post_verify = 0;\n"
        "\tint vh153_mutate_second_word = 0;\n"
        "\textern void vh153_arm_second_word_mutation(void);\n",
        "separate v153 second-opcode mutation CLI/ABI")
    source=once(source,
        '\t\telse if (!strcmp(argv[i], "--vh152-mutate-post-verify"))\n',
        '\t\telse if (!strcmp(argv[i], "--vh153-mutate-second-word"))\n'
        '\t\t\tvh153_mutate_second_word=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh152-mutate-post-verify"))\n',
        "opt-in mutation of second word only")
    source=once(source,
        "    if(vh152_mutate_post_verify &&\n",
        "    if(vh153_mutate_second_word &&\n"
        "       (!vh150_bounded_instructions || vh129_vblank_mode!=0 ||\n"
        "        vh152_mutate_post_verify)){\n"
        '        SysPrintf("VH153_INVALID_MODE_REFUSED\\n");\n'
        "        ClosePlugins();SysClose();menu_finish();plat_finish();return 57;\n"
        "    }\n"
        "    if(vh152_mutate_post_verify &&\n",
        "reject overlapping mutation flags and non-v129 launch")
    source=once(source,
        "            if(vh152_mutate_post_verify)\n"
        "                ((unsigned char *)psxRegs.ptrs.psxM)[0x10000u]^=1u;\n",
        "            if(vh152_mutate_post_verify)\n"
        "                ((unsigned char *)psxRegs.ptrs.psxM)[0x10000u]^=1u;\n"
        "            if(vh153_mutate_second_word)\n"
        "                vh153_arm_second_word_mutation();\n",
        "enable actual second fetched opcode mutation inside native observer")
    anchor=("            if(vh152_mutate_post_verify){\n"
            "                if(!faulted || witnessed!=0u){")
    replacement=(
        "            if(vh153_mutate_second_word){\n"
        "                if(!faulted || witnessed!=1u || vh150_steps()!=2u){\n"
        '                    SysPrintf("VH153_SECOND_WORD_FALSE_ACCEPT_REFUSED\\n");\n'
        "                    ClosePlugins();SysClose();menu_finish();plat_finish();return 57;\n"
        "                }\n"
        '                SysPrintf("VH153_NATIVE_SECOND_WORD_REFUSED"'
        '" matched=1 attempted=2 original_retail=0\\n");\n'
        "                ClosePlugins();SysClose();menu_finish();plat_finish();return 57;\n"
        "            }\n"+anchor)
    return once(source,anchor,replacement,
                "verify exactly one native MIPS word before second fetch refusal")


def apply(root:Path):
    old=apply_v152(root)
    base=root.resolve()
    core=base/"libpcsxcore/psxinterpreter.c"
    frontend=base/"frontend/main.c"
    core.write_text(patch_interpreter(core.read_text()))
    frontend.write_text(patch_frontend(frontend.read_text()))
    return dict(old,
        v153_second_word_mutated_after_first_dispatch_witness=True,
        v153_exactly_one_source_word_accepted=True,
        v153_second_word_refused_before_dispatch=True,
        v153_original_retail_executed=False,
        v153_MAP02_rendered=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
