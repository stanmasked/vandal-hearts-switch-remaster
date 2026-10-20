# MAP02 v192 — tie true PCSX subprocess exit codes to private log SHA-256

v192 stacks on the MAP02 v191 Draft PR #224, which is still awaiting complete GCC/Clang native verification. This isolated branch must not change or restart v191's checks.

The v191 phase checker correlates four genuine 595-pixel VRAM checks in the clean run with the ten isolated, synthetic PS1 guest runs and their 21 guest RAM receipts. It does not itself prove that the host PCSX subprocess returned exit code 0 for the clean run and exit code 86 for each of nine deliberate memory corruptions. Earlier shell workflow enforces each exit code, but those values are not bound to the exact private log bytes by an independent second verifier.

The pinned native shell in v192 records immediately after each of the same ten genuine PCSX subprocesses: mode number, actual host process return code, and SHA-256 hash of that process's private stdout/stderr log. The single private v192-native-exits.txt file is never uploaded or displayed. Negative and positive modes remain unchanged.

A separate read-only verifier checks the manifest is a bounded, real, non-symlink file read using O_NOFOLLOW; requires ten records in strict order (0..9), one clean mode with rc=0 and nine negative modes with rc=86, and compares all ten expected SHA-256 values against the native input logs. It checks the original ten logs' identity before/after the verification, then invokes the inherited v191/v190/v189 proof before issuing:

VH192_NATIVE_PROCESS_EXIT_RECEIPTS_PASS modes=10 positive_exit=0 negative_exits=9 native_exit=86 sha256_matches=10 phase_passes=22 mutations=159 original_retail=0

Independent GCC/Clang tests inject wrong exit, reordered/missing/duplicated manifests, misleading hash, changed private log bytes, symlinks and oversized manifest. No original retail MAP02 code is run, no physical Nintendo Switch claim, no private game bytes or trace logs exported.
