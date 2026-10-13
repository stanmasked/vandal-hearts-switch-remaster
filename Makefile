# Minimal devkitPro/libnx homebrew prototype.
# This does not port the original Vandal Hearts game yet.

TARGET      := vandal-hearts-prototype
BUILD       := build
SOURCES     := source
DATA        :=
INCLUDES    :=
ROMFS       :=

APP_TITLE   := Vandal Hearts Switch Prototype
APP_AUTHOR  := Vandal Hearts Switch Remaster contributors
APP_VERSION := 0.1.0

include $(DEVKITPRO)/libnx/switch_rules
