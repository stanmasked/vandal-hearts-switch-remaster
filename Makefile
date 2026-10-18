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
# Research variant builds use separate BUILD directories. Default remains
# phase0 so existing NRO provenance and slow-call audit are unmodified.
AUDOUT_PROBE_PHASE ?= 0
CFLAGS += -DVH_AUDOUT_PROBE_PHASE=$(AUDOUT_PROBE_PHASE)
LDFLAGS  := -specs=$(DEVKITPRO)/libnx/switch.specs -Wl,--gc-sections -pie
LDLIBS   := -L$(DEVKITPRO)/libnx/lib -lnx

.PHONY: all clean test test-audio-stream test-sanitize verify-nro sdl2-probe sdl2-gl-probe sdl2-texture-probe sdl2-audio-probe audout-audio-probe openal-probe
all: $(BUILD)/$(TARGET).nro

test: $(BUILD)/test_game_rules $(BUILD)/test_software_renderer $(BUILD)/test_vh_audio_stream $(BUILD)/test_vh_native_spu $(BUILD)/test_vh_native_seq $(BUILD)/test_vh_native_vab $(BUILD)/test_vh_audio_assets $(BUILD)/test_vh_audio_resample $(BUILD)/test_vh_audio_output_ramp $(BUILD)/test_vh_audio_diagnostics $(BUILD)/test_vh_audio_diag_journal $(BUILD)/test_vh_audio_diag_export $(BUILD)/switch_audio_export_session $(BUILD)/test_vh_audio_output_edges $(BUILD)/test_vh_audio_buffer_lease $(BUILD)/test_vh_audout_queue_telemetry $(BUILD)/test_vh_audout_queue_export $(BUILD)/test_vh_audio_output_recovery $(BUILD)/test_vh_spu_reverb $(BUILD)/test_vh_native_audio_soak $(BUILD)/test_vh_music_scene $(BUILD)/test_vh_music_scene_soak $(BUILD)/test_vh_audio_scene_trace $(BUILD)/test_vh_audio_scene_trace_export $(BUILD)/test_vh_audio_exit_timeline $(BUILD)/test_vh_audio_exit_output_witness $(BUILD)/test_vh_audio_exit_worker_stop_witness $(BUILD)/test_vh_audio_scene_optical $(BUILD)/test_vh_game_music_mailbox $(BUILD)/test_vh_music_focus_resume $(BUILD)/test_vh_music_lifecycle_soak $(BUILD)/test_vh_game_music_banks $(BUILD)/vh_music_bank_audit
	./$(BUILD)/test_game_rules
	./$(BUILD)/test_software_renderer
	./$(BUILD)/test_vh_audio_stream
	./$(BUILD)/test_vh_native_spu
	./$(BUILD)/test_vh_native_seq
	./$(BUILD)/test_vh_native_vab
	./$(BUILD)/test_vh_audio_assets
	./$(BUILD)/test_vh_audio_resample
	./$(BUILD)/test_vh_audio_output_ramp
	./$(BUILD)/test_vh_audio_diagnostics
	./$(BUILD)/test_vh_audio_diag_journal
	./$(BUILD)/test_vh_audio_diag_export
	./$(BUILD)/test_vh_audio_output_edges
	./$(BUILD)/test_vh_audio_buffer_lease
	./$(BUILD)/test_vh_audout_queue_telemetry
	./$(BUILD)/test_vh_audout_queue_export
	./$(BUILD)/test_vh_audio_output_recovery
	./$(BUILD)/test_vh_spu_reverb
	./$(BUILD)/test_vh_native_audio_soak
	./$(BUILD)/test_vh_music_scene
	./$(BUILD)/test_vh_music_scene_soak
	./$(BUILD)/test_vh_audio_scene_trace
	./$(BUILD)/test_vh_audio_scene_trace_export
	./$(BUILD)/test_vh_audio_exit_timeline
	./$(BUILD)/test_vh_audio_exit_output_witness
	./$(BUILD)/test_vh_audio_exit_worker_stop_witness
	./$(BUILD)/test_vh_audio_scene_optical
	./$(BUILD)/test_vh_game_music_mailbox
	./$(BUILD)/test_vh_music_focus_resume
	./$(BUILD)/test_vh_music_lifecycle_soak
	./$(BUILD)/test_vh_game_music_banks
	python3 tests/test_audit_switch_guest_scene_trace.py
	python3 tests/test_audit_nexium_guest_exit_timeline.py
	python3 tests/test_audit_nexium_guest_last_buffer_return.py
	python3 tests/test_audit_nexium_guest_worker_stop_observed.py
	python3 tests/test_analyze_switch_audio_log.py
	python3 tests/test_verify_switch_audio_bundle.py
	python3 tests/test_report_switch_audio_hardware.py
	python3 tests/test_verify_switch_audio_build_provenance.py
	python3 tests/test_switch_audio_ci_build_receipt.py
	python3 tests/test_verify_switch_audio_launch_gate.py
	python3 tests/test_verify_switch_audio_sd_reinsert.py
	python3 tests/test_link_switch_audio_device_evidence.py
	python3 tests/test_capture_switch_audio_sd_csv.py
	python3 tests/test_verify_switch_audio_h05_csv_persistence.py
	python3 tests/test_verify_switch_audio_h05_capture_binding.py
	python3 tests/test_verify_switch_audio_h05_operator_binding.py
	python3 tests/test_seal_switch_audio_h05_review.py
	python3 tests/test_classify_switch_portlib_install.py
	python3 tests/test_verify_switch_integrated_nro_preflight.py
	python3 tests/test_verify_switch_audio_live_preflight.py
	python3 tests/test_verify_switch_audio_sd_transfer.py
	python3 tests/test_assess_switch_audio_first_run.py
	python3 tests/test_report_switch_audio_acceptance_matrix.py
	python3 tests/test_audit_switch_audio_handoff.py
	python3 tests/test_archive_switch_audio_handoff.py
	python3 tests/test_compare_switch_audio_archive_reports.py
	python3 tests/test_replay_switch_audio_evidence_report.py
	python3 tests/test_chain_switch_audio_receipts.py
	python3 tests/test_checkpoint_switch_audio_receipt_chain.py
	python3 tests/test_verify_switch_audio_checkpoint_continuity.py
	python3 tests/test_compare_switch_audio_sessions.py
	python3 tests/test_switch_audio_telemetry_e2e.py
	python3 tests/test_switch_audio_long_cohort.py
	python3 tests/test_switch_audio_export_restart_e2e.py
	python3 tests/test_vh_music_bank_audit_cli.py
	python3 tests/test_audit_pcport_vab_aliases.py
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

