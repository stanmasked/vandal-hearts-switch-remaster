# Build Notes

## Status

There is currently no verified Switch build procedure in this repository. Do not
treat these notes as instructions for producing a working Switch binary.

## First: establish the upstream desktop build

1. Read the upstream project's own build instructions:
   https://github.com/HalmyLyseas/VandalHearts-PcPort
2. Review its architecture and cross-platform documentation, if present.
3. Record the operating system, compiler, build-system version, dependency versions,
   exact commands, and complete errors.
4. Confirm what legally obtained game data is required; do not commit that data.
5. Keep the unmodified upstream baseline separate from Switch-specific experiments.

## Switch toolchain investigation

Before writing a target-specific build:
- Consult current official devkitPro, devkitA64, and libnx documentation.
- Confirm target-compatible versions of each required library.
- Inspect the upstream build system and all platform-specific calls.
- Decide whether the current renderer, audio backend, input layer, and filesystem
  assumptions can be supported.
- Record the exact toolchain and dependency versions selected.

Do not copy generic build commands from unrelated projects and assume they apply.

## Reproducibility checklist

- [ ] Upstream revision recorded.
- [ ] Host OS and toolchain versions recorded.
- [ ] Dependencies and licenses inventoried.
- [ ] Desktop build result recorded.
- [ ] Switch target feasibility assessed.
- [ ] Build logs and known limitations documented.
- [ ] No proprietary game data included in the repository.
