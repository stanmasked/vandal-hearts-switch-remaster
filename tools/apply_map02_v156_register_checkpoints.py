#!/usr/bin/env python3
"""v156: observe real native MIPS-I register effects between four synthetic opcodes.

The v155 four-opcode mode is required. Source-derived LUI/ORI expectations
are checked immediately before dispatch of instructions 2, 3 and 4; a
test-only t0 flip before instruction two must be refused after one dispatch.
No retail game executable is accepted or run by these new checks.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v155_four_instruction_native import (
    apply as apply_v155, four_source_words
)
from .apply_map02_v69_pcsx_rearmed import once


def expected_register_checkpoints():
    w0,w1,w2,w3=four_source_words()
    def require_lui(word,reg):
        if (word>>26)!=15 or (word>>21)&31 or (word>>16)&31!=reg:
            raise ValueError("v156 expected a source-authored MIPS LUI")
        return (word&0xffff)<<16
    def require_ori(word,reg):
        if (word>>26)!=13 or (word>>21)&31!=reg or (word>>16)&31!=reg:
            raise ValueError("v156 expected a source-authored MIPS ORI")
        return word&0xffff
    t0_lui=require_lui(w0,8)
    t0_final=t0_lui|require_ori(w1,8)
    t1_lui=require_lui(w2,9)
    t1_final=t1_lui|require_ori(w3,9)
    if (t0_lui,t0_final,t1_lui,t1_final)!=(
            0x1f800000,0x1f801810,0xe3000000,0xe3000000):
        raise ValueError("v156 source-generated register effects changed")
    return t0_lui,t0_final,t1_lui,t1_final


def patch_interpreter(source: str) -> str:
    t0_lui,t0_final,t1_lui,_=expected_register_checkpoints()
    source=once(source,
        "static unsigned vh155_four_enabled,vh155_mutate_fourth_word;",
        "static unsigned vh155_four_enabled,vh155_mutate_fourth_word;\n"
        "static unsigned vh156_check_regs,vh156_corrupt_t0_second;",
        "declare register-observability witness state")
    anchor="static int vh152_before_dispatch(psxRegisters *regs,u32 pc,u32 fetched) {"
    addition=(
        "int vh156_arm_register_check(unsigned corrupt_t0){\n"
        "    if(vh152_state!=1u || vh152_matches!=0u ||\n"
        "       !vh155_four_enabled || vh156_check_regs) return -1;\n"
        "    vh156_check_regs=1u;\n"
        "    vh156_corrupt_t0_second=corrupt_t0 ? 1u : 0u;\n"
        "    return 0;\n"
        "}\n"
        "static int vh156_verify_previous_effects(psxRegisters *regs,u32 pc){\n"
        "    if(!vh156_check_regs) return 1;\n"
        "    /* This negative test changes the host-visible t0 after the\n"
        "     * FIRST genuine native LUI instruction and BEFORE the second\n"
        "     * synthetic opcode can be dispatched. */\n"
        "    if(pc==0x80010004u){\n"
        "        if(vh156_corrupt_t0_second){\n"
        "            regs->GPR.r[8]^=1u;\n"
        "            vh156_corrupt_t0_second=0u;\n"
        "        }\n"
        f"        return regs->GPR.r[8]==0x{t0_lui:08x}u;\n"
        "    }\n"
        "    if(pc==0x80010008u)\n"
        f"        return regs->GPR.r[8]==0x{t0_final:08x}u;\n"
        "    if(pc==0x8001000cu)\n"
        f"        return regs->GPR.r[8]==0x{t0_final:08x}u &&\n"
        f"               regs->GPR.r[9]==0x{t1_lui:08x}u;\n"
        "    return 1;\n"
        "}\n"
    )
    source=once(source,anchor,addition+anchor,
                "check native prior MIPS register effects before opcode fetch dispatch")
    source=once(source,
        "    idx=(pc-0x80010000u)/4u;",
        "    if(!vh156_verify_previous_effects(regs,pc)) goto refuse;\n"
        "    idx=(pc-0x80010000u)/4u;",
        "insert fail-closed register checkpoint before v152 opcode witness")
    source=once(source,
        "vh155_four_enabled=0u; vh155_mutate_fourth_word=0u;}",
        "vh155_four_enabled=0u; vh155_mutate_fourth_word=0u;\n"
        "    vh156_check_regs=0u; vh156_corrupt_t0_second=0u;}",
        "reset synthetic register witness on disarm")
    return source


def patch_frontend(source: str) -> str:
    if "VH156_NATIVE_REGISTER_EFFECTS_PASS" in source:
        raise ValueError("v156 patch already installed")
    t0_lui,t0_final,t1_lui,t1_final=expected_register_checkpoints()
    source=once(source,
        "\tint vh155_mutate_fourth_word = 0;\n",
        "\tint vh155_mutate_fourth_word = 0;\n"
        "\tint vh156_verify_register_effects = 0;\n"
        "\tint vh156_corrupt_t0_second = 0;\n"
        "\textern int vh156_arm_register_check(unsigned);\n",
        "v156 opt-in register checkpoint controls")
    source=once(source,
        '\t\telse if (!strcmp(argv[i], "--vh155-four-instructions"))\n',
        '\t\telse if (!strcmp(argv[i], "--vh156-verify-register-effects"))\n'
        '\t\t\tvh156_verify_register_effects=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh156-corrupt-t0-second"))\n'
        '\t\t\tvh156_corrupt_t0_second=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh155-four-instructions"))\n',
        "v156 synthetic-only new options")
    source=once(source,
        "    if((vh155_four_instructions || vh155_mutate_fourth_word) &&\n",
        "    if((vh156_verify_register_effects || vh156_corrupt_t0_second) &&\n"
        "       (!vh156_verify_register_effects || !vh155_four_instructions ||\n"
        "        !vh150_bounded_instructions || vh129_vblank_mode!=0 ||\n"
        "        vh152_mutate_post_verify || vh153_mutate_second_word ||\n"
        "        vh154_mutate_third_word || vh155_mutate_fourth_word)){\n"
        '        SysPrintf("VH156_INVALID_MODE_REFUSED\\n");\n'
        "        ClosePlugins();SysClose();menu_finish();plat_finish();return 60;\n"
        "    }\n"
        "    if((vh155_four_instructions || vh155_mutate_fourth_word) &&\n",
        "deny register-check mode without verified synthetic four-step execution")
    source=once(source,
        "                if(vh155_mutate_fourth_word)\n"
        "                    vh155_arm_fourth_mutation();\n",
        "                if(vh155_mutate_fourth_word)\n"
        "                    vh155_arm_fourth_mutation();\n"
        "                if(vh156_verify_register_effects &&\n"
        "                   vh156_arm_register_check(\n"
        "                       (unsigned)vh156_corrupt_t0_second)!=0){\n"
        '                    SysPrintf("VH156_REGISTER_ARM_REFUSED\\n");\n'
        "                    ClosePlugins();SysClose();menu_finish();plat_finish();return 60;\n"
        "                }\n",
        "arm native register witness after code digest and before first opcode")
    anchor="                if(vh155_mutate_fourth_word){\n"
    addition=(
        "                if(vh156_verify_register_effects){\n"
        "                    if(vh156_corrupt_t0_second){\n"
        "                        if(!faulted || witnessed!=1u ||\n"
        "                           steps!=2u || reason!=0u){\n"
        '                            SysPrintf("VH156_T0_FALSE_ACCEPT_REFUSED\\n");\n'
        "                            ClosePlugins();SysClose();menu_finish();plat_finish();return 60;\n"
        "                        }\n"
        '                        SysPrintf("VH156_NATIVE_REGISTER_CORRUPTION_REFUSED"'
        '" matched=1 attempted=2 original_retail=0\\n");\n'
        "                        ClosePlugins();SysClose();menu_finish();plat_finish();return 60;\n"
        "                    }\n"
        "                    if(faulted || witnessed!=4u || steps!=4u ||\n"
        "                       reason!=1u ||\n"
        f"                       psxRegs.GPR.r[8]!=0x{t0_final:08x}u ||\n"
        f"                       psxRegs.GPR.r[9]!=0x{t1_final:08x}u){{\n"
        '                        SysPrintf("VH156_REGISTER_EFFECTS_REFUSED\\n");\n'
        "                        ClosePlugins();SysClose();menu_finish();plat_finish();return 60;\n"
        "                    }\n"
        '                    SysPrintf("VH156_NATIVE_REGISTER_EFFECTS_PASS"'
        '" matched=4 capped=1 original_retail=0\\n");\n'
        "                    ClosePlugins();SysClose();menu_finish();plat_finish();return 0;\n"
        "                }\n"
    )
    # Distinguish frontend mode from earlier C witness's C function state.
    # This anchor occurs exactly once in the v155 frontend success path.
    source=once(source,anchor,addition+anchor,
                "bind native register values to accepted synthetic code effects")
    return source


def apply(root: Path):
    prior=apply_v155(root)
    base=root.resolve()
    interpreter=base/"libpcsxcore/psxinterpreter.c"
    frontend=base/"frontend/main.c"
    interpreter.write_text(patch_interpreter(interpreter.read_text()))
    frontend.write_text(patch_frontend(frontend.read_text()))
    return dict(prior,
        v156_native_register_effects_verified=True,
        v156_register_corruption_before_second_refused=True,
        v156_source_derived_register_state=True,
        v156_previous_four_step_and_mutation_modes_unchanged=True,
        v156_original_game_not_executed=True,
        v156_original_map02_not_rendered=True)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