test-audio-stream: $(BUILD)/test_vh_audio_stream $(BUILD)/test_vh_native_spu $(BUILD)/test_vh_native_seq $(BUILD)/test_vh_native_vab $(BUILD)/test_vh_audio_assets $(BUILD)/test_vh_audio_resample $(BUILD)/test_vh_audio_output_ramp $(BUILD)/test_vh_audio_diagnostics $(BUILD)/test_vh_audio_diag_journal $(BUILD)/test_vh_audio_diag_export $(BUILD)/switch_audio_export_session $(BUILD)/test_vh_audio_output_edges $(BUILD)/test_vh_audio_buffer_lease $(BUILD)/test_vh_audout_queue_telemetry $(BUILD)/test_vh_audout_queue_export $(BUILD)/test_vh_audio_output_recovery $(BUILD)/test_vh_spu_reverb $(BUILD)/test_vh_native_audio_soak $(BUILD)/test_vh_music_scene $(BUILD)/test_vh_music_scene_soak $(BUILD)/test_vh_audio_scene_trace $(BUILD)/test_vh_audio_scene_trace_export $(BUILD)/test_vh_audio_exit_timeline $(BUILD)/test_vh_audio_exit_output_witness $(BUILD)/test_vh_audio_exit_worker_stop_witness $(BUILD)/test_vh_audio_scene_optical $(BUILD)/test_vh_game_music_mailbox $(BUILD)/test_vh_music_focus_resume $(BUILD)/test_vh_music_lifecycle_soak $(BUILD)/test_vh_game_music_banks $(BUILD)/vh_music_bank_audit
	./$(BUILD)/test_vh_audio_stream
	./$(BUILD)/test_vh_native_spu
	./$(BUILD)/test_vh_native_seq
	./$(BUILD)/test_vh_native_vab
	./$(BUILD)/test_vh_audio_assets
	./$(BUILD)/test_vh_audio_resample
	./$(BUILD)/test_vh_audio_output_ramp
	./$(BUILD)/test_vh_audio_diagnostics
	./$(BUILD)/test_vh_audio_diag_journal
	./$(BUILD)/test_vh_audio_diag_export
	./$(BUILD)/test_vh_audio_output_edges
	./$(BUILD)/test_vh_audio_buffer_lease
	./$(BUILD)/test_vh_audout_queue_telemetry
	./$(BUILD)/test_vh_audout_queue_export
	./$(BUILD)/test_vh_audio_output_recovery
	./$(BUILD)/test_vh_spu_reverb
	./$(BUILD)/test_vh_native_audio_soak
	./$(BUILD)/test_vh_music_scene
	./$(BUILD)/test_vh_music_scene_soak
	./$(BUILD)/test_vh_audio_scene_trace
	./$(BUILD)/test_vh_audio_scene_trace_export
	./$(BUILD)/test_vh_audio_exit_timeline
	./$(BUILD)/test_vh_audio_exit_output_witness
	./$(BUILD)/test_vh_audio_exit_worker_stop_witness
	./$(BUILD)/test_vh_audio_scene_optical
	./$(BUILD)/test_vh_game_music_mailbox
	./$(BUILD)/test_vh_music_focus_resume
	./$(BUILD)/test_vh_music_lifecycle_soak
	./$(BUILD)/test_vh_game_music_banks
	python3 tests/test_audit_switch_guest_scene_trace.py
	python3 tests/test_audit_nexium_guest_exit_timeline.py
	python3 tests/test_audit_nexium_guest_last_buffer_return.py
	python3 tests/test_audit_nexium_guest_worker_stop_observed.py
	python3 tests/test_analyze_switch_audio_log.py
	python3 tests/test_verify_switch_audio_bundle.py
	python3 tests/test_report_switch_audio_hardware.py
	python3 tests/test_verify_switch_audio_build_provenance.py
	python3 tests/test_switch_audio_ci_build_receipt.py
	python3 tests/test_verify_switch_audio_launch_gate.py
	python3 tests/test_verify_switch_audio_sd_reinsert.py
	python3 tests/test_link_switch_audio_device_evidence.py
	python3 tests/test_capture_switch_audio_sd_csv.py
	python3 tests/test_verify_switch_audio_h05_csv_persistence.py
	python3 tests/test_verify_switch_audio_h05_capture_binding.py
	python3 tests/test_verify_switch_audio_h05_operator_binding.py
	python3 tests/test_seal_switch_audio_h05_review.py
	python3 tests/test_classify_switch_portlib_install.py
	python3 tests/test_verify_switch_integrated_nro_preflight.py
	python3 tests/test_verify_switch_audio_live_preflight.py
	python3 tests/test_verify_switch_audio_sd_transfer.py
	python3 tests/test_assess_switch_audio_first_run.py
	python3 tests/test_report_switch_audio_acceptance_matrix.py
	python3 tests/test_audit_switch_audio_handoff.py
	python3 tests/test_archive_switch_audio_handoff.py
	python3 tests/test_compare_switch_audio_archive_reports.py
	python3 tests/test_replay_switch_audio_evidence_report.py
	python3 tests/test_chain_switch_audio_receipts.py
	python3 tests/test_checkpoint_switch_audio_receipt_chain.py
	python3 tests/test_verify_switch_audio_checkpoint_continuity.py
	python3 tests/test_compare_switch_audio_sessions.py
	python3 tests/test_switch_audio_telemetry_e2e.py
	python3 tests/test_switch_audio_long_cohort.py
	python3 tests/test_switch_audio_export_restart_e2e.py
	python3 tests/test_vh_music_bank_audit_cli.py
	python3 tests/test_audit_pcport_vab_aliases.py
	python3 tests/test_native_spu_adpcm.py
	python3 tests/test_native_spu_gaussian.py
	python3 tests/test_native_vab_python_reference.py
	python3 tests/test_native_spu_reverb_reference.py

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

