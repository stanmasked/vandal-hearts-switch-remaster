# Minimal devkitPro/libnx homebrew prototype.
# This does not port the original Vandal Hearts game yet.

DEVKITPRO ?= /opt/devkitpro
DEVKITA64 ?= $(DEVKITPRO)/devkitA64
TARGET     := vandal-hearts-prototype
SDL2_TARGET := sdl2-switch-probe
SDL2_GL_TARGET := sdl2-gl-switch-probe
SDL2_TEXTURE_TARGET := sdl2-texture-switch-probe

SDL2_AUDIO_TARGET := sdl2-audio-switch-probe
AUDOUT_AUDIO_TARGET := audout-audio-switch-probe
AUDOUT_BUILD_REV := $(shell git rev-parse --verify HEAD 2>/dev/null || printf UNKNOWN)
# Explicitly distinguish a clean checkout from a modified or unpacked tree.
# This is source provenance, not the SHA-256 of the resulting NRO.
AUDOUT_BUILD_STATUS := $(shell if git rev-parse --is-inside-work-tree 2>/dev/null | grep -qx true; then if git status --porcelain --untracked-files=normal 2>/dev/null | grep -q .; then printf MODIFIED; else printf CLEAN; fi; else printf NO-GIT; fi)
OPENAL_TARGET := openal-switch-probe
SDL2_CONFIG ?= $(DEVKITPRO)/portlibs/switch/bin/sdl2-config
BUILD      := build
SOURCES    := source
APP_TITLE  := Vandal Hearts Switch Prototype
APP_AUTHOR := Vandal Hearts Switch Remaster contributors
APP_VERSION := 0.1.0

CC       := $(DEVKITA64)/bin/aarch64-none-elf-gcc
HOST_CC  ?= gcc
ELF2NRO  := $(DEVKITPRO)/tools/bin/elf2nro
NACPTOOL := $(DEVKITPRO)/tools/bin/nacptool
CFLAGS   := -g -Wall -Wextra -O2 -fPIE -ffunction-sections -fdata-sections -I$(DEVKITPRO)/libnx/include
LDFLAGS  := -specs=$(DEVKITPRO)/libnx/switch.specs -Wl,--gc-sections -pie
LDLIBS   := -L$(DEVKITPRO)/libnx/lib -lnx

.PHONY: all clean test test-audio-stream test-local-music-transition test-sanitize verify-nro sdl2-probe sdl2-gl-probe sdl2-texture-probe sdl2-audio-probe audout-audio-probe openal-probe
all: $(BUILD)/$(TARGET).nro

