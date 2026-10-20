# MAP02 — Intel Mac Catalina minimum binary target audit

This additional Draft test narrows the gap between the already verified
macOS 15 **Intel x86_64** synthetic source/GTE/VRAM/FT4 verification
and the owner's Intel Mac running an older macOS release.

The workflow runs Apple's native Clang on `macos-15-intel`, with
`-arch x86_64 -mmacosx-version-min=10.15` and
`MACOSX_DEPLOYMENT_TARGET=10.15`. It links the existing asset-free
three-face C11 MAP02 VRAM4/ordering-table test into a native Mach-O
executable and checks `file` and `otool -l` for both:

* actual **Mach-O x86_64** executable, not Apple Silicon and not a
  Linux/ELF cross-compile;
* exact recorded `LC_BUILD_VERSION minos 10.15.x` or legacy
  `LC_VERSION_MIN_MACOSX version 10.15.x` load-command minimum.

It then executes the built C program on the **macOS 15 Intel runner**
to revalidate the three-face 4bpp atlas/CLUT and original OT order.
It never reads original images, owned PS1 discs, private GPU snapshots,
textures, screenshots or any user files.

A successful binary minimum audit is **not a Catalina runtime test**.
The modern toolchain may link newer system symbols unless those are
separately inspected, and GitHub's runner uses macOS 15. It also does
not establish Catalina Python 3.9 interpreter support, installed Clang
SDK availability, real MAP02 provenance, bit-exact PS1 GPU rendering or
Nintendo Switch runtime boot.

Keep this separate child of Draft #332 unmerged. No production game
code or any earlier approved PR is edited.