$(BUILD)/test_vh_game_music_banks: tests/test_vh_game_music_banks.c source/vh_game_music_banks.c source/vh_game_music_banks.h source/vh_audio_assets.c source/vh_audio_assets.h source/vh_native_vab.c source/vh_native_vab.h source/vh_music_scene.c source/vh_music_scene.h source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_native_spu.h source/vh_spu_reverb.c source/vh_spu_reverb.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_spu_adpcm.c source/vh_spu_adpcm.h source/vh_audio_stream.c source/vh_audio_stream.h source/vh_audio_resample.c source/vh_audio_resample.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_game_music_banks.c source/vh_game_music_banks.c source/vh_audio_assets.c source/vh_native_vab.c source/vh_music_scene.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_spu_adpcm.c source/vh_audio_stream.c source/vh_audio_resample.c -lm -o $@

$(BUILD)/vh_music_bank_audit: tools/vh_music_bank_audit.c source/vh_game_music_banks.c source/vh_game_music_banks.h source/vh_audio_assets.c source/vh_audio_assets.h source/vh_native_vab.c source/vh_native_vab.h source/vh_music_scene.c source/vh_music_scene.h source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_native_spu.h source/vh_spu_reverb.c source/vh_spu_reverb.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_spu_adpcm.c source/vh_spu_adpcm.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tools/vh_music_bank_audit.c source/vh_game_music_banks.c source/vh_audio_assets.c source/vh_native_vab.c source/vh_music_scene.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_spu_adpcm.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_music_focus_resume: tests/test_vh_music_focus_resume.c source/vh_game_music_mailbox.c source/vh_game_music_mailbox.h source/vh_music_scene.c source/vh_music_scene.h source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_native_spu.h source/vh_spu_reverb.c source/vh_spu_reverb.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_audio_resample.c source/vh_audio_resample.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_music_focus_resume.c source/vh_game_music_mailbox.c source/vh_music_scene.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_audio_resample.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_music_lifecycle_soak: tests/test_vh_music_lifecycle_soak.c source/vh_audio_diag_journal.c source/vh_audio_diag_journal.h source/vh_audio_output_recovery.c source/vh_audio_output_recovery.h source/vh_audio_output_ramp.c source/vh_audio_output_ramp.h source/vh_audio_output_edges.c source/vh_audio_output_edges.h source/vh_game_music_mailbox.c source/vh_music_scene.c source/vh_audio_resample.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_audio_stream.c | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_music_lifecycle_soak.c source/vh_audio_diag_journal.c source/vh_audio_output_recovery.c source/vh_audio_output_ramp.c source/vh_audio_output_edges.c source/vh_game_music_mailbox.c source/vh_music_scene.c source/vh_audio_resample.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_audio_scene_optical: tests/test_vh_audio_scene_optical.c source/vh_audio_scene_optical.c source/vh_audio_scene_optical.h source/vh_audio_scene_trace.c source/vh_audio_scene_trace.h source/software_renderer.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_scene_optical.c source/vh_audio_scene_optical.c source/vh_audio_scene_trace.c -o $@

