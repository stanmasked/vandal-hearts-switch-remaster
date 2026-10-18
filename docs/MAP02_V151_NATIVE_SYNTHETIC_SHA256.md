# MAP02 v151 — native synthetic guest RAM identity by SHA-256

This experimental stage stacks on [v150 Draft PR #142](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/142) and **does not authorize retail game execution**.

## Fixed synthetic source binding

Earlier PCSX diagnostic routes accepted a self-authored `VH129SY!` tag as the synthetic program marker. This tag is trivially copyable. v151 additionally checks the SHA-256 hash of the **actual 8192 bytes loaded into PS1 RAM at physical offset 0x10000** before arming the v150 native three-instruction limit.

The expected digest is generated from the repository's own `make_map02_v129_four_vblank_exe.build()` output, never from the private game. `tools/apply_map02_v151_native_ram_identity.py` applies the original pinned PCSX v150 patch then generates a standalone, dependency-free C SHA-256 implementation and the reference digest in `frontend/vh151_synthetic_sha.h`. Only a byte-identical synthetic RAM payload is accepted by the v150 test route. Other historic modes remain unchanged unless the new native step budget is explicitly selected.

- **Positive:** pinned emulator boots the unmodified, original source-authored v129 synthetic EXE and confirms the native interpreter was capped at three instructions.
- **Negative:** the EXE has the same `VH129SY!` marker but a flipped payload byte. The native frontend must return exit status 55 with `VH151_NATIVE_SYNTHETIC_DIGEST_REFUSED` before it calls `vh150_arm` or executes any of the three synthetic guest instructions.
- **Independent SHA tests:** C implementations compiled by GCC and Clang are compared with Python `hashlib.sha256` on standard vectors, block boundaries and the complete 8192-byte synthetic source. A single altered byte must fail.
- **Evidence privacy:** tests produce only synthetic guest programs; protected runtime details and user-owned game images are excluded from published artifacts.

## Limits

SHA-256 binding of a public test fixture prevents accidental or straightforward same-tag substitution and detects changed bytes between source generation and guest-RAM execution. It does not establish an OS sandbox, prevent races after this guest-memory hash, stop all out-of-band emulator behavior, authenticate the original game, or allow execution of retail PS1 content. Private retail PS-X EXE launch, BIOS and CD access, MAP02 gameplay and Nintendo Switch HD parity remain unverified.

Keep the branch and PR in Draft until the actual pinned native PCSX/Unai GCC/Clang CI, including the tampered fixture denial, has passed.
