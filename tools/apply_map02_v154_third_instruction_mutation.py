#!/usr/bin/env python3
"""v154: after two verified native guest opcodes, refuse changed third.

Only opt-in, source-generated v129 synthetic three-word PCSX diagnostics.
The source-pinned v151 SHA-256 and v152 fetched word witness still run.
No user-owned original game MIPS content is executed.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v153_second_instruction_mutation import apply as apply_v153
from .apply_map02_v69_pcsx_rearmed import once


def patch_interpreter(source: str) -> str:
    source=once(source,
        "static unsigned vh153_mutate_second_word;",
        "static unsigned vh153_mutate_second_word;\n"
        "static unsigned vh154_mutate_third_word;",
        "declare independent third synthetic instruction mutation")
    source=once(source,
        "void vh153_arm_second_word_mutation(void){ vh153_mutate_second_word=1u; }\n",
        "void vh153_arm_second_word_mutation(void){ vh153_mutate_second_word=1u; }\n"
        "void vh154_arm_third_word_mutation(void){ vh154_mutate_third_word=1u; }\n",
        "declare precise third synthetic instruction negative-test arming")
    source=once(source,
        "        vh153_mutate_second_word=0u;\n"
        "    }\n"
        "    return 1;",
        "        vh153_mutate_second_word=0u;\n"
        "    }\n"
        "    /* Both legitimate synthetic MIPS words passed pre-dispatch checks.\n"
        "     * Mutate word three in guest RAM before the next native fetch. */\n"
        "    if(vh154_mutate_third_word && vh152_matches==2u){\n"
        "        ((unsigned char *)regs->ptrs.psxM)[0x10008u]^=1u;\n"
        "        vh154_mutate_third_word=0u;\n"
        "    }\n"
        "    return 1;",
        "mutate only after two verified synthetic opcodes")
    source=once(source,
        "void vh152_disarm(void) {vh152_state=0u; vh153_mutate_second_word=0u;}",
        "void vh152_disarm(void) {vh152_state=0u; "
        "vh153_mutate_second_word=0u; vh154_mutate_third_word=0u;}",
        "reset both mutation modes when native witness disarms")
    return source


def patch_frontend(source: str) -> str:
    if "VH154_NATIVE_THIRD_WORD_REFUSED" in source:
        raise ValueError("v154 third-opcode patch already present")
    source=once(source,
        "\tint vh153_mutate_second_word = 0;\n",
        "\tint vh153_mutate_second_word = 0;\n"
        "\tint vh154_mutate_third_word = 0;\n"
        "\textern void vh154_arm_third_word_mutation(void);\n",
        "v154 explicit, separately controlled synthetic mutation")
    source=once(source,
        '\t\telse if (!strcmp(argv[i], "--vh153-mutate-second-word"))\n',
        '\t\telse if (!strcmp(argv[i], "--vh154-mutate-third-word"))\n'
        '\t\t\tvh154_mutate_third_word=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh153-mutate-second-word"))\n',
        "parse third-word test CLI option")
    source=once(source,
        "    if(vh153_mutate_second_word &&\n",
        "    if(vh154_mutate_third_word &&\n"
        "       (!vh150_bounded_instructions || vh129_vblank_mode!=0 ||\n"
        "        vh152_mutate_post_verify || vh153_mutate_second_word)){\n"
        '        SysPrintf("VH154_INVALID_MODE_REFUSED\\n");\n'
        "        ClosePlugins();SysClose();menu_finish();plat_finish();return 58;\n"
        "    }\n"
        "    if(vh153_mutate_second_word &&\n",
        "refuse third-word mutation outside the isolated synthetic profile")
    source=once(source,
        "            if(vh153_mutate_second_word)\n"
        "                vh153_arm_second_word_mutation();\n",
        "            if(vh153_mutate_second_word)\n"
        "                vh153_arm_second_word_mutation();\n"
        "            if(vh154_mutate_third_word)\n"
        "                vh154_arm_third_word_mutation();\n",
        "arm third-word mutation only after full v151 RAM identity check")
    anchor=("            if(vh153_mutate_second_word){\n"
            "                if(!faulted || witnessed!=1u || vh150_steps()!=2u){")
    source=once(source,anchor,
        "            if(vh154_mutate_third_word){\n"
        "                if(!faulted || witnessed!=2u || vh150_steps()!=3u){\n"
        '                    SysPrintf("VH154_THIRD_WORD_FALSE_ACCEPT_REFUSED\\n");\n'
        "                    ClosePlugins();SysClose();menu_finish();plat_finish();return 58;\n"
        "                }\n"
        '                SysPrintf("VH154_NATIVE_THIRD_WORD_REFUSED"'
        '" matched=2 attempted=3 original_retail=0\\n");\n'
        "                ClosePlugins();SysClose();menu_finish();plat_finish();return 58;\n"
        "            }\n"+anchor,
        "assert exactly two instructions accepted and third denied in native PCSX")
    return source


def apply(root: Path):
    previous=apply_v153(root)
    base=root.resolve()
    core=base/"libpcsxcore/psxinterpreter.c"
    frontend=base/"frontend/main.c"
    core.write_text(patch_interpreter(core.read_text()))
    frontend.write_text(patch_frontend(frontend.read_text()))
    return dict(previous,
        v154_two_source_mips_instructions_accepted=True,
        v154_third_word_mutated_between_dispatches=True,
        v154_third_instruction_refused_pre_dispatch=True,
        v154_original_game_executed=False,
        v154_original_MAP02_rendered=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
