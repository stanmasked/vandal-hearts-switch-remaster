# MAP02 v169 — interpreted MIPS indexed CLUT STP/ABR and E2 vertical → Unai VRAM

This stage continues the successful v168 synthetic 4/8bpp CLUT and E2
horizontal experiment (61/61 workflows), reusing a **separate, entirely
self-authored** v75 signed synthetic PS-X EXE. It does not use the original
Vandal Hearts executable, its MAP02 graphics or any private retail trace.

The source-authored guest program makes a real PS1 GP1 FIFO-reset
write, followed by **236 GPU GP0 words** submitted by actual
interpreter-executed `SW t1,0(t0)` instructions. It uploads two packed
indexed 4/8bpp textures and their 16- and 256-entry CLUT palettes through
four GP0(A0) packets. It also draws five textured FT4 quads:

- 4bpp palette STP=1, ABR0 average blending over an opaque blue base;
- 4bpp palette STP=0 despite enabled ABE, no blend;
- 8bpp palette STP=1, ABR1 additive blending;
- transparent palette index 0, retaining the blue background;
- E2 vertical texture-window mask+offset `0xe2008020` mapping V0..3 to
  V8..11, followed by E2 reset `0xe2000000`.

The diagnostic-only v169 MMIO observer verifies source-derived MIPS
instruction PC, exact `SW` opcode, 32-bit GP0 packet word and correct
ordering **for every one of 236 writes**. It does not modify the
emulator, GPU or images. It disarms before native `GPU_freeze` reads
and the independent original v75 oracle compares **511 pixels**:
five sets of 16 colored pixels and 431 unchanged background pixels.

Required actual pinned native GCC and Clang success:

`VH169_GUEST_MIPS_STP_E2V_VRAM_PASS gp0_words=236 gp1_words=1 a0_uploads=4 ft4=5 pixels_checked=511 stp4=16 nonstp=16 abr1=16 transparent=16 e2_vertical=16 guard=431 original_retail=0`

A negative run retains the unique signed synthetic identity while
flipping exactly one guest-MIPS `ORI` instruction that generates the E2
vertical mask. The change alters the intended GPU word from
`0xe2008020` to `0xe2008000`, and must cause native code 75
(`VH169_STP_E2V_MIPS_GP0_REFUSED`) before any v169 pixel-positive
marker. GCC/Clang compiled regressions exercise the source-PC,
opcode, GP1-reset, wrong-word, extra-word and missing-word guards.

**No claims:** this is not genuine retail Vandal Hearts MAP02 artwork,
camera geometry, textures, battle scene, Switch HD graphical parity or
a playable remake. No original retail game file or private data are
committed to GitHub.
