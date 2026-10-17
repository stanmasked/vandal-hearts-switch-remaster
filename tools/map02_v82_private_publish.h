#ifndef VH82_PRIVATE_PUBLISH_H
#define VH82_PRIVATE_PUBLISH_H
#include <stddef.h>
/* POSIX-only private, exclusive, readback-verified publication.
 * No replacement of an existing final file, never public upload. */
int vh82_publish_private(const char *path,const char *bytes,size_t size);
/* Successful directory fsync calls after final hard-link and temp unlink. */
unsigned int vh100_directory_syncs(void);
/* Reopen and validate an already published 0600 private file without
 * modifying either the file or its pathname. Returns 0 ONLY if all
 * bytes match, the file itself fsyncs, and the reopened parent fsyncs. */
int vh101_verify_private_commit(const char *path,const char *bytes,size_t size);
unsigned int vh101_verified_commits(void);
unsigned int vh101_reopened_directory_syncs(void);
/* Number of successful rooted-directory identity checks and publications. */
unsigned int vh102_parent_identity_checks(void);
unsigned int vh102_anchored_publishes(void);
/* Successful parent-path component walks rejecting symlinks at every level. */
unsigned int vh103_safe_parent_walks(void);
#ifdef VH100_FAULT_TEST
/* Test-only fault gates at each post-link publish durability boundary. */
void vh100_test_fail_at(int phase);
/* Isolated post-commit verifier I/O failures; never in production PCSX. */
void vh101_test_fail_at(int phase);
/* Isolated native tests: deterministically rename parent and redirect path
 * via symlink at stage (1), after final hard link (2), or after unlink (3).
 * Never compiled in the real pinned PCSX runtime. */
int vh102_test_parent_redirect(const char *parent,const char *moved,
                               const char *target,int phase);
/* Isolated native deterministic identical-byte final-inode replacement at
 * (1) between fstatat and openat or (2) between readback and final fstatat. */
int vh103_test_replace_final(const char *original,const char *replacement,
                             const char *backup,int phase);
#endif
/* An existing private file must be immutable. Only a DISTINCT unused path
 * may receive a recovered observer lifetime; never rename/replace old. */
int vh98_publish_recovery(const char *previous_path,const char *next_path,
                          const char *bytes,size_t size);
/* Classify native private journal state WITHOUT opening a .tmp for replay.
 * -1 unsafe or unexpected IO; 0 entirely fresh; 1 committed-only;
 * 2 abandoned stage only; 3 committed with residual stage.
 * This does not modify either pathname. */
int vh99_private_state(const char *final_path);
/* After an interrupted, uncommitted stage, publish only to a DIFFERENT
 * empty final pathname. Never re-use, unlink or publish the staged file. */
int vh99_publish_after_interruption(const char *abandoned_final,
                                   const char *fresh_final,
                                   const char *bytes,size_t size);
#endif
