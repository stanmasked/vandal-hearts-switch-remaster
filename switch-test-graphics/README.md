# Switch framebuffer graphics smoke test

This is a standalone libnx test that renders six vertical color bars into a 1280x720 RGBA8888 framebuffer. It checks that the Switch homebrew target can create and present a framebuffer, independently of SDL/OpenGL or any Vandal Hearts code.

- Press `+` to exit to the Homebrew Menu.
- Build with `make -C switch-test-graphics` inside the devkitPro Switch environment.
- The generated `switch-graphics-smoke-test.nro` is a diagnostic, not a game build.

The source follows the framebuffer API pattern in the public [switch-examples](https://github.com/switchbrew/switch-examples/tree/master/graphics/simplegfx) project. No proprietary game data is included.