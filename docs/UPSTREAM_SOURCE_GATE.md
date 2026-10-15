# Pinned upstream source gate

This repository uses the public upstream project `HalmyLyseas/VandalHearts-PcPort` as a reference for a possible native Switch port. The source-integrity workflow checks out one reviewed revision:

`14552fffa0e0b47e02b57592e274fc6e7a649923`

It verifies the checkout SHA and presence of the upstream native build entry points and data-segment documentation. Pinning avoids silently auditing a moving default branch.

## What the CI source/configure gate proves

- CI can fetch the exact upstream source revision.
- The expected README, PC CMake/Make build entry points, and generated-data documentation exist.
- The audited CMake build references SDL2 and a region-specific PS-X executable input.
- On the current runner, the base CMake configuration succeeds with optional WebP/HD-video features disabled.

## What this gate does not prove

- It does not compile or link the upstream game.
- It does not validate any locally supplied game disc, executable, BIOS/font input, or generated data.
- It does not import upstream code into this repository or include copyrighted game data.
- It does not prove Switch compatibility, original-game rendering, audio, or physical-console behavior.

The native build generates assets and reconstructed data from a user's matching PS-X executable and KROMDAT/compatible BIOS font input. Those inputs are intentionally not stored in the repository or uploaded to CI.

## Opt-in local host build

The helper `tools/build_upstream_local.sh` provides the next step on a machine where the user already has the pinned upstream checkout and legally obtained input files. It expects these environment variables:

- `VH_UPSTREAM_DIR` — path to the checkout at the audited SHA; defaults to `upstream/` in the repository.
- `VH_PSX_EXE` — path to the user's matching regional PS-X executable (for the default US region, the upstream expects `SLUS_004.47`).
- `VH_KROM_SOURCE` — path to the user's `KROMDAT.BIN` or compatible BIOS font source.
- Optional: `VH_UPSTREAM_BUILD_DIR` for output location and `VH_BUILD_JOBS` for parallelism.

Example (adapt paths locally; do not commit the input files):

```sh
VH_UPSTREAM_DIR="$HOME/src/VandalHearts-PcPort" \
VH_PSX_EXE="$HOME/private-game-data/SLUS_004.47" \
VH_KROM_SOURCE="$HOME/private-game-data/KROMDAT.BIN" \
tools/build_upstream_local.sh
```

The helper checks that inputs are readable files, configures CMake with optional HD libraries disabled, and attempts to build `vandalhearts_pc`. It does not upload the inputs. A successful result would establish a **host PC compile/link** only, not a Switch-targeted build or runtime validation.

## Next integration step

Once a local host build is confirmed, compare the upstream renderer/presenter contract against the Switch presenter module and add a small, separately gated adapter while preserving desktop behavior. Do not claim original-game rendering until the real assets and game code have been exercised end-to-end.
