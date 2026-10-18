#!/usr/bin/env python3
"""v151: source-bound SHA-256 of loaded synthetic MIPS RAM before native step.

No retail guest support. SHA-256 binds exactly the self-authored 8192-byte
v129 executable payload, not merely the easily copied VH129SY! tag.
The in-memory (post-load) bytes are validated immediately before v150 arms.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .apply_map02_v150_native_instruction_budget import apply as apply_v150
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v129_four_vblank_exe import build


SHA_C = r'''
#ifndef VH151_SYNTHETIC_SHA_H
#define VH151_SYNTHETIC_SHA_H
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Standalone SHA-256 for a fixed, compiled-in self-authored fixture.
 * No third-party library or disclosure of user-owned bytes. */
static uint32_t vh151_rotr(uint32_t x, unsigned n) {
    return (x >> n) | (x << (32u - n));
}
static void vh151_sha256_block(uint32_t state[8],
                               const unsigned char input[64]) {
    static const uint32_t k[64] = {
        0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,
        0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
        0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,
        0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
        0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,
        0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
        0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,
        0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
        0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,
        0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
        0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,
        0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
        0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,
        0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
        0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,
        0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u
    };
    uint32_t w[64],a,b,c,d,e,f,g,h;
    unsigned i;
    for(i=0;i<16u;i++) {
        unsigned q=i*4u;
        w[i]=((uint32_t)input[q]<<24) |
             ((uint32_t)input[q+1u]<<16) |
             ((uint32_t)input[q+2u]<<8) |
             (uint32_t)input[q+3u];
    }
    for(i=16u;i<64u;i++) {
        uint32_t s0=vh151_rotr(w[i-15u],7u) ^
                    vh151_rotr(w[i-15u],18u) ^ (w[i-15u]>>3u);
        uint32_t s1=vh151_rotr(w[i-2u],17u) ^
                    vh151_rotr(w[i-2u],19u) ^ (w[i-2u]>>10u);
        w[i]=w[i-16u]+s0+w[i-7u]+s1;
    }
    a=state[0];b=state[1];c=state[2];d=state[3];
    e=state[4];f=state[5];g=state[6];h=state[7];
    for(i=0;i<64u;i++){
        uint32_t s1=vh151_rotr(e,6u)^vh151_rotr(e,11u)^vh151_rotr(e,25u);
        uint32_t ch=(e&f)^(~e&g);
        uint32_t t1=h+s1+ch+k[i]+w[i];
        uint32_t s0=vh151_rotr(a,2u)^vh151_rotr(a,13u)^vh151_rotr(a,22u);
        uint32_t maj=(a&b)^(a&c)^(b&c);
        uint32_t t2=s0+maj;
        h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
    }
    state[0]+=a;state[1]+=b;state[2]+=c;state[3]+=d;
    state[4]+=e;state[5]+=f;state[6]+=g;state[7]+=h;
}
static void vh151_sha256(const unsigned char *bytes, size_t len,
                         unsigned char digest[32]) {
    uint32_t state[8]={
        0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,
        0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u
    };
    unsigned char last[64]={0};
    size_t offset=0u,rem;
    uint64_t bits=(uint64_t)len*8u;
    unsigned i;
    while(len-offset>=64u){
        vh151_sha256_block(state,bytes+offset);
        offset+=64u;
    }
    rem=len-offset;
    if(rem) memcpy(last,bytes+offset,rem);
    last[rem]=0x80u;
    if(rem>=56u){
        vh151_sha256_block(state,last);
        memset(last,0,sizeof(last));
    }
    for(i=0u;i<8u;i++)
        last[56u+i]=(unsigned char)(bits>>(56u-8u*i));
    vh151_sha256_block(state,last);
    for(i=0u;i<8u;i++){
        digest[4u*i]=(unsigned char)(state[i]>>24u);
        digest[4u*i+1u]=(unsigned char)(state[i]>>16u);
        digest[4u*i+2u]=(unsigned char)(state[i]>>8u);
        digest[4u*i+3u]=(unsigned char)state[i];
    }
}
static int vh151_verify_payload(const unsigned char *loaded) {
    static const unsigned char reference[32]={EXPECTED_SYNTHETIC_DIGEST};
    unsigned char actual[32];
    unsigned mismatch=0u,i;
    if(!loaded) return 0;
    vh151_sha256(loaded,8192u,actual);
    for(i=0u;i<32u;i++) mismatch|=(unsigned)(actual[i]^reference[i]);
    return mismatch==0u;
}
#endif /* VH151_SYNTHETIC_SHA_H */
'''


def original_fixture():
    source,*_=build()
    if (len(source)!=10240 or source[:8]!=b"PS-X EXE"
            or source[0x4c:0x54]!=b"VH129SY!"):
        raise ValueError("unexpected v129 source-authored EXE identity")
    return source[2048:]


def expected_payload_digest():
    return hashlib.sha256(original_fixture()).digest()


def header_source():
    digest=expected_payload_digest()
    content=SHA_C.replace("EXPECTED_SYNTHETIC_DIGEST",
        ",".join("0x%02xu"%x for x in digest))
    if "EXPECTED_SYNTHETIC_DIGEST" in content:
        raise ValueError("unbound native SHA-256 expected digest")
    return content


def patch_frontend(source: str) -> str:
    if "vh151_verify_payload" in source:
        raise ValueError("v151 native identity patch already installed")
    anchor="            if(vh150_arm(0x80010000u,0x80012000u,3u)!=0){"
    replacement=(
        "            /* Loaded guest RAM, not just a path tag, must match the\n"
        "             * complete self-authored synthetic payload byte-for-byte\n"
        "             * under SHA-256 before even arming the native CPU. */\n"
        "            if(!psxRegs.ptrs.psxM ||\n"
        "               !vh151_verify_payload(((const unsigned char *)"
        "psxRegs.ptrs.psxM)+0x10000u)){\n"
        '                SysPrintf("VH151_NATIVE_SYNTHETIC_DIGEST_REFUSED\\n");\n'
        "                ClosePlugins();SysClose();menu_finish();plat_finish();return 55;\n"
        "            }\n"
        +anchor
    )
    source=once(source,anchor,replacement,
                "native SHA-256 verification before guest instruction execution")
    return ("#ifdef VH_MAP02_V66_PCSX_PROBE\n"
            '#include "vh151_synthetic_sha.h"\n'
            "#endif\n"+source)


def apply(root: Path):
    previous=apply_v150(root)
    base=root.resolve()
    main=base/"frontend/main.c"
    header=base/"frontend/vh151_synthetic_sha.h"
    if header.exists() or header.is_symlink():
        raise ValueError("refusing to overwrite the native v151 digest header")
    updated=patch_frontend(main.read_text())
    header.write_text(header_source())
    main.write_text(updated)
    return dict(previous,
        v151_native_loaded_synthetic_sha256=True,
        v151_verified_loaded_bytes=8192,
        v151_sha256_precedes_instruction_budget=True,
        v151_retail_original_runtime_enabled=False,
        v151_original_MAP02_rendered=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
