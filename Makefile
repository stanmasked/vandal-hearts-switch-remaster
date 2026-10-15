# Minimal devkitPro/libnx homebrew prototype.
# This does not port the original Vandal Hearts game yet.

DEVKITPRO ?= /opt/devkitpro
DEVKITA64 ?= $(DEVKITPRO)/devkitA64
TARGET     := vandal-hearts-prototype
SDL2_TARGET := sdl2-switch-probe
SDL2_GL_TARGET := sdl2-gl-switch-probe
SDL2_TEXTURE_TARGET := sdl2-texture-switch-probe

SDL2_AUDIO_TARGET := sdl2-audio-switch-probe
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

.PHONY: all clean test test-sanitize verify-nro sdl2-probe sdl2-gl-probe sdl2-texture-probe sdl2-audio-probe openal-probe
all: $(BUILD)/$(TARGET).nro

test: $(BUILD)/test_game_rules $(BUILD)/test_software_renderer
	./$(BUILD)/test_game_rules
	./$(BUILD)/test_software_renderer
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

$(BUILD):
	mkdir -p $@

$(BUILD)/test_game_rules: tests/test_game_rules.c source/game_rules.h source/game_state.h source/platform_input.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_software_renderer: tests/test_software_renderer.c source/software_renderer.h source/game_renderer.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

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


$(BUILD)/$(SDL2_AUDIO_TARGET).elf: probes/sdl2_audio_smoke.c | $(BUILD)
	$(CC) $(CFLAGS) $(LDFLAGS) $(shell $(SDL2_CONFIG) --cflags) $< -o $@ $(shell $(SDL2_CONFIG) --libs) $(LDLIBS) -lm

$(BUILD)/$(SDL2_AUDIO_TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts SDL2 Audio Probe" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(SDL2_AUDIO_TARGET).nro: $(BUILD)/$(SDL2_AUDIO_TARGET).elf $(BUILD)/$(SDL2_AUDIO_TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(SDL2_AUDIO_TARGET).nacp

$(BUILD)/$(OPENAL_TARGET).elf: probes/openal_smoke.c | $(BUILD)
	$(CC) $(CFLAGS) $(LDFLAGS) $(shell $(SDL2_CONFIG) --cflags) $< -o $@ -lopenal $(shell $(SDL2_CONFIG) --libs) $(LDLIBS) -lm

$(BUILD)/$(OPENAL_TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts OpenAL Probe" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(OPENAL_TARGET).nro: $(BUILD)/$(OPENAL_TARGET).elf $(BUILD)/$(OPENAL_TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(OPENAL_TARGET).nacp

clean:
	rm -rf $(BUILD)
