#!/usr/bin/env bash
# Diagnostic only: inspect a local devkitPro/libnx installation; does not build the game.
set -u

missing=0

report_command() {
    local name="$1"
    if command -v "$name" >/dev/null 2>&1; then
        printf 'OK      %-24s %s\n' "$name" "$(command -v "$name")"
    else
        printf 'MISSING %-24s not found on PATH\n' "$name"
        missing=$((missing + 1))
    fi
}

report_dir() {
    local name="$1" path="$2"
    if [[ -n "$path" && -d "$path" ]]; then
        printf 'OK      %-24s %s\n' "$name" "$path"
    else
        printf 'MISSING %-24s %s\n' "$name" "${path:-<unset>}"
        missing=$((missing + 1))
    fi
}

report_file() {
    local name="$1" path="$2"
    if [[ -n "$path" && -f "$path" ]]; then
        printf 'OK      %-24s %s\n' "$name" "$path"
    else
        printf 'MISSING %-24s %s\n' "$name" "${path:-<unset>}"
        missing=$((missing + 1))
    fi
}

printf 'Switch homebrew toolchain diagnostic (no build is performed)\n'
printf 'Host: %s\n' "$(uname -srm 2>/dev/null || printf unknown)"
printf 'DEVKITPRO=%s\n' "${DEVKITPRO:-<unset>}"
printf 'DEVKITA64=%s\n\n' "${DEVKITA64:-<unset>}"

report_dir 'DEVKITPRO directory' "${DEVKITPRO:-}"
report_dir 'DEVKITA64 directory' "${DEVKITA64:-}"
report_command 'aarch64-none-elf-gcc'
report_command 'aarch64-none-elf-g++'
report_command 'elf2nro'
report_command 'nacptool'

if [[ -n "${DEVKITPRO:-}" ]]; then
    report_file 'libnx switch.h' "$DEVKITPRO/libnx/include/switch.h"
else
    printf 'MISSING %-24s DEVKITPRO is unset; cannot check header path\n' 'libnx switch.h'
    missing=$((missing + 1))
fi

if command -v aarch64-none-elf-gcc >/dev/null 2>&1; then
    printf '\nCompiler version:\n'
    aarch64-none-elf-gcc --version | head -n 1
fi

if command -v dkp-pacman >/dev/null 2>&1; then
    printf '\nRelevant installed packages (if package metadata is available):\n'
    dkp-pacman -Q devkitA64 libnx switch-tools 2>&1 || true
elif command -v pacman >/dev/null 2>&1; then
    printf '\nRelevant installed packages (if package metadata is available):\n'
    pacman -Q devkitA64 libnx switch-tools 2>&1 || true
fi

printf '\n'
if (( missing == 0 )); then
    printf 'DIAGNOSTIC PASS: required commands and paths were found. This does not prove an NRO builds or runs.\n'
    exit 0
fi
printf 'DIAGNOSTIC FAIL: %d required check(s) missing. Install/configure devkitPro and libnx, then rerun.\n' "$missing"
printf 'This diagnostic is not a build attempt and says nothing about Switch runtime compatibility.\n'
exit 1
