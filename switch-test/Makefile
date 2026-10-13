# Minimal libnx homebrew smoke test; no game code or proprietary assets.
# Requires a working devkitPro Switch toolchain with libnx installed.

.SUFFIXES:
.PHONY: all clean

ifeq ($(strip $(DEVKITPRO)),)
$(error "DEVKITPRO is not set. Install devkitPro and configure its environment first.")
endif

TARGET      := switch-smoke-test
BUILD       := build
SOURCES     := source
DATA        :=
INCLUDES    :=

APP_TITLE   := VH Switch Smoke Test
APP_AUTHOR  := Vandal Hearts Switch Remaster contributors
APP_VERSION := 0.1.0

include $(DEVKITPRO)/libnx/switch_rules
