# MAP02 v177: GP0/GP1 high-lane validation

This stacked diagnostic-only stage builds on v176 (PR #199, 69/69 successful GitHub Actions).

The native GCC/Clang workflow adds four synthetic MIPS negative cases to the original four v176 cases: LB GP0+3, LH GP1+6, SB GP0+3 and SH GP1+6. Each case changes exactly one instruction in the self-authored VH78SYN! program, expects refusal 82 with the correct read/write and GP0/GP1 category, and forbids a false pixel success.

The independent C fixture checks 24 byte/halfword memory-access operations across both GPU ports, alongside normal-memory behavior, address aliases, window arming and disarming. The clean interpreted guest still requires four emulator-internal VBlank events and 2380 native Unai samples.

This does not establish original retail MAP02 execution, a playable remake, or physical Nintendo Switch graphics output. No original game data are published.
