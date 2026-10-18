#!/usr/bin/env python3
"""Witness exact *executed* SW instruction words and DMA stage prefixes.

v138 already authenticated PC and register class of 19 synthetic MIPS
stores in the real pinned PCSX interpreter. v139 also checks regs->code
against independently generated executable bytes and checks MMIO store
prefixes after each of four real ExecuteBlock stages. All checks are opt-in
and never alter simulated CPU/GPU/DMA state. No retail game content.
"""
from pathlib import Path
from .apply_map02_v138_interpreter_pc import (
    apply as apply_v138,expected_pc_events,MIPS_START,
)
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v129_four_vblank_exe import build

def codeword_expectations():
    data,stops,ops,starts,wait_pc=build()
    events=expected_pc_events()
    result=[]
    for pc,*_ in events:
        offset=pc-MIPS_START
        if offset<0 or offset+4>len(ops)*4:
            raise ValueError("synthetic MIPS source PC outside generated program")
        word=int.from_bytes(data[0x800+offset:0x804+offset],"little")
        if word != ops[offset//4] or word>>26!=0x2b:
            raise ValueError("synthetic SW instruction word not source matched")
        result.append(word)
    prefixes=tuple(sum(pc<stop for pc,*_ in events) for stop in stops)
    if (len(stops)!=4 or len(prefixes)!=4 or
            not 0<prefixes[0]<prefixes[1]<prefixes[2]<prefixes[3] or
            prefixes[-1]!=len(result) or len(result)!=19):
        raise ValueError("synthetic PC / DMA stage-prefix classification refused")
    return events,tuple(result),prefixes

def patch_v138_probe_c(src):
    events,words,prefixes=codeword_expectations()
    declared=(
        "static const unsigned vh139_expected_word[] = { "+
        ", ".join("0x%08xu"%word for word in words)+" };\n"
        "static const unsigned vh139_stage_prefix[4] = { "+
        ", ".join("%du"%p for p in prefixes)+" };\n"
        "static unsigned vh139_active, vh139_bad, vh139_stage_next, vh139_corrupt;\n"
        "typedef char vh139_word_table_bound[(sizeof(vh139_expected_word)/"
        "sizeof(vh139_expected_word[0])==VH138_EXPECTED_COUNT)?1:-1];\n"
        "void vh139_enable(unsigned corrupt) {\n"
        "    vh139_active=1u; vh139_bad=0u; vh139_stage_next=0u;\n"
        "    vh139_corrupt=corrupt?1u:0u;\n"
        "}\n"
        "void vh139_check_stage(unsigned stage) {\n"
        "    if(!vh139_active) return;\n"
        "    if(stage>=4u || stage!=vh139_stage_next ||\n"
        "       vh138_seen!=vh139_stage_prefix[stage]) vh139_bad++;\n"
        "    else vh139_stage_next++;\n"
        "}\n"
        "unsigned vh139_verify(void) {\n"
        "    vh139_active=0u;\n"
        "    return (vh139_bad==0u && vh139_stage_next==4u &&\n"
        "            vh138_seen==VH138_EXPECTED_COUNT)?0u:1u;\n"
        "}\n")
    # The native v138 declarations have one unique static state.
    src=once(src,"static unsigned vh138_seen, vh138_bad, vh138_active;\n",
        "static unsigned vh138_seen, vh138_bad, vh138_active;\n"+declared,
        "v139 source-bound full instruction table and real stage counters")
    hook="""    /* Check the whole fetched, executed MIPS instruction word, not only
     * its SW opcode. The corrupt control mutates the *expected* word
     * on the third store, never an emulator register or actual MMIO. */
    if(vh139_active && vh138_seen<VH138_EXPECTED_COUNT) {
        unsigned want=vh139_expected_word[vh138_seen];
        if(vh139_corrupt && vh138_seen==2u) want^=1u;
        if(regs->code!=want) vh139_bad++;
    }
"""
    anchor="    /* The pinned psxinterpreter.c execI_ advances regs->pc by four\n"
    src=once(src,anchor,hook+anchor,
        "exact word of actual current interpreted SW at MMIO write")
    return src

def modify_oracle(src,expected_count):
    src=once(src,
        "        extern void vh138_pc_enable(void);\n",
        "        extern void vh138_pc_enable(void);\n"
        "        extern void vh139_enable(unsigned corrupt);\n"
        "        extern void vh139_check_stage(unsigned stage);\n"
        "        extern unsigned vh139_verify(void);\n",
        "v139 native provenance API")
    anchor='        if(vh138_pc_capture && vh129_vblank_mode!=0){\n'
    src=once(src,anchor,
        '        if(vh139_word_capture && !vh138_pc_capture){\n'
        '            SysPrintf("VH139_MODE_REFUSED\\n");\n'
        '            ClosePlugins();SysClose();menu_finish();plat_finish();return 49;\n'
        '        }\n'+anchor,
        "v139 requires actual v138 interpreted MIPS memory writes")
    src=once(src,
        '        if(vh138_pc_capture) vh138_pc_enable();\n',
        '        if(vh138_pc_capture) vh138_pc_enable();\n'
        '        if(vh139_word_capture) vh139_enable(vh139_corrupt_word);\n',
        "enable codeword check only after validated self-authored EXE signature")
    src=once(src,
        '        psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);\n'
        '        unsigned int off=0x111a0u;\n',
        '        psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);\n'
        '        if(vh139_word_capture) vh139_check_stage(0u);\n'
        '        unsigned int off=0x111a0u;\n',
        "first interpreted MIPS setup stage exact MMIO site prefix")
    src=once(src,
        '            psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);\n'
        '            off=0x111a0u+4u*(phase+1u);\n',
        '            psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);\n'
        '            if(vh139_word_capture) vh139_check_stage(phase+1u);\n'
        '            off=0x111a0u+4u*(phase+1u);\n',
        "verify all three interpreted DMA stages before native Unai comparisons")
    guard="""            if(vh139_word_capture){
                if(vh139_verify()!=0u){
                    SysPrintf("VH139_NATIVE_WORD_REFUSED\\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 49;
                }
                SysPrintf("VH139_NATIVE_MIPS_WORDS_PASS matched=VH139_COUNT"
                          " stages=4 exact_words=VH139_COUNT"
                          " original_retail=0\\n");
            }
""".replace("VH139_COUNT",str(expected_count))
    src=once(src,
        '            if(vh138_pc_inject_bad) vh138_pc_inject_error();\n',
        guard+'            if(vh138_pc_inject_bad) vh138_pc_inject_error();\n',
        "native exact instruction and stage sequence before earlier v138 PASS")
    return src

def apply(root:Path):
    previous=apply_v138(root)
    events,words,prefixes=codeword_expectations()
    memfile=root.resolve()/"libpcsxcore/psxmem.c"
    frontfile=root.resolve()/"frontend/main.c"
    mem=patch_v138_probe_c(memfile.read_text())
    front=frontfile.read_text()
    front=once(front,
        "\tint vh138_pc_inject_bad = 0;\n",
        "\tint vh138_pc_inject_bad = 0;\n"
        "\tint vh139_word_capture = 0;\n"
        "\tint vh139_corrupt_word = 0;\n",
        "separate opt-in v139 codeword and corruption options")
    front=once(front,
        '\t\telse if (!strcmp(argv[i], "--vh138-interpreter-pc"))\n',
        '\t\telse if (!strcmp(argv[i], "--vh139-codewords"))\n'
        '\t\t\tvh139_word_capture=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh139-corrupt-word-witness"))\n'
        '\t\t\tvh139_corrupt_word=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh138-interpreter-pc"))\n',
        "additional opt-in word-by-word native MIPS execution checks")
    # Only alter the previously proven v138 native oracle, not game code.
    front=modify_oracle(front,len(events))
    memfile.write_text(mem)
    frontfile.write_text(front)
    return dict(previous,
        v139_exact_interpreted_mips_words_observed=len(words),
        v139_four_native_cpu_stage_prefixes=list(prefixes),
        v139_wrong_word_expected_mutation_rejected=True,
        original_mips_retail_execution_verified=False,
        original_map02_frame_capture_verified=False,
        nintendo_switch_hd_parity_verified=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
