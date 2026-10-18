#!/usr/bin/env python3
"""v152 native fetched-word witness after SHA-256, before opcode dispatch.

Only the v129 self-authored synthetic first three MIPS instructions are
supported. Retained v151 full payload SHA-256 is checked before the witness
arms. A negative opt-in changes PS1 RAM AFTER that digest check; the native
interpreter must refuse BEFORE dispatching the altered MIPS opcode.
"""
from __future__ import annotations

from pathlib import Path

from .apply_map02_v151_native_ram_identity import apply as apply_v151
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v129_four_vblank_exe import build


def expected_first_three_words():
    payload,*_=build()
    if len(payload)!=10240 or payload[0x4c:0x54]!=b"VH129SY!":
        raise ValueError("v152 refuses changed synthetic guest source")
    words=tuple(int.from_bytes(payload[2048+i*4:2052+i*4],"little")
                for i in range(3))
    if len(words)!=3 or any(x==0 for x in words):
        raise ValueError("v152 refuses unexpected synthetic first three instructions")
    return words


def native_opcode_witness():
    words=expected_first_three_words()
    return r'''
#ifdef VH_MAP02_V66_PCSX_PROBE
/* Source-authored three-word witness. Only active in v150's explicit
 * synthetic-only diagnostic, never for user-owned PS-X game content.
 * Both fetched opcode and guest physical RAM must match the source. */
static const u32 vh152_words[3]={V152_SOURCE_WORDS};
static unsigned vh152_state,vh152_matches,vh152_fault;
int vh152_arm(void) {
    if(vh152_state!=0u) return -1;
    vh152_state=1u; vh152_matches=0u; vh152_fault=0u;
    return 0;
}
static int vh152_before_dispatch(psxRegisters *regs,u32 pc,u32 fetched) {
    unsigned idx,i;
    u32 physical;
    const unsigned char *mem;
    if(vh152_state==0u) return 1;
    if(vh152_state!=1u) return 0;
    idx=(pc-0x80010000u)/4u;
    if(pc<0x80010000u || pc>=0x8001000cu || (pc&3u) ||
       idx>=3u || idx!=vh152_matches || !regs->ptrs.psxM ||
       fetched!=vh152_words[idx]) goto refuse;
    mem=(const unsigned char *)regs->ptrs.psxM;
    physical=0x10000u+idx*4u;
    for(i=0u;i<4u;i++)
        if(mem[physical+i]!=(unsigned char)(vh152_words[idx]>>(i*8u)))
            goto refuse;
    vh152_matches++;
    return 1;
refuse:
    vh152_state=2u; vh152_fault=1u;
    regs->stop=1; regs->branchSeen=1;
    return 0;
}
unsigned vh152_matched_count(void) {return vh152_matches;}
unsigned vh152_faulted(void) {return vh152_fault;}
void vh152_disarm(void) {vh152_state=0u;}
#endif

'''.replace("V152_SOURCE_WORDS",
            ",".join("0x%08xu"%w for w in words))


def patch_interpreter(source: str):
    source=once(source,
        "static inline void execI_(\n",
        native_opcode_witness()+"static inline void execI_(\n",
        "install test-only actual fetched MIPS instruction witness")
    anchor=("\tregs->code = fetch(regs, memRLUT, pc);\n"
            "\tpsxBSC[regs->code >> 26](regs, regs->code);")
    if source.count(anchor)!=2:
        raise ValueError("refusing pinned interpreter without two opcode dispatch paths")
    guarded=(
        "\tregs->code = fetch(regs, memRLUT, pc);\n"
        "#ifdef VH_MAP02_V66_PCSX_PROBE\n"
        "\tif(!vh152_before_dispatch(regs,pc,regs->code)) return;\n"
        "#endif\n"
        "\tpsxBSC[regs->code >> 26](regs, regs->code);"
    )
    return source.replace(anchor,guarded)


