# Switch Homebrew Smoke Test

This is the first isolated toolchain/input test for the Vandal Hearts Switch porting effort. It intentionally contains **no Vandal Hearts source code or game data**.

## What it checks

- The devkitPro/libnx toolchain can compile a minimal homebrew application.
- The application launches and displays text using libnx's console.
- Controller input is read; press **+** to exit.

This is not a graphics-framebuffer test and does not prove the PC port can run on Switch.

## Build

Use a development environment with the current official devkitPro Switch toolchain and libnx installed. In a shell where `DEVKITPRO` is set:

```sh
cd switch-test
make
```

The build should produce `switch-smoke-test.nro` (exact output depends on the installed devkitPro rules). Copy the generated NRO to your homebrew launch environment using your usual method.

## Expected result

A console screen with the smoke-test title and a prompt to press +. The application exits when + is pressed.

## If the build fails

Please capture the complete output of:

```sh
echo "$DEVKITPRO"
make clean
make
```

Do not share console serials, account credentials, or private keys. Do not add proprietary game files to this folder.

## Next milestone

After this test builds and runs, add a separate graphics test to present a generated color-bar framebuffer. Only after toolchain, input, and presentation are verified should the upstream renderer be adapted.