$(BUILD)/test_vh_audio_scene_trace_export: tests/test_vh_audio_scene_trace_export.c source/vh_audio_scene_trace_export.c source/vh_audio_scene_trace_export.h source/vh_audio_scene_trace.c source/vh_audio_scene_trace.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_scene_trace_export.c source/vh_audio_scene_trace_export.c source/vh_audio_scene_trace.c -o $@

$(BUILD)/test_vh_audio_exit_worker_stop_witness: tests/test_vh_audio_exit_worker_stop_witness.c source/vh_audio_exit_worker_stop_witness.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_exit_worker_stop_witness.c -o $@

$(BUILD)/test_vh_audio_exit_output_witness: tests/test_vh_audio_exit_output_witness.c source/vh_audio_exit_output_witness.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_exit_output_witness.c -o $@

$(BUILD)/test_vh_audio_exit_timeline: tests/test_vh_audio_exit_timeline.c source/vh_audio_exit_timeline.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_exit_timeline.c -o $@

$(BUILD)/test_vh_audio_scene_trace: tests/test_vh_audio_scene_trace.c source/vh_audio_scene_trace.c source/vh_audio_scene_trace.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_scene_trace.c source/vh_audio_scene_trace.c -pthread -o $@

$(BUILD)/test_vh_game_music_mailbox: tests/test_vh_game_music_mailbox.c source/vh_game_music_mailbox.c source/vh_game_music_mailbox.h source/game_state.h source/platform_input.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_game_music_mailbox.c source/vh_game_music_mailbox.c -pthread -o $@

