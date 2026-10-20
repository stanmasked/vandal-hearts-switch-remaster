# MAP02 — on-device Intel Mac / Catalina offline acceptance receipt

This stage follows the verified [Draft PR #369](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/369), where the public-only diagnostic ZIP is authenticated via its independently obtained SHA-256 **before extraction**, and its files are checked again before diagnostics are imported.

The owner has an Intel Mac target; an actual macOS Catalina 10.15.7 runtime has **not yet been accessed or tested**. The aim of this script is to make that eventual check unambiguous, without retrieving or publishing game content.

## Run on the extracted, already authenticated kit

From the extracted kit directory, with Python 3.9+ and Xcode/Clang tools installed:

```bash
python3 -B -m tools.map02_intel_mac_local_acceptance
```

This performs a fresh full synthetic test run: 49 source/GTE/VRAM/FT4 tests, 10 real CLI cases, the 3 actual public-PC-source C helpers, and Mach-O target/dylib audits. It checks the extracted kit manifest first. It emits one sanitized JSON receipt containing the bounded macOS version, x86_64 architecture, Python major/minor, exact test counts and false claims for proprietary assets, PS1 raster equivalence, Switch hardware and independent hardware attestation.

**On the physical Intel Mac running macOS Catalina 10.15.7**, use the stricter form:

```bash
python3 -B -m tools.map02_intel_mac_local_acceptance \
  --require-catalina-10-15-7
```

This rejects any other host **before running the expensive tests**. The `-B` switch prevents the interpreter from creating new `__pycache__` files before the kit's integrity check. Run both commands inside the verified extracted kit; do not move a report into that kit directory because an extra file invalidates its `files.json` closure. Redirect a receipt to a file outside the extracted tree if desired.

The exact field `actual_catalina_10_15_7_selfcheck_passed` can be true **only** if this code observes `Darwin/x86_64`, exactly macOS 10.15.7 and successfully completes the full suite on that host. It is a **self-reported local observation**, not a cryptographically trusted attestation or proof that the operating system has not been tampered with. The synthetic fixtures do not establish genuine retail Vandal Hearts image fidelity.

## Continuous integration verification

GitHub's available `macos-15-intel` runners (Python 3.9 and 3.11) exercise the real new command from the authenticated extracted kit; they must produce a general compatibility receipt and **strictly reject** the Catalina-only switch. The Linux job tests nine mocked contracts and denies Linux or Apple Silicon pretending to be Intel macOS. Mocked Catalina fixture acceptance is merely a test of the rule, **not evidence that Catalina ran**.

No owner's external drive, original PS1 BIN/CUE, decoded MAP02 sectors, game textures, true GPU captures, private user paths or screenshots are required or uploaded. `main` is unchanged; keep this child PR Draft and unmerged until a real local test can be reviewed.
