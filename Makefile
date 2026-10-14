# Minimal devkitPro/libnx homebrew prototype.
# This does not port the original Vandal Hearts game yet.

DEVKITPRO ?= /opt/devkitpro
DEVKITA64 ?= $(DEVKITPRO)/devkitA64
TARGET     := vandal-hearts-prototype
SDL2_TARGET := sdl2-switch-probe
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

.PHONY: all clean test verify-nro sdl2-probe
all: $(BUILD)/$(TARGET).nro

test: $(BUILD)/test_game_rules
	./$(BUILD)/test_game_rules

verify-nro: $(BUILD)/$(TARGET).nro
	python3 tests/check_nro.py $<

sdl2-probe: $(BUILD)/$(SDL2_TARGET).nro
	python3 tests/check_nro.py $<

$(BUILD):
	mkdir -p $@

$(BUILD)/test_game_rules: tests/test_game_rules.c source/game_rules.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 $< -o $@

$(BUILD)/$(TARGET).elf: $(SOURCES)/main.c $(SOURCES)/game_rules.h | $(BUILD)
	$(CC) $(CFLAGS) $(LDFLAGS) $< -o $@ $(LDLIBS)

$(BUILD)/$(TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "$(APP_TITLE)" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(TARGET).nro: $(BUILD)/$(TARGET).elf $(BUILD)/$(TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(TARGET).nacp

$(BUILD)/$(SDL2_TARGET).elf: probes/sdl2_smoke.c source/game_rules.h | $(BUILD)
	$(CC) $(CFLAGS) -Isource $(LDFLAGS) $(shell $(SDL2_CONFIG) --cflags) $< -o $@ $(shell $(SDL2_CONFIG) --libs) $(LDLIBS)

$(BUILD)/$(SDL2_TARGET).nacp: | $(BUILD)
	$(NACPTOOL) --create "Vandal Hearts SDL2 Probe" "$(APP_AUTHOR)" "$(APP_VERSION)" $@

$(BUILD)/$(SDL2_TARGET).nro: $(BUILD)/$(SDL2_TARGET).elf $(BUILD)/$(SDL2_TARGET).nacp
	$(ELF2NRO) $< $@ --nacp=$(BUILD)/$(SDL2_TARGET).nacp

clean:
	rm -rf $(BUILD)
