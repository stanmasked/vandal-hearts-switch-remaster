#!/usr/bin/env python3
"""v150: opt-in bounded *native PCSX* interpreter, synthetic only.

A guard is called at the beginning of both pinned interpreter single-step
functions, before fetch, clock advancement or MIPS side effects. It records a
bounded instruction count and stops the interpreter block at the exact quota.
The only enabled CLI route requires the existing authenticated *synthetic*
VH129 test program and exits immediately after its first bounded block.
This does NOT permit a private retail PS-X EXE boot or MAP02 execution.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v147_generic_native_mmio import apply as apply_v147
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v129_four_vblank_exe import build

NATIVE_GUARD=r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
/* Native interpreter quota, NOT a host-process sandbox. Only the v129
 * self-authored MIPS test may activate this guard from frontend/main.c.
 * The stop check is BEFORE addCycle/dloadStep/fetch/opcode dispatch. */
static unsigned vh150_state, vh150_count, vh150_budget, vh150_reason;
static u32 vh150_low, vh150_high;
int vh150_arm(u32 lo, u32 hi, unsigned budget) {
    if(vh150_state || lo>=hi || (lo&3u) || (hi&3u) ||
       budget==0u || budget>256u) return -1;
    vh150_low=lo; vh150_high=hi; vh150_budget=budget;
    vh150_count=0u; vh150_reason=0u; vh150_state=1u;
    return 0;
}
static int vh150_before(psxRegisters *regs, u32 pc) {
    if(vh150_state==0u) return 1;
    if(vh150_state!=1u) return 0;
    if(vh150_count>=vh150_budget) vh150_reason=1u;
    else if((pc&3u) || pc<vh150_low || pc>=vh150_high)
        vh150_reason=2u;
    else {
        vh150_count++;
        return 1;
    }
    /* Do not execute the rejected word, even in a nested delay slot.
     * Mark both Execute and ExecuteBlock stop criteria before returning. */
    vh150_state=2u;
    regs->stop=1;
    regs->branchSeen=1;
    return 0;
}
unsigned vh150_steps(void) { return vh150_count; }
unsigned vh150_stop_reason(void) { return vh150_reason; }
void vh150_disarm(void) { vh150_state=0u; }
#endif

"""


def patch_interpreter(source: str) -> str:
    # First declaration in pinned source occurs before optional nested
    # psxTestSWInts dispatch; do not alter interpreter ABI or instruction map.
    decl=("static inline void execI_(\n"
          "\tu32 (INT_ATTR *fetch)(struct psxRegisters *r, "
          "const uintptr_t *luts, u32 pc),\n"
          "\tconst uintptr_t *memRLUT, psxRegisters *regs);")
    source=once(source,decl,NATIVE_GUARD+decl,
                "install bounded native instruction dispatch guard")
    for fname in ("execI_", "execIbp"):
        signature=("static inline void "+fname+"(\n"
                   "\tu32 (INT_ATTR *fetch)(struct psxRegisters *r, "
                   "const uintptr_t *luts, u32 pc),\n"
                   "\tconst uintptr_t *memRLUT, psxRegisters *regs)\n"
                   "{\n\tu32 pc = regs->pc;\n\n"
                   "\taddCycle(regs);")
        replacement=(signature.replace("\taddCycle(regs);",
            "#ifdef VH_MAP02_V66_PCSX_PROBE\n"
            "\tif(!vh150_before(regs,pc)) return;\n"
            "#endif\n"
            "\taddCycle(regs);"))
        source=once(source,signature,replacement,
                    "interpreter guard before "+fname+" side effects")
    return source


