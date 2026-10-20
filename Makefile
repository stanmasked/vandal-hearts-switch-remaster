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

test: $(BUILD)/test_map02_variable_rosters $(BUILD)/test_map02_two_scenarios $(BUILD)/test_map02_data_driven $(BUILD)/test_map02_battle_fixture $(BUILD)/test_game_rules $(BUILD)/test_software_renderer $(BUILD)/test_texture_sample $(BUILD)/test_ft4_textured_quad $(BUILD)/test_ps1_indexed_texture $(BUILD)/test_ps1_abr_blend $(BUILD)/test_map02_terrain_lighting $(BUILD)/test_map02_face_direction $(BUILD)/test_map02_projection $(BUILD)/test_map02_terrain_quad $(BUILD)/test_map02_source_projection_batch $(BUILD)/test_map02_captured_projection_batch $(BUILD)/test_map02_captured_vram4_bridge $(BUILD)/test_map02_terrain_ot_scene $(BUILD)/test_map02_external_gte_ft4 $(BUILD)/test_map02_vram4_page $(BUILD)/test_map02_vram4_frame
	./$(BUILD)/test_map02_variable_rosters
	./$(BUILD)/test_map02_two_scenarios
	./$(BUILD)/test_map02_data_driven
	./$(BUILD)/test_map02_battle_fixture
	./$(BUILD)/test_game_rules
	./$(BUILD)/test_software_renderer
	./$(BUILD)/test_texture_sample
	./$(BUILD)/test_ft4_textured_quad
	./$(BUILD)/test_ps1_indexed_texture
	./$(BUILD)/test_ps1_abr_blend
	./$(BUILD)/test_map02_terrain_lighting
	./$(BUILD)/test_map02_face_direction
	./$(BUILD)/test_map02_projection
	./$(BUILD)/test_map02_terrain_quad
	./$(BUILD)/test_map02_source_projection_batch
	./$(BUILD)/test_map02_captured_projection_batch
	./$(BUILD)/test_map02_captured_vram4_bridge
	./$(BUILD)/test_map02_terrain_ot_scene
	./$(BUILD)/test_map02_external_gte_ft4
	./$(BUILD)/test_map02_vram4_page
	./$(BUILD)/test_map02_vram4_frame
	python3 tools/generate_map02_fixture.py --all --check
	python3 -m unittest discover -s tests -p 'test_map02_variable_rosters.py' -v
	python3 -m unittest discover -s tests -p 'test_map02_two_scenarios.py' -v
	python3 -m unittest discover -s tests -p 'test_map02_encounter_data.py' -v
	python3 tests/test_restore_ps1_str.py
	python3 tests/test_inspect_cdxa.py
	python3 tests/test_inspect_land_dt.py
	python3 -m unittest discover -s tests -p 'test_validate_map02_manifest.py'
	python3 -m unittest discover -s tests -p 'test_check_map02_raw.py'
	python3 -m unittest discover -s tests -p 'test_compare_map02_variants.py'
	python3 -m unittest discover -s tests -p 'test_verify_map02_trace.py'
	python3 -m unittest discover -s tests -p 'test_audit_map02_load_source.py'
	python3 -m unittest discover -s tests -p 'test_audit_map02_disc_prs.py'
	python3 -m unittest discover -s tests -p 'test_audit_map02_archive.py'
	python3 -m unittest discover -s tests -p 'test_map02_texture_pixel_proof.py'
	python3 -m unittest discover -s tests -p 'test_map02_face_geometry.py'
	python3 -m unittest discover -s tests -p 'test_map02_multicell_probe.py'
	python3 -m unittest discover -s tests -p 'test_audit_map02_face_source.py'
	python3 -m unittest discover -s tests -p 'test_audit_map02_direction_source.py'
	python3 -m unittest discover -s tests -p 'test_verify_map02_unpack_equivalence.py'
	python3 -m unittest discover -s tests -p 'test_instrument_map02_loader.py'
	python3 -m unittest discover -s tests -p 'test_instrument_map02_renderer.py'
	python3 -m unittest discover -s tests -p 'test_map02_renderer_smoke.py'
	python3 -m unittest discover -s tests -p 'test_prepare_map02_pcport.py'
	python3 -m unittest discover -s tests -p 'test_extract_map02_trace.py'
	python3 -m unittest discover -s tests -p 'test_capture_map02_runtime.py'
	python3 -m unittest discover -s tests -p 'test_verify_map02_capture.py'
	python3 -m unittest discover -s tests -p 'test_evaluate_map02_session.py'
	python3 -m unittest discover -s tests -p 'test_report_map02_bridge.py'
	python3 -m unittest discover -s tests -p 'test_preflight_map02_pcport.py'
	python3 -m unittest discover -s tests -p 'test_prepare_map02_session.py'
	python3 -m unittest discover -s tests -p 'test_make_map02_trace_patch.py'
	python3 -m unittest discover -s tests -p 'test_map02_trace_c_emitter.py'
	python3 tests/test_extract_cdxa_payload.py
	python3 tests/test_decode_cdxa_adpcm.py

