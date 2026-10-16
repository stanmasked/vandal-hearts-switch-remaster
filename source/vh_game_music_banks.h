#ifndef VH_GAME_MUSIC_BANKS_H
#define VH_GAME_MUSIC_BANKS_H

#include "vh_audio_assets.h"
#include "vh_game_music_mailbox.h"
#include "vh_music_scene.h"

/* Read-only, preloaded two-scene music pack from caller-owned SD data.
 * No original game resources are bundled. Load once on the audio owner
 * thread before starting audout. Each scene has its own bank/PCM arena.
 *
 * Directory hierarchy (exact names, no path data taken from SEQ/VH):
 *   root/field/music.seq, music.vh, music.vb
 *   root/selected/music.seq, music.vh, music.vb
 *
 * Both absent: VH_AUDIO_ASSET_MISSING (optional synthetic fallback).
 * A single present scene, partial triplet, malformed data or budget
 * violation: VH_AUDIO_ASSET_ERROR; no partial pack is published.
 */
#define VH_GAME_MUSIC_MAX_TOTAL_VB_BYTES (12u * 1024u * 1024u)

/* The first mismatched SEQ program/key and the tone chosen by the
 * PC-port-compatible global VH fallback. Diagnostic only: a valid
 * fallback may be musically intentional, not always an error.
 */
typedef struct {
    unsigned valid;
    unsigned requested_program, note;
    unsigned selected_program, selected_tone, selected_vag;
} VhGameMusicFallback;

typedef struct {
    VhAudioAssets field, selected;
    /* Audited during preload, before any audio service opens. Full
     * fallback is legal but indicates that SEQ requested an absent
     * program/range; can affect timbre relative to the original.
     */
    VhSeqAudit field_audit, selected_audit;
    uint32_t field_fallback_notes, selected_fallback_notes;
    VhGameMusicFallback field_first_fallback, selected_first_fallback;
} VhGameMusicBanks;

/* On success allocates *out and transfers ownership to caller.
 * On missing/error leaves *out unchanged. Caller passes *out==NULL.
 * Must keep *out until all scene voices and audout are fully stopped.
 */
int vh_game_music_banks_load(VhGameMusicBanks **out, const char *root);
int vh_game_music_banks_cue(VhGameMusicBanks *pack, unsigned scene_id,
                            VhMusicCue *cue);
void vh_game_music_banks_close(VhGameMusicBanks **pack);

#endif