$(BUILD)/test_vh_music_scene_soak: tests/test_vh_music_scene_soak.c source/vh_music_scene.c source/vh_music_scene.h source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_native_spu.h source/vh_spu_reverb.c source/vh_spu_reverb.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_audio_resample.c source/vh_audio_resample.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_music_scene_soak.c source/vh_music_scene.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_audio_resample.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_music_scene: tests/test_vh_music_scene.c source/vh_music_scene.c source/vh_music_scene.h source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_native_spu.h source/vh_spu_reverb.c source/vh_spu_reverb.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_music_scene.c source/vh_music_scene.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_native_audio_soak: tests/test_vh_native_audio_soak.c source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_native_spu.h source/vh_spu_reverb.c source/vh_spu_reverb.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_audio_resample.c source/vh_audio_resample.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_native_audio_soak.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_audio_resample.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_spu_reverb: tests/test_vh_spu_reverb.c source/vh_spu_reverb.c source/vh_spu_reverb.h source/vh_native_spu.c source/vh_native_spu.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_spu_reverb.c source/vh_spu_reverb.c source/vh_native_spu.c source/vh_spu_gaussian.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_native_spu: tests/test_vh_native_spu.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_native_spu.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_spu_adpcm.c source/vh_spu_adpcm.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_native_spu.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_spu_adpcm.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_native_vab: tests/test_vh_native_vab.c source/vh_native_vab.c source/vh_native_vab.h source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_spu_reverb.c source/vh_native_spu.h source/vh_spu_adpcm.c source/vh_spu_adpcm.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_native_vab.c source/vh_native_vab.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_adpcm.c source/vh_spu_gaussian.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/switch_audio_export_session: tests/switch_audio_export_session.c source/vh_audio_diag_export.c source/vh_audio_diag_export.h source/vh_audio_diag_journal.c source/vh_audio_diag_journal.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/switch_audio_export_session.c source/vh_audio_diag_export.c source/vh_audio_diag_journal.c -o $@

$(BUILD)/test_vh_audio_diag_export: tests/test_vh_audio_diag_export.c source/vh_audio_diag_export.c source/vh_audio_diag_export.h source/vh_audio_diag_journal.c source/vh_audio_diag_journal.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_diag_export.c source/vh_audio_diag_export.c source/vh_audio_diag_journal.c -o $@

$(BUILD)/test_vh_audio_diag_journal: tests/test_vh_audio_diag_journal.c source/vh_audio_diag_journal.c source/vh_audio_diag_journal.h source/vh_audio_diagnostics.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_diag_journal.c source/vh_audio_diag_journal.c -o $@

$(BUILD)/test_vh_audio_diagnostics: tests/test_vh_audio_diagnostics.c source/vh_audio_diagnostics.c source/vh_audio_diagnostics.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_diagnostics.c source/vh_audio_diagnostics.c -o $@

$(BUILD)/test_vh_audio_output_edges: tests/test_vh_audio_output_edges.c source/vh_audio_output_edges.c source/vh_audio_output_edges.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_output_edges.c source/vh_audio_output_edges.c -o $@

