# Minimal devkitPro/libnx homebrew prototype.
# This does not port the original Vandal Hearts game yet.

DEVKITPRO ?= /opt/devkitpro
DEVKITA64 ?= $(DEVKITPRO)/devkitA64
TARGET     := vandal-hearts-prototype
SDL2_TARGET := sdl2-switch-probe
SDL2_GL_TARGET := sdl2-gl-switch-probe
SDL2_TEXTURE_TARGET := sdl2-texture-switch-probe
RGB24_TEXTURE_TARGET := rgb24-texture-switch-probe

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

.PHONY: all clean test test-sanitize verify-nro sdl2-probe sdl2-gl-probe sdl2-texture-probe rgb24-texture-probe sdl2-audio-probe openal-probe
all: $(BUILD)/$(TARGET).nro

test: $(BUILD)/private_map_bank_bridge  $(BUILD)/test_game_rules $(BUILD)/test_software_renderer $(BUILD)/test_rgb24_frame $(BUILD)/test_switch_presenter_layout $(BUILD)/test_ps1_memory_view $(BUILD)/test_map_buffer_gate $(BUILD)/test_map_decode_checked $(BUILD)/test_map_load_checked $(BUILD)/test_private_map_bank
	./$(BUILD)/test_game_rules
	./$(BUILD)/test_software_renderer
	./$(BUILD)/test_rgb24_frame
	./$(BUILD)/test_switch_presenter_layout
	./$(BUILD)/test_ps1_memory_view
	./$(BUILD)/test_map_buffer_gate
	./$(BUILD)/test_map_decode_checked
	./$(BUILD)/test_map_load_checked
	./$(BUILD)/test_private_map_bank
	python3 tests/test_restore_ps1_str.py
	python3 tests/test_inspect_cdxa.py
	python3 tests/test_extract_cdxa_payload.py
	python3 tests/test_drawotag_texture_fixtures.py
	python3 tests/test_inspect_psx_tim.py
	python3 tests/test_inspect_vh_map_texture_bank.py
	python3 tests/test_stage_vh_private_map_bank.py
	python3 tests/test_private_map_bank_bridge.py $(BUILD)/private_map_bank_bridge

# Host-only memory and undefined-behavior checks; requires GCC or Clang sanitizers.
test-sanitize: | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_game_rules.c -o $(BUILD)/test_game_rules_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_software_renderer.c -o $(BUILD)/test_software_renderer_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_rgb24_frame.c -o $(BUILD)/test_rgb24_frame_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_switch_presenter_layout.c -o $(BUILD)/test_switch_presenter_layout_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_ps1_memory_view.c -o $(BUILD)/test_ps1_memory_view_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map_buffer_gate.c -o $(BUILD)/test_map_buffer_gate_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map_decode_checked.c -o $(BUILD)/test_map_decode_checked_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map_load_checked.c -o $(BUILD)/test_map_load_checked_sanitize
	./$(BUILD)/test_game_rules_sanitize
	./$(BUILD)/test_software_renderer_sanitize
	./$(BUILD)/test_rgb24_frame_sanitize
	./$(BUILD)/test_switch_presenter_layout_sanitize
	./$(BUILD)/test_ps1_memory_view_sanitize
	./$(BUILD)/test_map_buffer_gate_sanitize
	./$(BUILD)/test_map_decode_checked_sanitize
	./$(BUILD)/test_map_load_checked_sanitize

verify-nro: $(BUILD)/$(TARGET).nro
	python3 tests/check_nro.py $<

sdl2-probe: $(BUILD)/$(SDL2_TARGET).nro
	python3 tests/check_nro.py $<

sdl2-gl-probe: $(BUILD)/$(SDL2_GL_TARGET).nro
	python3 tests/check_nro.py $<

sdl2-texture-probe: $(BUILD)/$(SDL2_TEXTURE_TARGET).nro
	python3 tests/check_nro.py $<

rgb24-texture-probe: $(BUILD)/$(RGB24_TEXTURE_TARGET).nro
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