test: $(BUILD)/test_game_rules $(BUILD)/test_software_renderer $(BUILD)/test_vh_audio_stream $(BUILD)/test_vh_native_spu $(BUILD)/test_vh_native_seq $(BUILD)/test_vh_native_vab $(BUILD)/test_vh_audio_assets $(BUILD)/test_vh_audio_resample $(BUILD)/test_vh_spu_reverb $(BUILD)/test_vh_native_audio_soak $(BUILD)/test_vh_audio_output_recovery $(BUILD)/test_vh_audio_pcm_seams $(BUILD)/test_vh_audio_listening_marks $(BUILD)/test_vh_audio_listening_oracle $(BUILD)/test_vh_audio_input_poll $(BUILD)/test_vh_audio_mark_buttons $(BUILD)/test_vh_audio_listener_input $(BUILD)/test_vh_audio_compute_timing $(BUILD)/test_vh_audio_compute_wait_join $(BUILD)/test_vh_audio_page_telemetry $(BUILD)/test_vh_audio_resume_abort_telemetry $(BUILD)/test_vh_decoded_vab_audout $(BUILD)/test_vh_audio_report_pages
	./$(BUILD)/test_game_rules
	./$(BUILD)/test_software_renderer
	./$(BUILD)/test_vh_audio_stream
	./$(BUILD)/test_vh_native_spu
	./$(BUILD)/test_vh_native_seq
	./$(BUILD)/test_vh_native_vab
	./$(BUILD)/test_vh_audio_assets
	./$(BUILD)/test_vh_audio_resample
	./$(BUILD)/test_vh_spu_reverb
	./$(BUILD)/test_vh_native_audio_soak
	./$(BUILD)/test_vh_audio_output_recovery
	./$(BUILD)/test_vh_audio_pcm_seams
	./$(BUILD)/test_vh_audio_listening_marks
	./$(BUILD)/test_vh_audio_listening_oracle
	./$(BUILD)/test_vh_audio_input_poll
	./$(BUILD)/test_vh_audio_mark_buttons
	./$(BUILD)/test_vh_audio_listener_input
	./$(BUILD)/test_vh_audio_compute_timing
	./$(BUILD)/test_vh_audio_compute_wait_join
	./$(BUILD)/test_vh_audio_page_telemetry
	./$(BUILD)/test_vh_audio_resume_abort_telemetry
	./$(BUILD)/test_vh_decoded_vab_audout
	./$(BUILD)/test_vh_audio_report_pages
	python3 tests/test_audout_report_layout.py
	python3 tests/test_restore_ps1_str.py
	python3 tests/test_inspect_cdxa.py
	python3 tests/test_extract_cdxa_payload.py
	python3 tests/test_decode_cdxa_adpcm.py
	python3 tests/test_cdxa_pipeline.py
	python3 tests/test_validate_cdxa_extraction.py
	python3 tests/test_analyze_cdxa_boundaries.py
	python3 tests/test_compare_cdxa_wavs.py
	python3 tests/test_run_cdxa_local_check.py
	python3 tests/test_analyze_cdxa_wav_quality.py
	python3 tests/test_inventory_cdxa_streams.py
	python3 tests/test_inspect_spu_vag.py
	python3 tests/test_inspect_vab_header.py
	python3 tests/test_inspect_vab_sizes.py
	python3 tests/test_decode_spu_adpcm.py
	python3 tests/test_decode_vab_sample.py
	python3 tests/test_resolve_vab_note.py
	python3 tests/test_simulate_spu_voice.py
	python3 tests/test_render_vab_note.py
	python3 tests/test_spu_gaussian_interpolation.py
	python3 tests/test_mix_spu_stereo.py
	python3 tests/test_inspect_ps1_seq.py
	python3 tests/test_seq_to_chord_schedule.py
	python3 tests/test_render_ps1_seq.py
	python3 tests/test_seq_voice_slots.py
	python3 tests/test_repeat_ps1_seq.py
	python3 tests/test_spu_voice_lifetime.py
	python3 tests/test_schedule_ps1_seq_blocks.py
	python3 tests/test_native_spu_adpcm.py
	python3 tests/test_native_vab_python_reference.py
	python3 tests/test_native_spu_reverb_reference.py
	python3 tests/test_native_seq_timing_adsr_reference.py

test-audio-stream: $(BUILD)/test_vh_audio_stream $(BUILD)/test_vh_native_spu $(BUILD)/test_vh_native_seq $(BUILD)/test_vh_native_vab $(BUILD)/test_vh_audio_assets $(BUILD)/test_vh_audio_resample $(BUILD)/test_vh_spu_reverb $(BUILD)/test_vh_native_audio_soak $(BUILD)/test_vh_audio_output_recovery $(BUILD)/test_vh_audio_pcm_seams $(BUILD)/test_vh_audio_listening_marks $(BUILD)/test_vh_audio_listening_oracle $(BUILD)/test_vh_audio_input_poll $(BUILD)/test_vh_audio_mark_buttons $(BUILD)/test_vh_audio_listener_input $(BUILD)/test_vh_audio_compute_timing $(BUILD)/test_vh_audio_compute_wait_join $(BUILD)/test_vh_audio_page_telemetry $(BUILD)/test_vh_audio_resume_abort_telemetry $(BUILD)/test_vh_decoded_vab_audout $(BUILD)/test_vh_audio_report_pages $(BUILD)/vh_local_music_transition_probe
	./$(BUILD)/test_vh_audio_stream
	./$(BUILD)/test_vh_native_spu
	./$(BUILD)/test_vh_native_seq
	./$(BUILD)/test_vh_native_vab
	./$(BUILD)/test_vh_audio_assets
	./$(BUILD)/test_vh_audio_resample
	./$(BUILD)/test_vh_spu_reverb
	./$(BUILD)/test_vh_native_audio_soak
	./$(BUILD)/test_vh_audio_output_recovery
	./$(BUILD)/test_vh_audio_pcm_seams
	./$(BUILD)/test_vh_audio_listening_marks
	./$(BUILD)/test_vh_audio_listening_oracle
	./$(BUILD)/test_vh_audio_input_poll
	./$(BUILD)/test_vh_audio_mark_buttons
	./$(BUILD)/test_vh_audio_listener_input
	./$(BUILD)/test_vh_audio_compute_timing
	./$(BUILD)/test_vh_audio_compute_wait_join
	./$(BUILD)/test_vh_audio_page_telemetry
	./$(BUILD)/test_vh_audio_resume_abort_telemetry
	./$(BUILD)/test_vh_decoded_vab_audout
	./$(BUILD)/test_vh_audio_report_pages
	python3 tests/test_audout_report_layout.py
	python3 tests/test_native_spu_adpcm.py
	python3 tests/test_native_spu_gaussian.py
	python3 tests/test_native_vab_python_reference.py
	python3 tests/test_native_spu_reverb_reference.py
	python3 tests/test_native_seq_timing_adsr_reference.py
	python3 -m unittest discover -s tests -p 'test_vh_local_music_transition_probe.py' -v
