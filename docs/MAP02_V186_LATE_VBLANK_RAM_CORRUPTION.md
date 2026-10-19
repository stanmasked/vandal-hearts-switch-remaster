# MAP02 v186 — fail-closed RAM readbacks after later genuine VBlank windows

Base: [MAP02 v185 Draft PR #215](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/215), which confirmed 78/78 GitHub Actions on synthetic PS1 guest code and pinned native PCSX ReARMed/Unai GCC and Clang. The v185 diagnostic seeded RAM once and read three words **before** each subsequent guest execution; its negative modes injected test-only low-bit host faults after phase 0 and required refusal at phase 1.

v186 tests the remaining windows. Six new opt-in modes `--vh186-ram-persist-4..9` preserve the existing synthetic guest EXE, real VBlank counter and Unai GPU oracle. Modes 4–6 deliberately corrupt the first guest-written word, derived guest-written word or neighboring guard **after phase 1**, respectively, with refusal required at the **phase 2 pre-execution readback**. Modes 7–9 corrupt the same three values **after phase 2**, requiring refusal at **phase 3**. Each run must terminate with native exit 86 and exactly one incorrect field (`first_ok=0`, `derived_ok=0`, or `guard_ok=0`); no v185/v183 RAM success or Unai GPU success marker is allowed.

The existing phase-zero modes 1–3 are explicitly bounded to prevent accidental early corruption in v186. Both independent GCC/Clang source-model tests and actual pinned native PCSX GCC/Clang runs are required, preserving the v185 positive and original negative cases.

All intentional RAM modifications are **test-only host bit flips** after synthetic interpreted guest execution, never guest-originated corruption. No original retail Vandal Hearts MAP02 execution or physical Switch output is claimed. This work stays stacked in a Draft PR and leaves main untouched.
