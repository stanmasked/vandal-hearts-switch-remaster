# Switch Toolchain Diagnostic

This check is an environment preflight, not a Switch build and not a runtime test.

## Run

From the repository root, in Bash:

```sh
bash tools/check_switch_toolchain.sh
```

The script reports the host, `DEVKITPRO` and `DEVKITA64`, the expected AArch64 compiler and NRO tools, and the libnx `switch.h` header. If package-manager metadata is available, it also attempts to print versions of the relevant packages.

A non-zero exit status means one or more required commands or paths were not found. Review the exact output and install/configure the official devkitPro environment for your host before trying again. The script does not install packages or change shell configuration.

## Interpreting the result

- **Diagnostic pass:** the listed commands and paths were found. This does not prove a minimal NRO compiles, launches, reads controller input, or presents frames.
- **Diagnostic fail:** the output identifies missing commands or paths. This is an environment-preflight failure, not a failed game build.
- **Build success:** only record this after running an actual build command and confirming its exit code and generated artifact.
- **Runtime success:** record emulator and physical-console results separately, with environment/version details and evidence.

Capture the full output and host/toolchain versions when filing results in [the prototype checklist](PROTOTYPE_CHECKLIST.md). Do not include proprietary game files in test artifacts.