# Host-only memory and undefined-behavior checks; requires GCC or Clang sanitizers.
test-sanitize: | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map02_variable_rosters.c -o $(BUILD)/test_map02_variable_rosters_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map02_two_scenarios.c -o $(BUILD)/test_map02_two_scenarios_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map02_data_driven.c -o $(BUILD)/test_map02_data_driven_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map02_battle_fixture.c -o $(BUILD)/test_map02_battle_fixture_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_game_rules.c -o $(BUILD)/test_game_rules_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_software_renderer.c -o $(BUILD)/test_software_renderer_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_texture_sample.c -o $(BUILD)/test_texture_sample_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_ft4_textured_quad.c -o $(BUILD)/test_ft4_textured_quad_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_ps1_indexed_texture.c -o $(BUILD)/test_ps1_indexed_texture_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_ps1_abr_blend.c -o $(BUILD)/test_ps1_abr_blend_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map02_terrain_lighting.c -o $(BUILD)/test_map02_terrain_lighting_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map02_face_direction.c -o $(BUILD)/test_map02_face_direction_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map02_projection.c -o $(BUILD)/test_map02_projection_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map02_terrain_quad.c -o $(BUILD)/test_map02_terrain_quad_sanitize -lm
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map02_source_projection_batch.c -o $(BUILD)/test_map02_source_projection_batch_sanitize -lm
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map02_captured_projection_batch.c -o $(BUILD)/test_map02_captured_projection_batch_sanitize -lm
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map02_captured_vram4_bridge.c -o $(BUILD)/test_map02_captured_vram4_bridge_sanitize -lm
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map02_terrain_ot_scene.c -o $(BUILD)/test_map02_terrain_ot_scene_sanitize -lm
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map02_external_gte_ft4.c -o $(BUILD)/test_map02_external_gte_ft4_sanitize -lm
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map02_vram4_page.c -o $(BUILD)/test_map02_vram4_page_sanitize -lm
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map02_vram4_frame.c -o $(BUILD)/test_map02_vram4_frame_sanitize -lm
	./$(BUILD)/test_map02_variable_rosters_sanitize
	./$(BUILD)/test_map02_two_scenarios_sanitize
	./$(BUILD)/test_map02_data_driven_sanitize
	./$(BUILD)/test_map02_battle_fixture_sanitize
	./$(BUILD)/test_game_rules_sanitize
	./$(BUILD)/test_software_renderer_sanitize
	./$(BUILD)/test_texture_sample_sanitize
	./$(BUILD)/test_ft4_textured_quad_sanitize
	./$(BUILD)/test_ps1_indexed_texture_sanitize
	./$(BUILD)/test_ps1_abr_blend_sanitize
	./$(BUILD)/test_map02_terrain_lighting_sanitize
	./$(BUILD)/test_map02_face_direction_sanitize
	./$(BUILD)/test_map02_projection_sanitize
	./$(BUILD)/test_map02_terrain_quad_sanitize
	./$(BUILD)/test_map02_source_projection_batch_sanitize
	./$(BUILD)/test_map02_captured_projection_batch_sanitize
	./$(BUILD)/test_map02_captured_vram4_bridge_sanitize
	./$(BUILD)/test_map02_terrain_ot_scene_sanitize
	./$(BUILD)/test_map02_external_gte_ft4_sanitize
	./$(BUILD)/test_map02_vram4_page_sanitize
	./$(BUILD)/test_map02_vram4_frame_sanitize

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

$(BUILD)/test_map02_variable_rosters: tests/test_map02_variable_rosters.c source/map02_battle_fixture.h source/map02_encounter_data.h source/map02_encounter_b_data.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_map02_two_scenarios: tests/test_map02_two_scenarios.c source/map02_battle_fixture.h source/map02_encounter_data.h source/map02_encounter_b_data.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_map02_data_driven: tests/test_map02_data_driven.c source/map02_battle_fixture.h source/map02_encounter_data.h source/map02_encounter_b_data.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_map02_battle_fixture: tests/test_map02_battle_fixture.c source/map02_battle_fixture.h source/map02_encounter_data.h source/map02_encounter_b_data.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_game_rules: tests/test_game_rules.c source/game_rules.h source/game_state.h source/platform_input.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_software_renderer: tests/test_software_renderer.c source/software_renderer.h source/game_renderer.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_texture_sample: tests/test_texture_sample.c source/texture_sample.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_ft4_textured_quad: tests/test_ft4_textured_quad.c source/ft4_textured_quad.h source/software_renderer.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_ps1_indexed_texture: tests/test_ps1_indexed_texture.c source/ps1_indexed_texture.h source/ft4_textured_quad.h source/software_renderer.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_ps1_abr_blend: tests/test_ps1_abr_blend.c source/ps1_abr_blend.h source/ps1_indexed_texture.h source/ft4_textured_quad.h source/software_renderer.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_map02_terrain_lighting: tests/test_map02_terrain_lighting.c source/map02_terrain_lighting.h source/ps1_abr_blend.h source/ft4_textured_quad.h source/software_renderer.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_map02_face_direction: tests/test_map02_face_direction.c source/map02_face_direction.h source/map02_terrain_lighting.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_map02_projection: tests/test_map02_projection.c source/map02_projection.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_map02_terrain_quad: tests/test_map02_terrain_quad.c source/map02_terrain_quad.h source/map02_projection.h source/ft4_textured_quad.h source/ps1_indexed_texture.h source/software_renderer.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@ -lm

