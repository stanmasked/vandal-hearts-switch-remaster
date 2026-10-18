#!/usr/bin/env python3
"""v157: verify fourth synthetic MIPS instruction refuses changed t1 register.

Stacks on verified v156 with native PCSX ReARMed register checkpoints. The
only new run mutates t1 after three genuine synthetic LUI/ORI opcodes, then
refuses the fourth opcode before dispatch. Retail-original MIPS remains off.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v156_register_checkpoints import apply as apply_v156
from .apply_map02_v69_pcsx_rearmed import once


def patch_interpreter(source: str) -> str:
    source=once(source,
        "static unsigned vh156_check_regs,vh156_corrupt_t0_second;",
        "static unsigned vh156_check_regs,vh156_corrupt_t0_second;\n"
        "static unsigned vh157_corrupt_t1_fourth;",
        "add separate fourth-instruction GPR t1 corruption latch")
    source=once(source,
        "static int vh156_verify_previous_effects(psxRegisters *regs,u32 pc){",
        "void vh157_arm_t1_fourth(void){\n"
        "    if(vh156_check_regs && vh155_four_enabled &&\n"
        "       vh152_state==1u && vh152_matches==0u)\n"
        "        vh157_corrupt_t1_fourth=1u;\n"
        "}\n"
        "static int vh156_verify_previous_effects(psxRegisters *regs,u32 pc){",
        "declare precise fourth-opcode-only synthetic register corruption")
    source=once(source,
        "    if(pc==0x8001000cu)\n"
        "        return regs->GPR.r[8]==0x1f801810u &&\n"
        "               regs->GPR.r[9]==0xe3000000u;",
        "    if(pc==0x8001000cu){\n"
        "        /* Three genuine instructions passed, but no fourth dispatch.\n"
        "         * Corrupt the t1 register just before register verification. */\n"
        "        if(vh157_corrupt_t1_fourth){\n"
        "            regs->GPR.r[9]^=1u;\n"
        "            vh157_corrupt_t1_fourth=0u;\n"
        "        }\n"
        "        return regs->GPR.r[8]==0x1f801810u &&\n"
        "               regs->GPR.r[9]==0xe3000000u;\n"
        "    }",
        "reject mutated fourth-instruction t1 before opcode dispatch")
    source=once(source,
        "vh156_check_regs=0u; vh156_corrupt_t0_second=0u;}",
        "vh156_check_regs=0u; vh156_corrupt_t0_second=0u;\n"
        "    vh157_corrupt_t1_fourth=0u;}",
        "clear v157 negative mode when native MIPS observer disarms")
    return source


def patch_frontend(source: str) -> str:
    if "VH157_NATIVE_T1_FOURTH_REFUSED" in source:
        raise ValueError("v157 already installed")
    source=once(source,
        "\tint vh156_corrupt_t0_second = 0;\n",
        "\tint vh156_corrupt_t0_second = 0;\n"
        "\tint vh157_corrupt_t1_fourth = 0;\n"
        "\textern void vh157_arm_t1_fourth(void);\n",
        "opt-in synthetic-only v157 CLI state and ABI")
    source=once(source,
        '\t\telse if (!strcmp(argv[i], "--vh156-corrupt-t0-second"))\n',
        '\t\telse if (!strcmp(argv[i], "--vh157-corrupt-t1-fourth"))\n'
        '\t\t\tvh157_corrupt_t1_fourth=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh156-corrupt-t0-second"))\n',
        "parse fourth synthetic register mutation option")
    source=once(source,
        "    if((vh156_verify_register_effects || vh156_corrupt_t0_second) &&\n",
        "    if(vh157_corrupt_t1_fourth &&\n"
        "       (!vh156_verify_register_effects || vh156_corrupt_t0_second ||\n"
        "        !vh155_four_instructions || !vh150_bounded_instructions ||\n"
        "        vh129_vblank_mode!=0 || vh152_mutate_post_verify ||\n"
        "        vh153_mutate_second_word || vh154_mutate_third_word ||\n"
        "        vh155_mutate_fourth_word)){\n"
        '        SysPrintf("VH157_INVALID_MODE_REFUSED\\n");\n'
        "        ClosePlugins();SysClose();menu_finish();plat_finish();return 61;\n"
        "    }\n"
        "    if((vh156_verify_register_effects || vh156_corrupt_t0_second) &&\n",
        "deny unverified and mixed GPR mutation modes")
    anchor=(
        "                if(vh156_verify_register_effects &&\n"
        "                   vh156_arm_register_check(\n"
        "                       (unsigned)vh156_corrupt_t0_second)!=0){\n"
        '                    SysPrintf("VH156_REGISTER_ARM_REFUSED\\n");\n'
        "                    ClosePlugins();SysClose();menu_finish();plat_finish();return 60;\n"
        "                }\n"
    )
    source=once(source,anchor,
        anchor+
        "                if(vh157_corrupt_t1_fourth)\n"
        "                    vh157_arm_t1_fourth();\n",
        "arm new t1 mutation only after full v151 RAM SHA and v156 GPR observer")
    source=once(source,
        "                if(vh156_verify_register_effects){\n"
        "                    if(vh156_corrupt_t0_second){",
        "                if(vh156_verify_register_effects){\n"
        "                    if(vh157_corrupt_t1_fourth){\n"
        "                        if(!faulted || witnessed!=3u ||\n"
        "                           steps!=4u || reason!=0u){\n"
        '                            SysPrintf("VH157_T1_FALSE_ACCEPT_REFUSED\\n");\n'
        "                            ClosePlugins();SysClose();menu_finish();plat_finish();return 61;\n"
        "                        }\n"
        '                        SysPrintf("VH157_NATIVE_T1_FOURTH_REFUSED"'
        '" matched=3 attempted=4 original_retail=0\\n");\n'
        "                        ClosePlugins();SysClose();menu_finish();plat_finish();return 61;\n"
        "                    }\n"
        "                    if(vh156_corrupt_t0_second){",
        "require exactly three native opcodes and fourth pre-dispatch refusal")
    return source


def apply(root: Path):
    previous=apply_v156(root)
    base=root.resolve()
    interp=base/"libpcsxcore/psxinterpreter.c"
    main=base/"frontend/main.c"
    interp.write_text(patch_interpreter(interp.read_text()))
    main.write_text(patch_frontend(main.read_text()))
    return dict(previous,
        v157_three_native_opcodes_precede_t1_corruption=True,
        v157_fourth_guest_opcode_refused_before_dispatch=True,
        v157_v156_register_success_mode_preserved=True,
        v157_original_retail_execution_disabled=True,
        v157_MAP02_rendered=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
