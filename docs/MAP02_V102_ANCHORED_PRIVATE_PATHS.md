# MAP02 v102 — anchor private journal writes to a verified open directory

The pinned PCSX ReARMed v101 native GCC and Clang jobs passed 4 emulator
VBlank edges, 2,380 synthetic MIPS VRAM samples and 4,140 ordered native
GPU/private events without drops. Its original v82 private publisher used
no-clobber final hard links, double directory fsync, byte-exact final
re-opening, and fail-closed recovery after interrupted stages.

**Remaining risk:** pathname-based `open(tmp)`, `link(tmp,final)`,
`unlink(tmp)` could resolve through a *different directory* if the
parent were renamed or replaced between syscalls. Checking the old
descriptor only at the beginning is insufficient.

## v102 changes to native POSIX operations

The original v82 publisher still retains a single POSIX directory
descriptor opened with `O_DIRECTORY|O_NOFOLLOW`. v102 now performs its
stage operations **relative to that identical descriptor**:

- `openat(dirfd,stage,O_CREAT|O_EXCL|O_NOFOLLOW,0600)`;
- `openat(dirfd,stage,O_RDONLY|O_NOFOLLOW)` and exact byte readback;
- `linkat(dirfd,stage,dirfd,final_basename,0)`, preserving no-overwrite;
- `unlinkat(dirfd,stage,0)`, removing only the owned stage inside the
  originally opened directory.

New `vh102_parent_matches(dirfd,parent)` reopens the requested parent
using `O_DIRECTORY|O_NOFOLLOW`, compares **device and inode** with the
anchored descriptor and requires them to be identical. It runs before
mutating stage/final paths and after hard-link/unlink transitions.
The v101 final content verifier also uses `fstatat(dirfd,...,
AT_SYMLINK_NOFOLLOW)` and `openat(dirfd,final,O_NOFOLLOW)`. It requires
no unexpected sibling `.tmp`, checks file identity and contents,
and rejects changes in parent identity around final inode and
directory synchronization.

If identity changes, publication **fails closed** and does not retry
under the potentially redirected pathname. A post-link failure
deliberately leaves the possibly committed old final name in the
original directory; callers must use a **different clean filename**
for subsequent recovery. Private bytes must never be written to an
attacker-selected replacement directory through a redirected parent
symbolic link.

The solution does not prove atomic resistance to arbitrary adversarial
concurrent replacement of every intermediate parent component.
It assumes an exclusively controlled private directory and checks
the leaf parent's identity on each important transition. Pathnames
must be stable when the initial descriptor is opened.

## Deterministic native path-redirection regressions

Only isolated native GCC and Clang builds with `VH100_FAULT_TEST`
compile `vh102_test_parent_redirect`. This hook simulates, at
each of **three distinct commit boundaries**, renaming the private
directory and inserting a symlink at its previous name to another
directory containing a foreign file:

1. Before `linkat` final commit;
2. Immediately after `linkat`, before the first directory fsync;
3. After stage `unlinkat`, before the second directory fsync.

Every attempt must return failure; foreign destination bytes stay
unchanged. The original anchor remains the directory used for stage
operations, even when its pathname is redirected. Both normal successful
publication and verification are additionally tested under the true
directory identity, with no-clobber, symlink final refusal, and
pre-existing foreign stage refusal.

These are deterministic **path swap simulations**, not an exhaustive
concurrent-thread/model-checking proof nor a real power loss.

## Full pinned PCSX native smoke

v102 preserves every original v80–v101 MIPS, VBlank, Unai software-GPU
and async worker probe. Only **after** the original `GPUfreeze` barrier
and earlier checks, it writes two small synthetic private-only marker
files through the now descriptor-anchored native publisher, verifies
at least twelve successful directory identity checks, two anchored
commits, a second independent content verification for each file,
and refusal to republish at an occupied final filename.

The canonical private GPU journal still uses the original exclusive
mode-0600 output location with byte-exact and SHA-256 verification and
is never uploaded as a public GitHub artifact. Three bounded host-only
v102 observations are independently checked by a strict Python
verifier that requires the complete original v80–v101 event sequence.

## Evidence limits

Neither v102 nor earlier synthetic host controls demonstrate
authentic retail Vandal Hearts MAP02 rendering, physical PS1 GPU timing,
Nintendo Switch hardware execution, or correctness of the HD renderer.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`

Draft stacked on v101; `main` remains unchanged.