test-local-music-transition: $(BUILD)/vh_local_music_transition_probe
	python3 -m unittest discover -s tests -p 'test_vh_local_music_transition_probe.py' -v


# Host-only memory and undefined-behavior checks; requires GCC or Clang sanitizers.
test-sanitize: | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_game_rules.c -o $(BUILD)/test_game_rules_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_software_renderer.c -o $(BUILD)/test_software_renderer_sanitize
	./$(BUILD)/test_game_rules_sanitize
	./$(BUILD)/test_software_renderer_sanitize

verify-nro: $(BUILD)/$(TARGET).nro
	python3 tests/check_nro.py $<

sdl2-probe: $(BUILD)/$(SDL2_TARGET).nro
	python3 tests/check_nro.py $<

sdl2-gl-probe: $(BUILD)/$(SDL2_GL_TARGET).nro
	python3 tests/check_nro.py $<

sdl2-texture-probe: $(BUILD)/$(SDL2_TEXTURE_TARGET).nro
	python3 tests/check_nro.py $<

openal-probe: $(BUILD)/$(OPENAL_TARGET).nro
	python3 tests/check_nro.py $<

sdl2-audio-probe: $(BUILD)/$(SDL2_AUDIO_TARGET).nro
	python3 tests/check_nro.py $<

audout-audio-probe: $(BUILD)/$(AUDOUT_AUDIO_TARGET).nro
	python3 tests/check_nro.py $<

$(BUILD):
	mkdir -p $@

$(BUILD)/test_game_rules: tests/test_game_rules.c source/game_rules.h source/game_state.h source/platform_input.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_software_renderer: tests/test_software_renderer.c source/software_renderer.h source/game_renderer.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_vh_audio_stream: tests/test_vh_audio_stream.c source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_stream.c source/vh_audio_stream.c -o $@

$(BUILD)/test_vh_native_audio_soak: tests/test_vh_native_audio_soak.c source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_native_spu.h source/vh_spu_reverb.c source/vh_spu_reverb.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_audio_resample.c source/vh_audio_resample.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_native_audio_soak.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_audio_resample.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/vh_local_music_transition_probe: tools/vh_local_music_transition_probe.c source/vh_audio_assets.c source/vh_audio_assets.h source/vh_native_vab.c source/vh_native_vab.h source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_native_spu.h source/vh_spu_reverb.c source/vh_spu_adpcm.c source/vh_spu_gaussian.c source/vh_audio_resample.c source/vh_audio_resample.h source/vh_audio_stream.c | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tools/vh_local_music_transition_probe.c source/vh_audio_assets.c source/vh_native_vab.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_adpcm.c source/vh_spu_gaussian.c source/vh_audio_resample.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_audio_report_pages: tests/test_vh_audio_report_pages.c source/vh_audio_report_pages.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource $< -o $@

$(BUILD)/test_vh_decoded_vab_audout: tests/test_vh_decoded_vab_audout.c source/vh_native_vab.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_spu_adpcm.c source/vh_audio_resample.c source/vh_audio_output_recovery.c source/vh_audio_page_telemetry.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource $< source/vh_native_vab.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_spu_adpcm.c source/vh_audio_resample.c source/vh_audio_output_recovery.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_audio_resume_abort_telemetry: tests/test_vh_audio_resume_abort_telemetry.c source/vh_audio_page_telemetry.h source/vh_audio_report_pages.h source/vh_audio_compute_wait_join.h source/vh_audio_listening_marks.h source/vh_audio_output_recovery.h source/vh_audio_output_recovery.c | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource $< source/vh_audio_output_recovery.c -o $@