$(BUILD)/test_rgb24_frame: tests/test_rgb24_frame.c source/rgb24_frame.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_switch_presenter_layout: tests/test_switch_presenter_layout.c source/switch_presenter_layout.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_ps1_memory_view: tests/test_ps1_memory_view.c source/ps1_memory_view.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_map_buffer_gate: tests/test_map_buffer_gate.c source/map_buffer_gate.h source/ps1_memory_view.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_map_decode_checked: tests/test_map_decode_checked.c source/map_decode_checked.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_map_load_checked: tests/test_map_load_checked.c source/map_load_checked.h source/map_buffer_gate.h source/map_decode_checked.h source/ps1_memory_view.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/private_map_bank_bridge: tests/private_map_bank_bridge.c source/vh_private_map_bank.c source/vh_private_map_bank.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 tests/private_map_bank_bridge.c source/vh_private_map_bank.c -o $@

$(BUILD)/test_private_map_bank: tests/test_private_map_bank.c source/vh_private_map_bank.c source/vh_private_map_bank.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 tests/test_private_map_bank.c source/vh_private_map_bank.c -o $@

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

$(BUILD)/$(RGB24_TEXTURE_TARGET).elf: probes/rgb24_texture_smoke.c source/rgb24_frame.h source/switch_presenter_layout.h source/switch_rgb24_presenter.h source/switch_rgb24_presenter.c | $(BUILD)
	$(CC) $(CFLAGS) $(LDFLAGS) $(shell $(SDL2_CONFIG) --cflags) probes/rgb24_texture_smoke.c source/switch_rgb24_presenter.c -o $@ $(shell $(SDL2_CONFIG) --libs) -lGLESv2 $(LDLIBS) -lm