$(BUILD)/test_vh_audio_output_ramp: tests/test_vh_audio_output_ramp.c source/vh_audio_output_ramp.c source/vh_audio_output_ramp.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_output_ramp.c source/vh_audio_output_ramp.c -o $@

$(BUILD)/test_vh_audio_buffer_lease: tests/test_vh_audio_buffer_lease.c source/vh_audio_buffer_lease.c source/vh_audio_buffer_lease.h source/vh_audio_output_recovery.c source/vh_audio_output_recovery.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_buffer_lease.c source/vh_audio_buffer_lease.c source/vh_audio_output_recovery.c -o $@

$(BUILD)/test_vh_audout_queue_telemetry: tests/test_vh_audout_queue_telemetry.c source/vh_audout_queue_telemetry.c source/vh_audout_queue_telemetry.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audout_queue_telemetry.c source/vh_audout_queue_telemetry.c -o $@

$(BUILD)/test_vh_audout_queue_export: tests/test_vh_audout_queue_export.c source/vh_audout_queue_export.c source/vh_audout_queue_export.h source/vh_audout_queue_telemetry.c source/vh_audout_queue_telemetry.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audout_queue_export.c source/vh_audout_queue_export.c source/vh_audout_queue_telemetry.c -o $@

$(BUILD)/test_vh_audio_output_recovery: tests/test_vh_audio_output_recovery.c source/vh_audio_output_recovery.c source/vh_audio_output_recovery.h source/vh_audio_output_ramp.c source/vh_audio_output_ramp.h source/vh_music_scene.c source/vh_music_scene.h source/vh_audio_resample.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_audio_stream.c | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_output_recovery.c source/vh_audio_output_recovery.c source/vh_audio_output_ramp.c source/vh_music_scene.c source/vh_audio_resample.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_audio_resample: tests/test_vh_audio_resample.c source/vh_audio_resample.c source/vh_audio_resample.h source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_resample.c source/vh_audio_resample.c -o $@

$(BUILD)/test_vh_audio_assets: tests/test_vh_audio_assets.c source/vh_audio_assets.c source/vh_audio_assets.h source/vh_native_vab.c source/vh_native_vab.h source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_spu_reverb.c source/vh_native_spu.h source/vh_spu_adpcm.c source/vh_spu_adpcm.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_audio_assets.c source/vh_audio_assets.c source/vh_native_vab.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_adpcm.c source/vh_spu_gaussian.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/test_vh_native_seq: tests/test_vh_native_seq.c source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_spu_reverb.c source/vh_native_spu.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -O2 -Isource tests/test_vh_native_seq.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_gaussian.c source/vh_audio_stream.c -lm -o $@