def patch_frontend(source: str):
    if "VH152_NATIVE_FETCH_TAMPER_REFUSED" in source:
        raise ValueError("v152 already patched into frontend")
    source=once(source,
        "\tint vh150_bounded_instructions = 0;\n",
        "\tint vh150_bounded_instructions = 0;\n"
        "\tint vh152_mutate_post_verify = 0;\n"
        "\textern int vh152_arm(void);\n"
        "\textern unsigned vh152_faulted(void);\n"
        "\textern unsigned vh152_matched_count(void);\n"
        "\textern void vh152_disarm(void);\n",
        "v152 explicit private synthetic-mode controls")
    source=once(source,
        '\t\telse if (!strcmp(argv[i], "--vh150-bounded-instructions"))\n',
        '\t\telse if (!strcmp(argv[i], "--vh152-mutate-post-verify"))\n'
        '\t\t\tvh152_mutate_post_verify=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh150-bounded-instructions"))\n',
        "test-only tamper flag")
    source=once(source,
        "    if(vh150_bounded_instructions && vh129_vblank_mode!=0){\n",
        "    if(vh152_mutate_post_verify &&\n"
        "       (!vh150_bounded_instructions || vh129_vblank_mode!=0)){\n"
        '        SysPrintf("VH152_INVALID_MODE_REFUSED\\n");\n'
        "        ClosePlugins();SysClose();menu_finish();plat_finish();return 56;\n"
        "    }\n"
        "    if(vh150_bounded_instructions && vh129_vblank_mode!=0){\n",
        "no mutation without valid synthetic v150 mode")
    anchor="            if(vh150_arm(0x80010000u,0x80012000u,3u)!=0){"
    replacement=(
        "            /* v151 has verified loaded 8 KiB guest RAM just above.\n"
        "             * Now arm actual fetch/dispatch, before any guest opcode.\n"
        "             * This mutation is possible ONLY under synthetic CLI.\n"
        "             */\n"
        "            if(vh152_arm()!=0){\n"
        '                SysPrintf("VH152_NATIVE_ARM_REFUSED\\n");\n'
        "                ClosePlugins();SysClose();menu_finish();plat_finish();return 56;\n"
        "            }\n"
        "            if(vh152_mutate_post_verify)\n"
        "                ((unsigned char *)psxRegs.ptrs.psxM)[0x10000u]^=1u;\n"
        +anchor
    )
    source=once(source,anchor,replacement,
                "deliberate synthetic mutation after RAM SHA and before fetch")
    anchor=("        if(vh150_bounded_instructions){\n"
            "            unsigned count=vh150_steps();")
    replacement=(
        "        if(vh150_bounded_instructions){\n"
        "            unsigned witnessed=vh152_matched_count();\n"
        "            unsigned faulted=vh152_faulted();\n"
        "            vh152_disarm();\n"
        "            if(vh152_mutate_post_verify){\n"
        "                if(!faulted || witnessed!=0u){\n"
        '                    SysPrintf("VH152_NATIVE_UNSAFE_ACCEPT_REFUSED\\n");\n'
        "                    ClosePlugins();SysClose();menu_finish();plat_finish();return 56;\n"
        "                }\n"
        '                SysPrintf("VH152_NATIVE_FETCH_TAMPER_REFUSED"'
        '" matched=0 original_retail=0\\n");\n'
        "                ClosePlugins();SysClose();menu_finish();plat_finish();return 56;\n"
        "            }\n"
        "            if(faulted || witnessed!=3u){\n"
        '                SysPrintf("VH152_NATIVE_FETCH_REFUSED\\n");\n'
        "                ClosePlugins();SysClose();menu_finish();plat_finish();return 56;\n"
        "            }\n"
        "            unsigned count=vh150_steps();"
    )
    return once(source,anchor,replacement,
                "separate native tamper refusal from the v150 three-step success")


def apply(root:Path):
    prior=apply_v151(root)
    core=root.resolve()/"libpcsxcore/psxinterpreter.c"
    main=root.resolve()/"frontend/main.c"
    core.write_text(patch_interpreter(core.read_text()))
    main.write_text(patch_frontend(main.read_text()))
    return dict(prior,
        v152_native_actual_fetched_opcodes_source_bound=True,
        v152_both_interpreter_dispatch_paths=True,
        v152_three_synthetic_opcodes_verified=True,
        v152_post_sha_pre_dispatch_mutation_refusal=True,
        v152_original_retail_MIPS_executed=False,
        v152_original_MAP02_rendered=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