$(BUILD)/$(RGB24_TEXTURE_TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts RGB24 Texture Probe" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(RGB24_TEXTURE_TARGET).nro: $(BUILD)/$(RGB24_TEXTURE_TARGET).elf $(BUILD)/$(RGB24_TEXTURE_TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(RGB24_TEXTURE_TARGET).nacp


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

# Standalone end-to-end observer NRO, using SDL2 to own the GLES2 context.
OBSERVER_TARGET := upstream-rgb24-observer-probe
OBSERVER_MODULES := source/switch_rgb24_presenter.c source/frame_conversion.c \
	source/switch_frame_bridge.c source/switch_completed_frame.c \
	source/switch_present_hook.c source/switch_upstream_observer.c

.PHONY: upstream-observer-probe
upstream-observer-probe: $(BUILD)/$(OBSERVER_TARGET).nro
	python3 tests/check_nro.py $<

$(BUILD)/$(OBSERVER_TARGET).elf: probes/upstream_rgb24_observer_smoke.c $(OBSERVER_MODULES) | $(BUILD)
	$(CC) $(CFLAGS) -Isource $(LDFLAGS) $(shell $(SDL2_CONFIG) --cflags) \
		probes/upstream_rgb24_observer_smoke.c $(OBSERVER_MODULES) -o $@ \
		$(shell $(SDL2_CONFIG) --libs) -lGLESv2 $(LDLIBS) -lm

$(BUILD)/$(OBSERVER_TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "VH RGB24 Observer Probe" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(OBSERVER_TARGET).nro: $(BUILD)/$(OBSERVER_TARGET).elf $(BUILD)/$(OBSERVER_TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(OBSERVER_TARGET).nacp

# Reusable SDL2/GLES2 observer backend lifecycle probe.
BACKEND_LIFECYCLE_TARGET := sdl2-observer-lifecycle-probe
.PHONY: observer-backend-lifecycle-probe
observer-backend-lifecycle-probe: $(BUILD)/$(BACKEND_LIFECYCLE_TARGET).nro
	python3 tests/check_nro.py $<

$(BUILD)/$(BACKEND_LIFECYCLE_TARGET).elf: probes/sdl2_observer_backend_lifecycle.c source/switch_sdl2_observer_backend.c source/switch_sdl2_observer_backend.h $(OBSERVER_MODULES) | $(BUILD)
	$(CC) $(CFLAGS) -Isource $(LDFLAGS) $(shell $(SDL2_CONFIG) --cflags) \
		probes/sdl2_observer_backend_lifecycle.c source/switch_sdl2_observer_backend.c $(OBSERVER_MODULES) -o $@ \
		$(shell $(SDL2_CONFIG) --libs) -lGLESv2 $(LDLIBS) -lm

$(BUILD)/$(BACKEND_LIFECYCLE_TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "VH Observer Lifecycle Probe" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(BACKEND_LIFECYCLE_TARGET).nro: $(BUILD)/$(BACKEND_LIFECYCLE_TARGET).elf $(BUILD)/$(BACKEND_LIFECYCLE_TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(BACKEND_LIFECYCLE_TARGET).nacp
 $(BUILD)/test_software_renderer $(BUILD)/test_rgb24_frame $(BUILD)/test_switch_presenter_layout $(BUILD)/test_ps1_memory_view $(BUILD)/test_map_buffer_gate $(BUILD)/test_map_decode_checked $(BUILD)/test_map_load_checked $(BUILD)/test_private_map_bank
	./$(BUILD)/test_game_rules
	./$(BUILD)/test_software_renderer
	./$(BUILD)/test_rgb24_frame
	./$(BUILD)/test_switch_presenter_layout
	./$(BUILD)/test_ps1_memory_view
	./$(BUILD)/test_map_buffer_gate
	./$(BUILD)/test_map_decode_checked
	./$(BUILD)/test_map_load_checked
	./$(BUILD)/test_private_map_bank
	python3 tests/test_restore_ps1_str.py
	python3 tests/test_inspect_cdxa.py
	python3 tests/test_extract_cdxa_payload.py
	python3 tests/test_drawotag_texture_fixtures.py
	python3 tests/test_inspect_psx_tim.py
	python3 tests/test_inspect_vh_map_texture_bank.py
	python3 tests/test_stage_vh_private_map_bank.py

# Host-only memory and undefined-behavior checks; requires GCC or Clang sanitizers.
test-sanitize: | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_game_rules.c -o $(BUILD)/test_game_rules_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_software_renderer.c -o $(BUILD)/test_software_renderer_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_rgb24_frame.c -o $(BUILD)/test_rgb24_frame_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_switch_presenter_layout.c -o $(BUILD)/test_switch_presenter_layout_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_ps1_memory_view.c -o $(BUILD)/test_ps1_memory_view_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map_buffer_gate.c -o $(BUILD)/test_map_buffer_gate_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map_decode_checked.c -o $(BUILD)/test_map_decode_checked_sanitize
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer tests/test_map_load_checked.c -o $(BUILD)/test_map_load_checked_sanitize
	./$(BUILD)/test_game_rules_sanitize
	./$(BUILD)/test_software_renderer_sanitize
	./$(BUILD)/test_rgb24_frame_sanitize
	./$(BUILD)/test_switch_presenter_layout_sanitize
	./$(BUILD)/test_ps1_memory_view_sanitize
	./$(BUILD)/test_map_buffer_gate_sanitize
	./$(BUILD)/test_map_decode_checked_sanitize
	./$(BUILD)/test_map_load_checked_sanitize

verify-nro: $(BUILD)/$(TARGET).nro
	python3 tests/check_nro.py $<

sdl2-probe: $(BUILD)/$(SDL2_TARGET).nro
	python3 tests/check_nro.py $<

sdl2-gl-probe: $(BUILD)/$(SDL2_GL_TARGET).nro
	python3 tests/check_nro.py $<

sdl2-texture-probe: $(BUILD)/$(SDL2_TEXTURE_TARGET).nro
	python3 tests/check_nro.py $<

rgb24-texture-probe: $(BUILD)/$(RGB24_TEXTURE_TARGET).nro
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

$(BUILD)/test_rgb24_frame: tests/test_rgb24_frame.c source/rgb24_frame.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_switch_presenter_layout: tests/test_switch_presenter_layout.c source/switch_presenter_layout.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_ps1_memory_view: tests/test_ps1_memory_view.c source/ps1_memory_view.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_map_buffer_gate: tests/test_map_buffer_gate.c source/map_buffer_gate.h source/ps1_memory_view.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_map_decode_checked: tests/test_map_decode_checked.c source/map_decode_checked.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_map_load_checked: tests/test_map_load_checked.c source/map_load_checked.h source/map_buffer_gate.h source/map_decode_checked.h source/ps1_memory_view.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/test_private_map_bank: tests/test_private_map_bank.c source/vh_private_map_bank.c source/vh_private_map_bank.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 tests/test_private_map_bank.c source/vh_private_map_bank.c -o $@

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

$(BUILD)/$(RGB24_TEXTURE_TARGET).elf: probes/rgb24_texture_smoke.c source/rgb24_frame.h source/switch_presenter_layout.h source/switch_rgb24_presenter.h source/switch_rgb24_presenter.c | $(BUILD)
	$(CC) $(CFLAGS) $(LDFLAGS) $(shell $(SDL2_CONFIG) --cflags) probes/rgb24_texture_smoke.c source/switch_rgb24_presenter.c -o $@ $(shell $(SDL2_CONFIG) --libs) -lGLESv2 $(LDLIBS) -lm

$(BUILD)/$(RGB24_TEXTURE_TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts RGB24 Texture Probe" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(RGB24_TEXTURE_TARGET).nro: $(BUILD)/$(RGB24_TEXTURE_TARGET).elf $(BUILD)/$(RGB24_TEXTURE_TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(RGB24_TEXTURE_TARGET).nacp


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

# Standalone end-to-end observer NRO, using SDL2 to own the GLES2 context.
OBSERVER_TARGET := upstream-rgb24-observer-probe
OBSERVER_MODULES := source/switch_rgb24_presenter.c source/frame_conversion.c \
	source/switch_frame_bridge.c source/switch_completed_frame.c \
	source/switch_present_hook.c source/switch_upstream_observer.c

.PHONY: upstream-observer-probe
upstream-observer-probe: $(BUILD)/$(OBSERVER_TARGET).nro
	python3 tests/check_nro.py $<

$(BUILD)/$(OBSERVER_TARGET).elf: probes/upstream_rgb24_observer_smoke.c $(OBSERVER_MODULES) | $(BUILD)
	$(CC) $(CFLAGS) -Isource $(LDFLAGS) $(shell $(SDL2_CONFIG) --cflags) \
		probes/upstream_rgb24_observer_smoke.c $(OBSERVER_MODULES) -o $@ \
		$(shell $(SDL2_CONFIG) --libs) -lGLESv2 $(LDLIBS) -lm

$(BUILD)/$(OBSERVER_TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "VH RGB24 Observer Probe" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(OBSERVER_TARGET).nro: $(BUILD)/$(OBSERVER_TARGET).elf $(BUILD)/$(OBSERVER_TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(OBSERVER_TARGET).nacp

# Reusable SDL2/GLES2 observer backend lifecycle probe.
BACKEND_LIFECYCLE_TARGET := sdl2-observer-lifecycle-probe
.PHONY: observer-backend-lifecycle-probe
observer-backend-lifecycle-probe: $(BUILD)/$(BACKEND_LIFECYCLE_TARGET).nro
	python3 tests/check_nro.py $<

$(BUILD)/$(BACKEND_LIFECYCLE_TARGET).elf: probes/sdl2_observer_backend_lifecycle.c source/switch_sdl2_observer_backend.c source/switch_sdl2_observer_backend.h $(OBSERVER_MODULES) | $(BUILD)
	$(CC) $(CFLAGS) -Isource $(LDFLAGS) $(shell $(SDL2_CONFIG) --cflags) \
		probes/sdl2_observer_backend_lifecycle.c source/switch_sdl2_observer_backend.c $(OBSERVER_MODULES) -o $@ \
		$(shell $(SDL2_CONFIG) --libs) -lGLESv2 $(LDLIBS) -lm

$(BUILD)/$(BACKEND_LIFECYCLE_TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "VH Observer Lifecycle Probe" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(BACKEND_LIFECYCLE_TARGET).nro: $(BUILD)/$(BACKEND_LIFECYCLE_TARGET).elf $(BUILD)/$(BACKEND_LIFECYCLE_TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(BACKEND_LIFECYCLE_TARGET).nacp