$(BUILD)/test_vh_audio_page_telemetry: tests/test_vh_audio_page_telemetry.c source/vh_audio_page_telemetry.h source/vh_audio_compute_wait_join.h source/vh_audio_listening_marks.h source/vh_audio_compute_timing.h source/vh_audio_output_recovery.h source/vh_audio_output_recovery.c | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource $< source/vh_audio_output_recovery.c -o $@

$(BUILD)/test_vh_audio_compute_wait_join: tests/test_vh_audio_compute_wait_join.c source/vh_audio_compute_wait_join.h source/vh_audio_compute_timing.h source/vh_audio_output_recovery.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource $< -o $@

$(BUILD)/test_vh_audio_compute_timing: tests/test_vh_audio_compute_timing.c source/vh_audio_compute_timing.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource $< -o $@

$(BUILD)/test_vh_audio_listener_input: tests/test_vh_audio_listener_input.c source/vh_audio_listener_input.h source/vh_audio_mark_buttons.h source/vh_audio_listening_marks.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource $< -o $@

$(BUILD)/test_vh_audio_mark_buttons: tests/test_vh_audio_mark_buttons.c source/vh_audio_mark_buttons.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource $< -o $@

$(BUILD)/test_vh_audio_input_poll: tests/test_vh_audio_input_poll.c source/vh_audio_input_poll.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource $< -o $@

$(BUILD)/test_vh_audio_listening_oracle: tests/test_vh_audio_listening_oracle.c source/vh_audio_listening_marks.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource $< -o $@

$(BUILD)/test_vh_audio_listening_marks: tests/test_vh_audio_listening_marks.c source/vh_audio_listening_marks.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource $< -o $@

$(BUILD)/test_vh_audio_pcm_seams: tests/test_vh_audio_pcm_seams.c source/vh_audio_output_recovery.c source/vh_audio_output_recovery.h source/vh_audio_resample.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_pcm_seams.c source/vh_audio_output_recovery.c -o $@

$(BUILD)/test_vh_audio_output_recovery: tests/test_vh_audio_output_recovery.c source/vh_audio_output_recovery.c source/vh_audio_output_recovery.h source/vh_audio_resample.c source/vh_audio_resample.h source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_native_spu.h source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_audio_stream.c | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_output_recovery.c source/vh_audio_output_recovery.c source/vh_audio_resample.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_spu_reverb: tests/test_vh_spu_reverb.c source/vh_spu_reverb.c source/vh_spu_reverb.h source/vh_native_spu.c source/vh_native_spu.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_spu_reverb.c source/vh_spu_reverb.c source/vh_native_spu.c source/vh_spu_gaussian.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_native_spu: tests/test_vh_native_spu.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_native_spu.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_spu_adpcm.c source/vh_spu_adpcm.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_native_spu.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_spu_adpcm.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_native_vab: tests/test_vh_native_vab.c source/vh_native_vab.c source/vh_native_vab.h source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_spu_reverb.c source/vh_native_spu.h source/vh_spu_adpcm.c source/vh_spu_adpcm.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_native_vab.c source/vh_native_vab.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_adpcm.c source/vh_spu_gaussian.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_audio_resample: tests/test_vh_audio_resample.c source/vh_audio_resample.c source/vh_audio_resample.h source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_resample.c source/vh_audio_resample.c -o $@

$(BUILD)/test_vh_audio_assets: tests/test_vh_audio_assets.c source/vh_audio_assets.c source/vh_audio_assets.h source/vh_native_vab.c source/vh_native_vab.h source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_spu_reverb.c source/vh_native_spu.h source/vh_spu_adpcm.c source/vh_spu_adpcm.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_assets.c source/vh_audio_assets.c source/vh_native_vab.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_adpcm.c source/vh_spu_gaussian.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_native_seq: tests/test_vh_native_seq.c source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_spu_reverb.c source/vh_native_spu.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_native_seq.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/$(TARGET).elf: $(SOURCES)/main.c $(SOURCES)/game_rules.h $(SOURCES)/game_state.h $(SOURCES)/platform_input.h $(SOURCES)/software_renderer.h $(SOURCES)/game_renderer.h | $(BUILD)
	$(CC) $(CFLAGS) $(LDFLAGS) $< -o $@ $(LDLIBS)

