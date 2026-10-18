#!/usr/bin/env python3
"""v155: four source-authored native MIPS opcodes, quota four, opt-in only.

Layer this patch on verified v154. The original 3-instruction test and all
mutation modes remain unmodified by default. The new positive path executes
four verified v129 *synthetic* instructions and halts before instruction 5.
The new negative path changes word 4 after three successful dispatches and
requires an immediate pre-dispatch refusal. No retail game runtime support.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v154_third_instruction_mutation import apply as apply_v154
from .apply_map02_v69_pcsx_rearmed import once
from .apply_map02_v152_fetch_opcode_witness import expected_first_three_words
from .make_map02_v129_four_vblank_exe import build


def four_source_words():
    raw,*_=build()
    if len(raw)!=10240 or raw[:8]!=b"PS-X EXE" or raw[0x4c:0x54]!=b"VH129SY!":
        raise ValueError("v155 requires the pinned source-generated v129 EXE")
    words=tuple(int.from_bytes(raw[2048+i*4:2052+i*4],"little")
                for i in range(4))
    if len(words)!=4 or words[:3]!=expected_first_three_words() or not all(words):
        raise ValueError("v155 source prefix changed")
    # All four instructions must be straight-line, not J/JAL/branch/COP.
    for word in words:
        op=word>>26
        if op in (1,2,3,4,5,6,7,16,17,18,19):
            raise ValueError("v155 four-word demonstration is not straight-line")
    return words


def patch_interpreter(source: str) -> str:
    three=expected_first_three_words()
    four=four_source_words()
    prior="static const u32 vh152_words[3]={"+",".join("0x%08xu"%w for w in three)+"};"
    expanded="static const u32 vh152_words[4]={"+",".join("0x%08xu"%w for w in four)+"};"
    source=once(source,prior,expanded,"source-authored four instruction digest witness")
    source=once(source,
        "static unsigned vh154_mutate_third_word;",
        "static unsigned vh154_mutate_third_word;\n"
        "static unsigned vh155_four_enabled,vh155_mutate_fourth_word;",
        "v155 four-word gate and negative mutation state")
    source=once(source,
        "static int vh152_before_dispatch(psxRegisters *regs,u32 pc,u32 fetched) {",
        "int vh155_enable_four(void){\n"
        "    if(vh152_state!=1u || vh152_matches!=0u || vh155_four_enabled)\n"
        "        return -1;\n"
        "    vh155_four_enabled=1u;\n"
        "    return 0;\n"
        "}\n"
        "void vh155_arm_fourth_mutation(void){\n"
        "    if(vh155_four_enabled) vh155_mutate_fourth_word=1u;\n"
        "}\n"
        "static int vh152_before_dispatch(psxRegisters *regs,u32 pc,u32 fetched) {",
        "v155 gated native four-word mode")
    source=once(source,
        "    if(pc<0x80010000u || pc>=0x8001000cu || (pc&3u) ||\n"
        "       idx>=3u || idx!=vh152_matches || !regs->ptrs.psxM ||",
        "    if(pc<0x80010000u ||\n"
        "       pc>=0x80010000u+(vh155_four_enabled ? 16u : 12u) || (pc&3u) ||\n"
        "       idx>=(vh155_four_enabled ? 4u : 3u) ||\n"
        "       idx!=vh152_matches || !regs->ptrs.psxM ||",
        "preserve three-opcode path, explicitly unlock 4th only for v155")
    source=once(source,
        "        vh154_mutate_third_word=0u;\n"
        "    }\n"
        "    return 1;",
        "        vh154_mutate_third_word=0u;\n"
        "    }\n"
        "    /* Mutate word 4 strictly after the first three correct words. */\n"
        "    if(vh155_four_enabled && vh155_mutate_fourth_word &&\n"
        "       vh152_matches==3u){\n"
        "        ((unsigned char *)regs->ptrs.psxM)[0x1000cu]^=1u;\n"
        "        vh155_mutate_fourth_word=0u;\n"
        "    }\n"
        "    return 1;",
        "negative after-third-before-fourth native code alteration")
    source=once(source,
        "vh154_mutate_third_word=0u;}",
        "vh154_mutate_third_word=0u;\n"
        "    vh155_four_enabled=0u; vh155_mutate_fourth_word=0u;}",
        "reset extended native witness after each test")
    return source


def patch_frontend(source: str) -> str:
    if "VH155_NATIVE_FOUR_STEP_PASS" in source:
        raise ValueError("v155 applied twice")
    source=once(source,
        "\tint vh154_mutate_third_word = 0;\n",
        "\tint vh154_mutate_third_word = 0;\n"
        "\tint vh155_four_instructions = 0;\n"
        "\tint vh155_mutate_fourth_word = 0;\n"
        "\textern int vh155_enable_four(void);\n"
        "\textern void vh155_arm_fourth_mutation(void);\n",
        "v155 explicit four-word CLI and ABI")
    source=once(source,
        '\t\telse if (!strcmp(argv[i], "--vh154-mutate-third-word"))\n',
        '\t\telse if (!strcmp(argv[i], "--vh155-four-instructions"))\n'
        '\t\t\tvh155_four_instructions=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh155-mutate-fourth-word"))\n'
        '\t\t\tvh155_mutate_fourth_word=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh154-mutate-third-word"))\n',
        "v155 four-word-only opt-in options")
    source=once(source,
        "    if(vh154_mutate_third_word &&\n",
        "    if((vh155_four_instructions || vh155_mutate_fourth_word) &&\n"
        "       (!vh155_four_instructions || !vh150_bounded_instructions ||\n"
        "        vh129_vblank_mode!=0 || vh152_mutate_post_verify ||\n"
        "        vh153_mutate_second_word || vh154_mutate_third_word)){\n"
        '        SysPrintf("VH155_INVALID_MODE_REFUSED\\n");\n'
        "        ClosePlugins();SysClose();menu_finish();plat_finish();return 59;\n"
        "    }\n"
        "    if(vh154_mutate_third_word &&\n",
        "reject mixed or non-synthetic modes before any guest execution")
    source=once(source,
        "            if(vh154_mutate_third_word)\n"
        "                vh154_arm_third_word_mutation();\n",
        "            if(vh154_mutate_third_word)\n"
        "                vh154_arm_third_word_mutation();\n"
        "            if(vh155_four_instructions){\n"
        "                if(vh155_enable_four()!=0){\n"
        '                    SysPrintf("VH155_FOUR_ARM_REFUSED\\n");\n'
        "                    ClosePlugins();SysClose();menu_finish();plat_finish();return 59;\n"
        "                }\n"
        "                if(vh155_mutate_fourth_word)\n"
        "                    vh155_arm_fourth_mutation();\n"
        "            }\n",
        "enable first-ever four-instruction witness only after v151 full RAM SHA")
    source=once(source,
        "if(vh150_arm(0x80010000u,0x80012000u,3u)!=0)",
        "if(vh150_arm(0x80010000u,0x80012000u,\n"
        "                         vh155_four_instructions ? 4u : 3u)!=0)",
        "native instruction budget increases to 4 only under v155 opt-in")
    source=once(source,
        "            vh152_disarm();\n"
        "            if(vh154_mutate_third_word){",
        "            vh152_disarm();\n"
        "            if(vh155_four_instructions){\n"
        "                unsigned steps=vh150_steps();\n"
        "                unsigned reason=vh150_stop_reason();\n"
        "                vh150_disarm();\n"
        "                if(vh155_mutate_fourth_word){\n"
        "                    if(!faulted || witnessed!=3u || steps!=4u ||\n"
        "                       reason!=0u){\n"
        '                        SysPrintf("VH155_FOURTH_FALSE_ACCEPT_REFUSED\\n");\n'
        "                        ClosePlugins();SysClose();menu_finish();plat_finish();return 59;\n"
        "                    }\n"
        '                    SysPrintf("VH155_NATIVE_FOURTH_WORD_REFUSED"'
        '" matched=3 attempted=4 original_retail=0\\n");\n'
        "                    ClosePlugins();SysClose();menu_finish();plat_finish();return 59;\n"
        "                }\n"
        "                if(faulted || witnessed!=4u || steps!=4u || reason!=1u){\n"
        '                    SysPrintf("VH155_FOUR_STEP_REFUSED\\n");\n'
        "                    ClosePlugins();SysClose();menu_finish();plat_finish();return 59;\n"
        "                }\n"
        '                SysPrintf("VH155_NATIVE_FOUR_STEP_PASS"'
        '" steps=4 capped=1 synthetic_only=1 original_retail=0\\n");\n'
        "                ClosePlugins();SysClose();menu_finish();plat_finish();return 0;\n"
        "            }\n"
        "            if(vh154_mutate_third_word){",
        "v155 native positive and fourth-word mutation proof before old branches")
    return source


def apply(root: Path):
    old=apply_v154(root)
    base=root.resolve()
    interp=base/"libpcsxcore/psxinterpreter.c"
    frontend=base/"frontend/main.c"
    interp.write_text(patch_interpreter(interp.read_text()))
    frontend.write_text(patch_frontend(frontend.read_text()))
    return dict(old,
        v155_source_bound_four_opcodes=True,
        v155_native_four_step_quota=True,
        v155_fourth_code_mutation_pre_dispatch_refused=True,
        v155_old_three_word_native_proofs_preserved=True,
        v155_original_game_executed=False,
        v155_original_map02_not_rendered=True)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