def patch_frontend(source: str) -> str:
    if "VH150_NATIVE_BOUNDED_INTERPRETER_PASS" in source:
        raise ValueError("v150 native quota patch is already present")
    source=once(source,
        "\tint vh147_generic_trace = 0;\n",
        "\tint vh147_generic_trace = 0;\n"
        "\tint vh150_bounded_instructions = 0;\n"
        "\textern int vh150_arm(uint32_t,uint32_t,unsigned);\n"
        "\textern unsigned vh150_steps(void);\n"
        "\textern unsigned vh150_stop_reason(void);\n"
        "\textern void vh150_disarm(void);\n",
        "explicit native guest budget opt-in variable")
    source=once(source,
        '\t\telse if (!strcmp(argv[i], "--vh147-bounded-mmio"))\n',
        '\t\telse if (!strcmp(argv[i], "--vh150-bounded-instructions"))\n'
        '\t\t\tvh150_bounded_instructions=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh147-bounded-mmio"))\n',
        "native bounded subset CLI option")
    source=once(source,
        "    if(vh129_vblank_mode>=0) {",
        "    if(vh150_bounded_instructions && vh129_vblank_mode!=0){\n"
        '        SysPrintf("VH150_SYNTHETIC_ONLY_REFUSED\\n");\n'
        "        ClosePlugins();SysClose();menu_finish();plat_finish();return 54;\n"
        "    }\n"
        "    if(vh129_vblank_mode>=0) {",
        "reject all non-v129 and mismatched VBlank options")
    anchor=("        /* Execute GPU setup as an original interpreted MIPS stage. */\n"
            "        psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);")
    raw,*_=build()
    if raw[:8]!=b"PS-X EXE" or raw[0x4c:0x54]!=b"VH129SY!" or len(raw)!=10240:
        raise ValueError("v129 synthetic-only native budget source changed")
    end=0x80010000 + len(raw)-2048
    replacement=(
        "        if(vh150_bounded_instructions){\n"

        f"            if(vh150_arm(0x80010000u,0x{end:08x}u,3u)!=0){{\n"
        '                SysPrintf("VH150_NATIVE_BUDGET_REFUSED\\n");\n'
        "                ClosePlugins();SysClose();menu_finish();plat_finish();return 54;\n"
        "            }\n"
        "        }\n"
        +anchor+
        "\n        if(vh150_bounded_instructions){\n"
        "            unsigned count=vh150_steps();\n"
        "            unsigned reason=vh150_stop_reason();\n"
        "            vh150_disarm();\n"
        "            if(count!=3u || reason!=1u){\n"
        '                SysPrintf("VH150_NATIVE_BUDGET_REFUSED\\n");\n'
        "                ClosePlugins();SysClose();menu_finish();plat_finish();return 54;\n"
        "            }\n"
        '            SysPrintf("VH150_NATIVE_BOUNDED_INTERPRETER_PASS"\n'
        '                      " steps=3 capped=1 synthetic_only=1 original_retail=0\\n");\n'
        "            ClosePlugins();SysClose();menu_finish();plat_finish();return 0;\n"
        "        }")
    # Earlier v125/v127 test oracles also contain the same setup phrase.
    # Scope the replacement to v129's own block, never to an older mode.
    header="    if(vh129_vblank_mode>=0) {"
    if source.count(header)!=1:
        raise ValueError("missing or ambiguous pinned v129 oracle boundary")
    begin=source.index(header)
    position=source.find(anchor,begin)
    if (position<0 or "VH129SY!" not in source[begin:position]
            or "#endif" in source[begin:position]):
        raise ValueError("native bounded setup not inside authenticated v129 block")
    # Permit the anchor to occur elsewhere for preserved older test modes.
    return source[:position]+replacement+source[position+len(anchor):]


def apply(root: Path):
    result=apply_v147(root)
    base=root.resolve()
    interp=base/"libpcsxcore/psxinterpreter.c"
    frontend=base/"frontend/main.c"
    interp.write_text(patch_interpreter(interp.read_text()))
    frontend.write_text(patch_frontend(frontend.read_text()))
    return dict(result,
        v150_native_actual_interpreter_budget=True,
        v150_interpreter_entry_guarded_before_side_effects=True,
        v150_normal_execution_inactive_by_default=True,
        v150_synthetic_only_original_boot_disabled=True,
        v150_no_retail_game_execution_or_MAP02_claim=True)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