$(BUILD)/$(TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "$(APP_TITLE)" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(TARGET).nro: $(BUILD)/$(TARGET).elf $(BUILD)/$(TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(TARGET).nacp

$(BUILD)/$(SDL2_TARGET).elf: probes/sdl2_smoke.c source/game_rules.h source/game_state.h | $(BUILD)
	$(CC) $(CFLAGS) -Isource $(LDFLAGS) $(shell $(SDL2_CONFIG) --cflags) $< -o $@ $(shell $(SDL2_CONFIG) --libs) $(LDLIBS) -lm

$(BUILD)/$(SDL2_TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts SDL2 Probe" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(SDL2_TARGET).nro: $(BUILD)/$(SDL2_TARGET).elf $(BUILD)/$(SDL2_TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(SDL2_TARGET).nacp

$(BUILD)/$(SDL2_GL_TARGET).elf: probes/sdl2_gl_smoke.c | $(BUILD)
	$(CC) $(CFLAGS) $(LDFLAGS) $(shell $(SDL2_CONFIG) --cflags) $< -o $@ $(shell $(SDL2_CONFIG) --libs) -lGLESv2 $(LDLIBS) -lm

$(BUILD)/$(SDL2_GL_TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts SDL2 GL Probe" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(SDL2_GL_TARGET).nro: $(BUILD)/$(SDL2_GL_TARGET).elf $(BUILD)/$(SDL2_GL_TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(SDL2_GL_TARGET).nacp

$(BUILD)/$(SDL2_TEXTURE_TARGET).elf: probes/sdl2_texture_smoke.c source/game_rules.h source/game_state.h | $(BUILD)
	$(CC) $(CFLAGS) -Isource $(LDFLAGS) $(shell $(SDL2_CONFIG) --cflags) $< -o $@ $(shell $(SDL2_CONFIG) --libs) -lGLESv2 $(LDLIBS) -lm

$(BUILD)/$(SDL2_TEXTURE_TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts SDL2 Texture Probe" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(SDL2_TEXTURE_TARGET).nro: $(BUILD)/$(SDL2_TEXTURE_TARGET).elf $(BUILD)/$(SDL2_TEXTURE_TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(SDL2_TEXTURE_TARGET).nacp


$(BUILD)/$(SDL2_AUDIO_TARGET).elf: probes/sdl2_audio_smoke.c source/vh_audio_stream.c source/vh_audio_stream.h source/vh_spu_adpcm.c source/vh_spu_adpcm.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_native_spu.c source/vh_spu_reverb.c source/vh_native_spu.h source/vh_native_seq.c source/vh_native_seq.h source/vh_native_vab.c source/vh_native_vab.h source/vh_audio_assets.c source/vh_audio_assets.h | $(BUILD)
	$(CC) $(CFLAGS) -Isource $(LDFLAGS) $(shell $(SDL2_CONFIG) --cflags) probes/sdl2_audio_smoke.c source/vh_audio_stream.c source/vh_spu_adpcm.c source/vh_spu_gaussian.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_native_seq.c source/vh_native_vab.c source/vh_audio_assets.c -o $@ $(shell $(SDL2_CONFIG) --libs) $(LDLIBS) -lm

$(BUILD)/$(SDL2_AUDIO_TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts SDL2 Audio Probe" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(SDL2_AUDIO_TARGET).nro: $(BUILD)/$(SDL2_AUDIO_TARGET).elf $(BUILD)/$(SDL2_AUDIO_TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(SDL2_AUDIO_TARGET).nacp

$(BUILD)/$(AUDOUT_AUDIO_TARGET).elf: probes/audout_audio_smoke.c source/vh_audio_resample.c source/vh_audio_resample.h source/vh_audio_output_recovery.c source/vh_audio_output_recovery.h source/vh_audio_listening_marks.h source/vh_audio_mark_buttons.h source/vh_audio_listener_input.h source/vh_audio_input_poll.h source/vh_audio_compute_timing.h source/vh_audio_compute_wait_join.h source/vh_audio_page_telemetry.h source/vh_audio_report_pages.h source/vh_audio_assets.c source/vh_audio_assets.h source/vh_native_vab.c source/vh_native_vab.h source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_spu_reverb.c source/vh_native_spu.h source/vh_spu_adpcm.c source/vh_spu_adpcm.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(CC) $(CFLAGS) -DVH_AUDIO_BUILD_REV=\"$(AUDOUT_BUILD_REV)\" -DVH_AUDIO_BUILD_STATUS=\"$(AUDOUT_BUILD_STATUS)\" -Isource $(LDFLAGS) probes/audout_audio_smoke.c source/vh_audio_resample.c source/vh_audio_output_recovery.c source/vh_audio_assets.c source/vh_native_vab.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_adpcm.c source/vh_spu_gaussian.c source/vh_audio_stream.c -o $@ $(LDLIBS) -lm

$(BUILD)/$(AUDOUT_AUDIO_TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts Native Audout Audio" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(AUDOUT_AUDIO_TARGET).nro: $(BUILD)/$(AUDOUT_AUDIO_TARGET).elf $(BUILD)/$(AUDOUT_AUDIO_TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(AUDOUT_AUDIO_TARGET).nacp

$(BUILD)/$(OPENAL_TARGET).elf: probes/openal_smoke.c | $(BUILD)
	$(CC) $(CFLAGS) $(LDFLAGS) $(shell $(SDL2_CONFIG) --cflags) $< -o $@ -lopenal $(shell $(SDL2_CONFIG) --libs) $(LDLIBS) -lm

$(BUILD)/$(OPENAL_TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts OpenAL Probe" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(OPENAL_TARGET).nro: $(BUILD)/$(OPENAL_TARGET).elf $(BUILD)/$(OPENAL_TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(OPENAL_TARGET).nacp

clean:
	rm -rf $(BUILD)


# Combined native libnx framebuffer plus PS1 SEQ/VAB/SPU sound transport.
# A separate experimental NRO: never packages original music or game assets.
.PHONY: ps1-music-av-probe

PS1_MUSIC_AV_SOURCES := probes/libnx_ps1_music_av.c source/vh_audio_resample.c \
	source/vh_audio_output_recovery.c \
	source/vh_audio_assets.c source/vh_native_vab.c source/vh_native_seq.c \
	source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_adpcm.c \
	source/vh_spu_gaussian.c source/vh_audio_stream.c

$(BUILD)/libnx-ps1-music-av.elf: $(PS1_MUSIC_AV_SOURCES) \
	source/vh_audio_output_recovery.h \
	source/vh_audio_assets.h source/vh_audio_resample.h \
	source/vh_native_spu.h source/vh_native_seq.h \
	source/game_renderer.h source/game_state.h | $(BUILD)
	$(CC) $(CFLAGS) -std=c11 -Isource $(LDFLAGS) $(PS1_MUSIC_AV_SOURCES) -o $@ $(LDLIBS) -lm

$(BUILD)/libnx-ps1-music-av.nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts PS1 Music AV Prototype" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/libnx-ps1-music-av.nro: $(BUILD)/libnx-ps1-music-av.elf $(BUILD)/libnx-ps1-music-av.nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/libnx-ps1-music-av.nacp

ps1-music-av-probe: $(BUILD)/libnx-ps1-music-av.nro
	python3 tests/check_nro.py $<

# Dedicated CI-only NeXium build: the normal AV NRO is unchanged.
# Trigger exactly one synthetic ZR-style wrapper failure after real
# guest audout returns, then prove recovery and immutable PS1 music state.
.PHONY: ps1-music-av-zr-probe

$(BUILD)/libnx-ps1-music-av-zr.elf: $(PS1_MUSIC_AV_SOURCES) \
	source/vh_audio_output_recovery.h source/game_renderer.h \
	source/game_state.h | $(BUILD)
	$(CC) $(CFLAGS) -std=c11 -DVH_AUDIO_GUEST_ZR_AUTOTEST=1 -Isource \
		$(LDFLAGS) $(PS1_MUSIC_AV_SOURCES) -o $@ $(LDLIBS) -lm

$(BUILD)/libnx-ps1-music-av-zr.nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts AV ZR Guest Witness" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/libnx-ps1-music-av-zr.nro: $(BUILD)/libnx-ps1-music-av-zr.elf $(BUILD)/libnx-ps1-music-av-zr.nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/libnx-ps1-music-av-zr.nacp

ps1-music-av-zr-probe: $(BUILD)/libnx-ps1-music-av-zr.nro
	python3 tests/check_nro.py $<

# An independent CI-only guest BAD-CLOCK probe: successful audout
# descriptor return + rejected timing telemetry MUST NOT replay PCM.
.PHONY: ps1-music-av-zl-probe

$(BUILD)/libnx-ps1-music-av-zl.elf: $(PS1_MUSIC_AV_SOURCES) \
	source/vh_audio_output_recovery.h source/game_renderer.h \
	source/game_state.h | $(BUILD)
	$(CC) $(CFLAGS) -std=c11 -DVH_AUDIO_GUEST_ZL_AUTOTEST=1 -Isource \
		$(LDFLAGS) $(PS1_MUSIC_AV_SOURCES) -o $@ $(LDLIBS) -lm

$(BUILD)/libnx-ps1-music-av-zl.nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts AV ZL Guest Witness" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/libnx-ps1-music-av-zl.nro: $(BUILD)/libnx-ps1-music-av-zl.elf $(BUILD)/libnx-ps1-music-av-zl.nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/libnx-ps1-music-av-zl.nacp

ps1-music-av-zl-probe: $(BUILD)/libnx-ps1-music-av-zl.nro
	python3 tests/check_nro.py $<

# A separate CI-only guest device lifecycle test. After returned PCM
# exercise serialized stop/start then forced stop/close/open/start,
# verifying that the NEXT service descriptor returns after each action.
.PHONY: ps1-music-av-resume-probe

$(BUILD)/libnx-ps1-music-av-resume.elf: $(PS1_MUSIC_AV_SOURCES) \
	source/vh_audio_output_recovery.h source/game_renderer.h \
	source/game_state.h | $(BUILD)
	$(CC) $(CFLAGS) -std=c11 -DVH_AUDIO_GUEST_RESUME_AUTOTEST=1 -Isource \
		$(LDFLAGS) $(PS1_MUSIC_AV_SOURCES) -o $@ $(LDLIBS) -lm

$(BUILD)/libnx-ps1-music-av-resume.nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts AV Resume Guest" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/libnx-ps1-music-av-resume.nro: $(BUILD)/libnx-ps1-music-av-resume.elf $(BUILD)/libnx-ps1-music-av-resume.nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/libnx-ps1-music-av-resume.nacp

ps1-music-av-resume-probe: $(BUILD)/libnx-ps1-music-av-resume.nro
	python3 tests/check_nro.py $<

# CI-only forced reopen with ONE synthetic pre-service open failure.
# Verifies bounded second attempt AND subsequently returned PCM.
.PHONY: ps1-music-av-resume-retry-probe

$(BUILD)/libnx-ps1-music-av-resume-retry.elf: $(PS1_MUSIC_AV_SOURCES) \
	source/vh_audio_output_recovery.h source/game_renderer.h \
	source/game_state.h | $(BUILD)
	$(CC) $(CFLAGS) -std=c11 -DVH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST=1 -Isource \
		$(LDFLAGS) $(PS1_MUSIC_AV_SOURCES) -o $@ $(LDLIBS) -lm

$(BUILD)/libnx-ps1-music-av-resume-retry.nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts AV Resume Retry" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/libnx-ps1-music-av-resume-retry.nro: $(BUILD)/libnx-ps1-music-av-resume-retry.elf $(BUILD)/libnx-ps1-music-av-resume-retry.nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/libnx-ps1-music-av-resume-retry.nacp

ps1-music-av-resume-retry-probe: $(BUILD)/libnx-ps1-music-av-resume-retry.nro
	python3 tests/check_nro.py $<

# Console-only HOME/sleep focus-event instrumentation. No automatic
# stop/reopen or simulated inputs; requires manual physical testing.
.PHONY: ps1-music-av-focus-probe

$(BUILD)/libnx-ps1-music-av-focus.elf: $(PS1_MUSIC_AV_SOURCES) \
	source/vh_audio_output_recovery.h source/game_renderer.h \
	source/game_state.h | $(BUILD)
	$(CC) $(CFLAGS) -std=c11 -DVH_AUDIO_HARDWARE_FOCUS_TRACE=1 -Isource \
		$(LDFLAGS) $(PS1_MUSIC_AV_SOURCES) -o $@ $(LDLIBS) -lm

$(BUILD)/libnx-ps1-music-av-focus.nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts AV Focus Trace" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/libnx-ps1-music-av-focus.nro: $(BUILD)/libnx-ps1-music-av-focus.elf $(BUILD)/libnx-ps1-music-av-focus.nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/libnx-ps1-music-av-focus.nacp

ps1-music-av-focus-probe: $(BUILD)/libnx-ps1-music-av-focus.nro
	python3 tests/check_nro.py $<
