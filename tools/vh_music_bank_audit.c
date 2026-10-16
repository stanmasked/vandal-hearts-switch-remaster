/* Read-only offline instrument coverage analyzer for user-owned
 * SEQ/VH/VB assets. Emits numbers only, never audio samples or bytes.
 * Works on Linux/macOS with the host compiler; no Switch SDK needed.
 */
#include <stdio.h>
#include <string.h>
#include <stdint.h>

#include "vh_game_music_banks.h"

static void print_scene(const char *name, const VhSeqAudit *audit,
                        uint32_t fallback_count,
                        const VhGameMusicFallback *first) {
    printf("  \"%s\": {\n", name);
    printf("    \"events\": %u, \"note_on\": %u, "
           "\"resolved\": %u, \"missing\": %u, "
           "\"fallback\": %u,\n",
           audit->events, audit->note_events, audit->resolved_notes,
           audit->missing_notes, fallback_count);
    printf("    \"program_changes\": %u, \"tempo_changes\": %u,\n",
           audit->program_changes, audit->tempo_changes);
    if (audit->has_missing) {
        printf("    \"first_missing\": {\"channel\": %u, "
               "\"program\": %u, \"note\": %u},\n",
               audit->first_missing_channel,
               audit->first_missing_program,
               audit->first_missing_note);
    } else {
        puts("    \"first_missing\": null,");
    }
    if (first->valid) {
        printf("    \"first_fallback\": {\"program\": %u, "
               "\"note\": %u, \"selected_program\": %u, "
               "\"selected_tone\": %u, \"selected_vag\": %u}\n",
               first->requested_program, first->note,
               first->selected_program, first->selected_tone,
               first->selected_vag);
    } else {
        puts("    \"first_fallback\": null");
    }
    printf("  }");
}

int main(int argc, char **argv) {
    int strict=0;
    const char *folder=NULL;
    if (argc==2) folder=argv[1];
    else if (argc==3 && strcmp(argv[1],"--strict")==0) {
        strict=1;
        folder=argv[2];
    } else {
        fprintf(stderr,"Usage: vh_music_bank_audit [--strict] <audio-root>\n"
            "Requires audio-root/{field,selected}/{music.seq,music.vh,music.vb}\n");
        return 1;
    }

    VhGameMusicBanks *banks=NULL;
    const int result=vh_game_music_banks_load(&banks, folder);
    if (result!=VH_AUDIO_ASSET_OK) {
        fputs(result==VH_AUDIO_ASSET_MISSING
            ? "No complete music banks found in either scene directory.\n"
            : "Incomplete, invalid or over-budget SEQ/VH/VB music pack.\n",
            stderr);
        return result==VH_AUDIO_ASSET_MISSING?2:3;
    }
    printf("{\n  \"schema\": 1,\n");
    print_scene("field",&banks->field_audit,
                banks->field_fallback_notes,&banks->field_first_fallback);
    puts(",");
    print_scene("selected",&banks->selected_audit,
                banks->selected_fallback_notes,&banks->selected_first_fallback);
    puts("\n}");
    const unsigned issues=
        banks->field_audit.missing_notes +
        banks->selected_audit.missing_notes +
        banks->field_fallback_notes +
        banks->selected_fallback_notes;
    vh_game_music_banks_close(&banks);
    return strict && issues ? 4 : 0;
}
