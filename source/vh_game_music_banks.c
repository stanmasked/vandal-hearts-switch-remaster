#include "vh_game_music_banks.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    VhNativeVab *bank;
    uint32_t fallback_notes;
    VhGameMusicFallback first;
} BankAuditContext;

/* The existing PC-like resolver uses requested-program range first,
 * then falls back across VH. Diagnostic calls are made once at load.
 * No need to parse pQES twice or allocate voices to detect them.
 */
static int audit_resolve(void *context, unsigned program, unsigned note,
                         unsigned velocity, unsigned volume, unsigned pan,
                         VhSeqTone *out) {
    BankAuditContext *audit = context;
    const int status = vh_native_vab_resolve(
        audit->bank, program, note, velocity, volume, pan, out);
    if (status == 0) {
        const VhVabTone *tone =
            &audit->bank->tones[audit->bank->selected_program]
                               [audit->bank->selected_tone];
        if (audit->bank->selected_program != program ||
            note < tone->low || note > tone->high) {
            ++audit->fallback_notes;
            if (!audit->first.valid) {
                audit->first=(VhGameMusicFallback){
                    .valid=1u, .requested_program=program, .note=note,
                    .selected_program=audit->bank->selected_program,
                    .selected_tone=audit->bank->selected_tone,
                    .selected_vag=audit->bank->selected_vag
                };
            }
        }
    }
    return status;
}

static void dispose(VhGameMusicBanks *pack) {
    if (!pack) return;
    vh_audio_assets_close(&pack->selected);
    vh_audio_assets_close(&pack->field);
    free(pack);
}

void vh_game_music_banks_close(VhGameMusicBanks **pack) {
    if (!pack || !*pack) return;
    dispose(*pack);
    *pack = NULL;
}

int vh_game_music_banks_load(VhGameMusicBanks **out, const char *root) {
    if (!out || *out || !root || !*root) return VH_AUDIO_ASSET_ERROR;
    char field[VH_AUDIO_ASSET_MAX_PATH], selected[VH_AUDIO_ASSET_MAX_PATH];
    const int nf=snprintf(field,sizeof field,"%s/field",root);
    const int ns=snprintf(selected,sizeof selected,"%s/selected",root);
    if (nf<0 || ns<0 || (size_t)nf>=sizeof field ||
        (size_t)ns>=sizeof selected) return VH_AUDIO_ASSET_ERROR;

    /* No giant metadata objects on constrained Switch thread stacks.
     * A temporary published pack is only visible when BOTH succeed.
     */
    VhGameMusicBanks *pending=calloc(1,sizeof(*pending));
    if (!pending) return VH_AUDIO_ASSET_ERROR;
    const int a=vh_audio_assets_load(&pending->field,field);
    /* Do not waste memory decoding selected after corrupt field. */
    if (a==VH_AUDIO_ASSET_ERROR) {
        dispose(pending);
        return VH_AUDIO_ASSET_ERROR;
    }
    const size_t remaining =
        VH_GAME_MUSIC_MAX_TOTAL_VB_BYTES - pending->field.vb_size;
    const int b=vh_audio_assets_load_bounded(
        &pending->selected,selected,remaining);
    if (a!=VH_AUDIO_ASSET_OK || b!=VH_AUDIO_ASSET_OK) {
        const int entirely_absent =
            a==VH_AUDIO_ASSET_MISSING && b==VH_AUDIO_ASSET_MISSING;
        dispose(pending);
        return entirely_absent ? VH_AUDIO_ASSET_MISSING
                               : VH_AUDIO_ASSET_ERROR;
    }
    /* Defense in depth: the second set had its compressed-VB bound
     * checked BEFORE allocating its VB and decoded PCM arrays. Keep
     * the post-load aggregate assertion against future loader changes.
     */
    if (pending->field.vb_size >
          VH_GAME_MUSIC_MAX_TOTAL_VB_BYTES - pending->selected.vb_size) {
        dispose(pending);
        return VH_AUDIO_ASSET_ERROR;
    }
    BankAuditContext field_audit={.bank=&pending->field.bank};
    BankAuditContext selected_audit={.bank=&pending->selected.bank};
    const int ok_field=vh_native_seq_audit(
        pending->field.seq,pending->field.seq_size,audit_resolve,
        &field_audit,&pending->field_audit);
    const int ok_selected=vh_native_seq_audit(
        pending->selected.seq,pending->selected.seq_size,audit_resolve,
        &selected_audit,&pending->selected_audit);
    /* A song containing actual note-on events but with no playable
     * instruments is not a valid user music set for this scene.
     * Partial fallback remains allowed, but is reported distinctly.
     */
    if (ok_field || ok_selected ||
        (pending->field_audit.note_events &&
         !pending->field_audit.resolved_notes) ||
        (pending->selected_audit.note_events &&
         !pending->selected_audit.resolved_notes)) {
        dispose(pending);
        return VH_AUDIO_ASSET_ERROR;
    }
    pending->field_fallback_notes=field_audit.fallback_notes;
    pending->selected_fallback_notes=selected_audit.fallback_notes;
    pending->field_first_fallback=field_audit.first;
    pending->selected_first_fallback=selected_audit.first;
    *out=pending;
    return VH_AUDIO_ASSET_OK;
}

int vh_game_music_banks_cue(VhGameMusicBanks *pack, unsigned scene_id,
                            VhMusicCue *cue) {
    if (!pack || !cue) return -1;
    VhAudioAssets *assets = scene_id==VH_GAME_MUSIC_FIELD
        ? &pack->field
        : scene_id==VH_GAME_MUSIC_HERO_SELECTED ? &pack->selected : NULL;
    if (!assets || !assets->seq || !assets->bank.active) return -1;
    *cue=(VhMusicCue){
        .id=scene_id,
        .seq=assets->seq,
        .seq_size=assets->seq_size,
        .repeats=0,
        .resolver=vh_native_vab_resolve,
        .context=&assets->bank
    };
    return 0;
}
