#include "vh_game_music_banks.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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
    const int b=vh_audio_assets_load(&pending->selected,selected);
    if (a!=VH_AUDIO_ASSET_OK || b!=VH_AUDIO_ASSET_OK) {
        const int entirely_absent =
            a==VH_AUDIO_ASSET_MISSING && b==VH_AUDIO_ASSET_MISSING;
        dispose(pending);
        return entirely_absent ? VH_AUDIO_ASSET_MISSING
                               : VH_AUDIO_ASSET_ERROR;
    }
    /* Guard simultaneous bank memory pressure. The compressed-file
     * cap also bounds the 28-per-16 PCM arena to roughly 42 MiB total.
     * Each source has its own preexisting strict 8 MiB VB cap.
     */
    if (pending->field.vb_size >
          VH_GAME_MUSIC_MAX_TOTAL_VB_BYTES - pending->selected.vb_size) {
        dispose(pending);
        return VH_AUDIO_ASSET_ERROR;
    }
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