$(BUILD)/$(TARGET).elf: $(SOURCES)/main.c $(SOURCES)/game_rules.h $(SOURCES)/game_state.h $(SOURCES)/platform_input.h $(SOURCES)/software_renderer.h $(SOURCES)/game_renderer.h $(SOURCES)/vh_switch_game_audio.c $(SOURCES)/vh_switch_game_audio.h $(SOURCES)/vh_audio_scene_trace.c $(SOURCES)/vh_audio_scene_trace.h $(SOURCES)/vh_audio_scene_trace_export.c $(SOURCES)/vh_audio_scene_trace_export.h $(SOURCES)/vh_audio_scene_optical.c $(SOURCES)/vh_audio_scene_optical.h $(SOURCES)/vh_game_music_banks.c $(SOURCES)/vh_game_music_banks.h $(SOURCES)/vh_audio_assets.c $(SOURCES)/vh_audio_assets.h $(SOURCES)/vh_native_vab.c $(SOURCES)/vh_native_vab.h $(SOURCES)/vh_spu_adpcm.c $(SOURCES)/vh_spu_adpcm.h $(SOURCES)/vh_game_music_mailbox.c $(SOURCES)/vh_game_music_mailbox.h $(SOURCES)/vh_music_scene.c $(SOURCES)/vh_music_scene.h $(SOURCES)/vh_native_seq.c $(SOURCES)/vh_native_seq.h $(SOURCES)/vh_native_spu.c $(SOURCES)/vh_native_spu.h $(SOURCES)/vh_spu_reverb.c $(SOURCES)/vh_spu_reverb.h $(SOURCES)/vh_spu_gaussian.c $(SOURCES)/vh_spu_gaussian.h $(SOURCES)/vh_audio_resample.c $(SOURCES)/vh_audio_resample.h $(SOURCES)/vh_audio_output_recovery.c $(SOURCES)/vh_audio_output_recovery.h $(SOURCES)/vh_audio_buffer_lease.c $(SOURCES)/vh_audio_buffer_lease.h $(SOURCES)/vh_audout_queue_telemetry.c $(SOURCES)/vh_audout_queue_telemetry.h $(SOURCES)/vh_audout_queue_export.c $(SOURCES)/vh_audout_queue_export.h $(SOURCES)/vh_audio_output_ramp.c $(SOURCES)/vh_audio_output_ramp.h $(SOURCES)/vh_audio_output_edges.c $(SOURCES)/vh_audio_output_edges.h $(SOURCES)/vh_audio_diagnostics.c $(SOURCES)/vh_audio_diagnostics.h $(SOURCES)/vh_audio_diag_journal.c $(SOURCES)/vh_audio_diag_journal.h $(SOURCES)/vh_audio_diag_export.c $(SOURCES)/vh_audio_diag_export.h $(SOURCES)/vh_audio_stream.c $(SOURCES)/vh_audio_stream.h | $(BUILD)
	$(CC) $(CFLAGS) -Isource $(LDFLAGS) $(SOURCES)/main.c $(SOURCES)/vh_switch_game_audio.c $(SOURCES)/vh_audio_scene_trace.c $(SOURCES)/vh_audio_scene_trace_export.c $(SOURCES)/vh_audio_scene_optical.c $(SOURCES)/vh_game_music_banks.c $(SOURCES)/vh_audio_assets.c $(SOURCES)/vh_native_vab.c $(SOURCES)/vh_spu_adpcm.c $(SOURCES)/vh_game_music_mailbox.c $(SOURCES)/vh_music_scene.c $(SOURCES)/vh_native_seq.c $(SOURCES)/vh_native_spu.c $(SOURCES)/vh_spu_reverb.c $(SOURCES)/vh_spu_gaussian.c $(SOURCES)/vh_audio_resample.c $(SOURCES)/vh_audio_output_recovery.c $(SOURCES)/vh_audio_buffer_lease.c $(SOURCES)/vh_audout_queue_telemetry.c $(SOURCES)/vh_audout_queue_export.c $(SOURCES)/vh_audio_output_ramp.c $(SOURCES)/vh_audio_output_edges.c $(SOURCES)/vh_audio_diagnostics.c $(SOURCES)/vh_audio_diag_journal.c $(SOURCES)/vh_audio_diag_export.c $(SOURCES)/vh_audio_stream.c -o $@ $(LDLIBS) -lm

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

$(BUILD)/$(AUDOUT_AUDIO_TARGET).elf: probes/audout_audio_smoke.c source/vh_music_scene.c source/vh_music_scene.h source/vh_audio_resample.c source/vh_audio_resample.h source/vh_audio_assets.c source/vh_audio_assets.h source/vh_native_vab.c source/vh_native_vab.h source/vh_native_seq.c source/vh_native_seq.h source/vh_native_spu.c source/vh_spu_reverb.c source/vh_native_spu.h source/vh_spu_adpcm.c source/vh_spu_adpcm.h source/vh_spu_gaussian.c source/vh_spu_gaussian.h source/vh_audio_stream.c source/vh_audio_stream.h | $(BUILD)
	$(CC) $(CFLAGS) -Isource $(LDFLAGS) probes/audout_audio_smoke.c source/vh_music_scene.c source/vh_audio_resample.c source/vh_audio_assets.c source/vh_native_vab.c source/vh_native_seq.c source/vh_native_spu.c source/vh_spu_reverb.c source/vh_spu_adpcm.c source/vh_spu_gaussian.c source/vh_audio_stream.c -o $@ $(LDLIBS) -lm

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