$(BUILD)/test_map02_source_projection_batch: tests/test_map02_source_projection_batch.c source/map02_source_projection_batch.h source/map02_terrain_ot_scene.h source/map02_terrain_quad.h source/map02_projection.h source/ft4_textured_quad.h source/ps1_indexed_texture.h source/software_renderer.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@ -lm

$(BUILD)/test_map02_captured_projection_batch: tests/test_map02_captured_projection_batch.c source/map02_captured_projection_batch.h source/map02_source_projection_batch.h source/map02_terrain_quad.h source/map02_projection.h source/ft4_textured_quad.h source/ps1_indexed_texture.h source/software_renderer.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@ -lm

$(BUILD)/test_map02_captured_vram4_bridge: tests/test_map02_captured_vram4_bridge.c source/map02_captured_vram4_bridge.h source/map02_vram4_transfer_import.h source/map02_vram4_transfer_ledger.h source/map02_vram4_timeline_frame.h source/map02_captured_projection_batch.h source/map02_source_projection_batch.h source/map02_vram4_frame.h source/map02_external_gte_ft4.h source/map02_vram4_page.h source/map02_terrain_ot_scene.h source/map02_terrain_quad.h source/map02_projection.h source/ft4_textured_quad.h source/ps1_indexed_texture.h source/software_renderer.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@ -lm

$(BUILD)/test_map02_terrain_ot_scene: tests/test_map02_terrain_ot_scene.c source/map02_terrain_ot_scene.h source/map02_terrain_quad.h source/map02_projection.h source/ft4_textured_quad.h source/ps1_indexed_texture.h source/software_renderer.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@ -lm

$(BUILD)/test_map02_external_gte_ft4: tests/test_map02_external_gte_ft4.c source/map02_external_gte_ft4.h source/map02_terrain_ot_scene.h source/map02_terrain_quad.h source/map02_projection.h source/ft4_textured_quad.h source/ps1_indexed_texture.h source/software_renderer.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@ -lm

$(BUILD)/test_map02_vram4_page: tests/test_map02_vram4_page.c source/map02_vram4_page.h source/map02_external_gte_ft4.h source/map02_terrain_ot_scene.h source/map02_terrain_quad.h source/map02_projection.h source/ft4_textured_quad.h source/ps1_indexed_texture.h source/software_renderer.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@ -lm

$(BUILD)/test_map02_vram4_frame: tests/test_map02_vram4_frame.c source/map02_vram4_frame.h source/map02_vram4_page.h source/map02_external_gte_ft4.h source/map02_terrain_ot_scene.h source/map02_terrain_quad.h source/map02_projection.h source/ft4_textured_quad.h source/ps1_indexed_texture.h source/software_renderer.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@ -lm

$(BUILD)/$(TARGET).elf: $(SOURCES)/main.c $(SOURCES)/map02_battle_fixture.h $(SOURCES)/map02_encounter_data.h $(SOURCES)/map02_encounter_b_data.h $(SOURCES)/game_rules.h $(SOURCES)/game_state.h $(SOURCES)/platform_input.h $(SOURCES)/software_renderer.h $(SOURCES)/game_renderer.h $(SOURCES)/ft4_textured_quad.h $(SOURCES)/ps1_indexed_texture.h $(SOURCES)/ps1_abr_blend.h $(SOURCES)/map02_terrain_lighting.h $(SOURCES)/map02_face_direction.h | $(BUILD)
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


# Asset-free, SDL2-independent combined software-video + native audout NRO.
# This demonstrates the integration boundary; not original music or gameplay.
.PHONY: native-av-probe test-native-tone

test-native-tone: $(BUILD)/test_native_tone
	./$(BUILD)/test_native_tone

$(BUILD)/test_native_tone: tests/test_native_tone.c source/vh_native_tone.h | $(BUILD)
	$(HOST_CC) -std=c11 -O2 -Wall -Wextra -Werror $< -o $@

$(BUILD)/libnx-av-switch-probe.elf: probes/libnx_av_smoke.c source/vh_native_tone.h source/game_state.h source/game_renderer.h source/software_renderer.h source/platform_input.h | $(BUILD)
	$(CC) $(CFLAGS) -std=c11 -Isource $(LDFLAGS) $< -o $@ $(LDLIBS)

$(BUILD)/libnx-av-switch-probe.nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts Native AV Probe" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/libnx-av-switch-probe.nro: $(BUILD)/libnx-av-switch-probe.elf $(BUILD)/libnx-av-switch-probe.nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/libnx-av-switch-probe.nacp

native-av-probe: $(BUILD)/libnx-av-switch-probe.nro
	python3 tests/check_nro.py $<
