# Minimal libnx homebrew smoke test; no game code or proprietary assets.
# Based on the standard devkitPro Switch application template.

.SUFFIXES:

ifeq ($(strip $(DEVKITPRO)),)
$(error "Please set DEVKITPRO in your environment. export DEVKITPRO=<path to>/devkitpro")
endif

TOPDIR ?= $(CURDIR)
include $(DEVKITPRO)/libnx/switch_rules

TARGET      := switch-smoke-test
BUILD       := build
SOURCES     := source
DATA        :=
INCLUDES    :=

APP_TITLE   := VH Switch Smoke Test
APP_AUTHOR  := Vandal Hearts Switch Remaster contributors
APP_VERSION := 0.1.0
