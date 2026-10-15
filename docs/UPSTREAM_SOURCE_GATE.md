# Pinned upstream source gate

This repository uses the public upstream project `HalmyLyseas/VandalHearts-PcPort` as a reference for a possible native Switch port. The source-integrity workflow checks out one reviewed revision:

`14552fffa0e0b47e02b57592e274fc6e7a649923`

It verifies the checkout SHA and presence of the upstream native build entry points and data-segment documentation. Pinning avoids silently auditing a moving default branch.

## What this gate proves

- CI can fetch the exact upstream source revision.
- The expected README, PC CMake/Make build entry points, and generated-data documentation exist.
- The audited CMake build references SDL2 and a region-specific PS-X executable input.

## What this gate does not prove

- It does not compile or link the upstream game.
- It does not validate any locally supplied game disc, executable, BIOS/font input, or generated data.
- It does not import upstream code into this repository or include copyrighted game data.
- It does not prove Switch compatibility, original-game rendering, audio, or physical-console behavior.

The upstream build documentation states that its native PC build needs a user's own matching game executable and disc data, plus SDL2, OpenAL, OpenGL on non-macOS targets, Python, and optionally libwebp/libav for HD features. The current Switch project has not yet integrated the upstream implementation. A later build gate should use user-supplied local data outside version control, record dependency/toolchain versions, and clearly separate a successful host build from a Switch-targeted build.

## Next integration step

After this pinned source gate passes, define a reproducible dependency environment and an opt-in local-data build check. Only then should a small, separately gated change connect the audited final-frame output to the Switch presenter while preserving desktop behavior.
