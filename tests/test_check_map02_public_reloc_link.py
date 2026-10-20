"""Host-toolchain regressions for asset-free MAP02 native partial-ELF link.

Source fixtures are tiny, independent synthetic C snippets. These tests do
NOT link actual game resources or claim to run original MAP02.
"""
from contextlib import redirect_stderr
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.check_map02_elf_code_witness import (
    EHDR, SHDR, RELA, compare_function_images, function_images,
)

from tools.check_map02_public_reloc_link import (
    REQUIRED_SYMBOLS, inspect_relocatable, make_inventory, main,
    stable_relocatable_output, stable_object_input, sealed_input_fd,
    audit_public_link, BUILD, OUTPUT, inspect_sealed_export_origins,
    function_code_sha256, summarize_partial_elf_undefined_symbols,
    save_private_undefined_manifest, PRIVATE_UNDEFINED_MANIFEST,
)


class PublicRelocatableELFTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-map02-reloc-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def compile(self, data, name="fixture", *, shared=False):
        src = self.root / (name + ".c")
        obj = self.root / (name + (".so" if shared else ".o"))
        src.write_text(data, encoding="utf-8")
        cmd = ["cc", "-std=c99", "-fPIC", str(src)]
        if shared:
            cmd += ["-shared"]
        else:
            cmd += ["-c"]
        subprocess.run(
            [*cmd, "-o", str(obj)], check=True, capture_output=True,
            text=True, timeout=30)
        return obj

    def all_exports(self):
        return "\n".join(
            f"void {name}(void) {{}}" for name in REQUIRED_SYMBOLS)

    def test_real_ld_r_proves_all_expected_exports_but_not_full_elf(self):
        names = list(REQUIRED_SYMBOLS)
        left = self.compile(
            "\n".join(f"void {name}(void) {{}}" for name in names[:5]),
            "cdside")
        right = self.compile(
            "\n".join(f"void {name}(void) {{}}" for name in names[5:]),
            "gpuside")
        combined = self.root / "combined.o"
        subprocess.run(["ld", "-r", "-o", str(combined), str(left),
                        str(right)], check=True, capture_output=True,
                       text=True, timeout=30)
        report = inspect_relocatable(combined)
        self.assertEqual(report["original_cd_gpu_and_vram_exports_verified"],
                         len(REQUIRED_SYMBOLS))
        self.assertTrue(
            report["ordinary_game_or_private_asset_symbols_may_be_unresolved"])

    def test_real_partial_elf_reports_required_unresolved_imports(self):
        # This is a real compiler-generated ET_REL; only names and
        # aggregate SHA-256 leave the test, not any retail image data.
        code = (self.all_exports() +
                "\nextern void private_runtime_stub(void);"
                "\nvoid caller(void) { private_runtime_stub(); }")
        obj = self.compile(code, "unresolved-real-elf")
        summary = inspect_relocatable(obj)
        self.assertEqual(
            summary["partial_elf_unresolved_strong_symbol_count"], 1)
        self.assertEqual(
            summary["partial_elf_unresolved_weak_symbol_count"], 0)
        self.assertEqual(
            summary["partial_elf_unresolved_strong_symbols_sha256"],
            summarize_partial_elf_undefined_symbols(
                "                 U private_runtime_stub\n")[
                    "partial_elf_unresolved_strong_symbols_sha256"])
        self.assertNotIn("private_runtime_stub", json.dumps(summary))

    def test_undefined_symbol_summary_is_stable_and_excludes_weak(self):
        lines = " U source_loader\n w optional_foo\n U alpha\n U source_loader\n"
        report = summarize_partial_elf_undefined_symbols(lines)
        reordered = summarize_partial_elf_undefined_symbols(
            "U alpha\n U source_loader\n v optional_foo\n")
        self.assertEqual(report, reordered)
        self.assertEqual(report["partial_elf_unresolved_strong_symbol_count"], 2)
        self.assertEqual(report["partial_elf_unresolved_weak_symbol_count"], 1)
        self.assertEqual(len(report["partial_elf_unresolved_strong_symbols_sha256"]), 64)
        self.assertNotIn("source_loader", json.dumps(report))
        changed = summarize_partial_elf_undefined_symbols(
            "U alpha\n U source_loader_new\n w optional_foo\n")
        self.assertNotEqual(
            report["partial_elf_unresolved_strong_symbols_sha256"],
            changed["partial_elf_unresolved_strong_symbols_sha256"])

    def test_undefined_symbol_summary_rejects_unexpected_nm_records(self):
        for invalid in ("U", "C forged_common", "U symbol trailing",
                        "untrusted.o:\n U symbol"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "unexpected undefined nm row"):
                    summarize_partial_elf_undefined_symbols(invalid)

    def test_private_undefined_manifest_written_only_in_owner_directory(self):
        code = (self.all_exports() +
                "\nextern void needed_for_link(void);"
                "\nvoid caller(void) { needed_for_link(); }")
        obj = self.compile(code, "private-nm-export")
        checked = inspect_relocatable(obj)
        report_dir = self.root / "private-manifest-output"
        report_dir.mkdir(mode=0o700)
        proof = stable_object_input(obj)
        fd = sealed_input_fd(obj, proof, index=8)
        try:
            save_private_undefined_manifest(
                report_dir, fd, checked, proof[0])
            with self.assertRaisesRegex(ValueError, "already exists"):
                save_private_undefined_manifest(
                    report_dir, fd, checked, proof[0])
        finally:
            os.close(fd)
        path = report_dir / PRIVATE_UNDEFINED_MANIFEST
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        report = json.loads(path.read_text())
        self.assertEqual(report["strong_symbols"], ["needed_for_link"])
        self.assertEqual(report["weak_symbols"], [])
        self.assertEqual(report["relocatable_elf_sha256"], proof[0])
        self.assertEqual(
            report["partial_elf_unresolved_strong_symbols_sha256"],
            checked["partial_elf_unresolved_strong_symbols_sha256"])
        self.assertNotIn("needed_for_link", json.dumps(checked))

    def test_private_undefined_manifest_fails_closed_on_wrong_audit_or_mode(self):
        code = (self.all_exports() +
                "\nextern void unresolved_private_probe(void);"
                "\nvoid caller(void) { unresolved_private_probe(); }")
        obj = self.compile(code, "private-nm-deny")
        checked = inspect_relocatable(obj)
        report_dir = self.root / "private-report-reject"
        report_dir.mkdir(mode=0o700)
        proof = stable_object_input(obj)
        fd = sealed_input_fd(obj, proof, index=12)
        try:
            altered = dict(checked)
            altered["partial_elf_unresolved_strong_symbol_count"] += 1
            with self.assertRaisesRegex(ValueError, "differ from sealed audit"):
                save_private_undefined_manifest(
                    report_dir, fd, altered, proof[0])
            self.assertFalse((report_dir / PRIVATE_UNDEFINED_MANIFEST).exists())
            report_dir.chmod(0o755)
            with self.assertRaisesRegex(ValueError, "not owner-only"):
                save_private_undefined_manifest(
                    report_dir, fd, checked, proof[0])
            self.assertFalse((report_dir / PRIVATE_UNDEFINED_MANIFEST).exists())
        finally:
            os.close(fd)

    def test_missing_cd_gpu_or_capture_export_rejected(self):
        missing = REQUIRED_SYMBOLS[-1]
        obj = self.compile(
            "\n".join(f"void {name}(void) {{}}"
                      for name in REQUIRED_SYMBOLS if name != missing))
        with self.assertRaisesRegex(ValueError, "export absent"):
            inspect_relocatable(obj)

    def test_global_data_cannot_impersonate_original_code_export(self):
        impostor = REQUIRED_SYMBOLS[0]
        obj = self.compile(
            "\n".join(f"void {name}(void) {{}}"
                      for name in REQUIRED_SYMBOLS if name != impostor) +
            f"\nint {impostor} = 1;\n")
        with self.assertRaisesRegex(ValueError, "strong code export"):
            inspect_relocatable(obj)

    def test_weak_function_cannot_impersonate_original_code_export(self):
        impostor = REQUIRED_SYMBOLS[-1]
        obj = self.compile(
            "\n".join(f"void {name}(void) {{}}"
                      for name in REQUIRED_SYMBOLS if name != impostor) +
            f"\nvoid {impostor}(void) __attribute__((weak));\n"
            f"void {impostor}(void) {{}}\n")
        with self.assertRaisesRegex(ValueError, "strong code export"):
            inspect_relocatable(obj)

    def test_global_text_label_without_func_type_is_not_a_function(self):
        missing = REQUIRED_SYMBOLS[0]
        # This provides an nm type T label, but readelf must reveal NOTYPE.
        obj = self.compile(
            "\n".join(f"void {name}(void) {{}}"
                      for name in REQUIRED_SYMBOLS if name != missing) +
            f'\n__asm__(".globl {missing}\\n{missing}:\\n nop\\n");\n',
            name="notype-impostor")
        direct = subprocess.run(
            ["nm", "-g", "--defined-only", str(obj)],
            capture_output=True, text=True, check=True)
        self.assertTrue(any(line.split()[-2:] == ["T", missing]
                            for line in direct.stdout.splitlines()))
        with self.assertRaisesRegex(ValueError, "ELF FUNC export"):
            inspect_relocatable(obj)

    def test_zero_sized_func_label_is_not_an_original_c_function(self):
        missing = REQUIRED_SYMBOLS[-1]
        obj = self.compile(
            "\n".join(f"void {name}(void) {{}}"
                      for name in REQUIRED_SYMBOLS if name != missing) +
            f'\n__asm__(".globl {missing}\\n.type {missing}, @function'
            f'\\n{missing}:\\n.size {missing}, .-{missing}\\n");\n',
            name="empty-function-impostor")
        with self.assertRaisesRegex(ValueError, "ELF FUNC bounds"):
            inspect_relocatable(obj)

    def test_nonzero_elf_func_extending_past_text_section_rejected(self):
        impostor = REQUIRED_SYMBOLS[0]
        # GNU as allows a FUNC's declared size to exceed its .text section.
        obj = self.compile(
            "\n".join(f"void {name}(void) {{}}"
                      for name in REQUIRED_SYMBOLS if name != impostor) +
            f'\n__asm__(".text\\n.globl {impostor}'
            f'\\n.type {impostor}, @function'
            f'\\n{impostor}:\\n nop'
            f'\\n.size {impostor}, 0x100000\\n");\n',
            name="oversized-func")
        with self.assertRaisesRegex(ValueError, "ELF FUNC bounds"):
            inspect_relocatable(obj)

    def test_nonzero_elf_func_starting_outside_text_section_rejected(self):
        impostor = REQUIRED_SYMBOLS[-1]
        # An out-of-range .set label still appears as T in nm and FUNC in
        # readelf. Its st_value cannot identify original bytes in .text.
        obj = self.compile(
            "\n".join(f"void {name}(void) {{}}"
                      for name in REQUIRED_SYMBOLS if name != impostor) +
            f'\n__asm__(".text\\n.globl {impostor}'
            f'\\n.type {impostor}, @function'
            f'\\n.set {impostor}, .+2048'
            f'\\n.size {impostor}, 2\\n");\n',
            name="out-of-range-func")
        with self.assertRaisesRegex(ValueError, "ELF FUNC bounds"):
            inspect_relocatable(obj)

    def test_aliased_required_exports_with_overlapping_text_bytes_rejected(self):
        original, impostor = REQUIRED_SYMBOLS[:2]
        # GNU nm reports two strong T exports and readelf reports two sized
        # GLOBAL FUNC entries. Both are individually inside .text, but the
        # second must not impersonate an independent CD/GPU code entrypoint.
        for offset in (0, 1):
            with self.subTest(offset=offset):
                definitions = "\n".join(
                    f"void {name}(void) {{}}"
                    for name in REQUIRED_SYMBOLS if name != impostor
                )
                asm = (f'\n__asm__(".text\\n.globl {impostor}'
                       f'\\n.type {impostor}, @function'
                       f'\\n.set {impostor}, {original}+{offset}'
                       f'\\n.size {impostor}, 1\\n");\n')
                obj = self.compile(definitions + asm, name=f"alias-{offset}")
                with self.assertRaisesRegex(ValueError, "ELF FUNC ranges overlap"):
                    inspect_relocatable(obj)

    def test_equal_offsets_in_distinct_text_sections_are_not_overlaps(self):
        first, second = REQUIRED_SYMBOLS[:2]
        source = (
            f'__attribute__((section(".text.map02_first"))) '
            f'void {first}(void) {{}}\n'
            f'__attribute__((section(".text.map02_second"))) '
            f'void {second}(void) {{}}\n' +
            "\n".join(f"void {name}(void) {{}}"
                      for name in REQUIRED_SYMBOLS[2:])
        )
        obj = self.compile(source, name="distinct-exec-sections")
        report = inspect_relocatable(obj)
        self.assertEqual(report["original_cd_gpu_and_vram_exports_verified"],
                         len(REQUIRED_SYMBOLS))

    def test_unresolved_capture_hook_rejected_even_if_other_exports_present(self):
        obj = self.compile(
            self.all_exports() +
            "\nextern void vh_map02_unresolved_callback(void);\n"
            "void call_unverified_probe(void) { vh_map02_unresolved_callback(); }")
        with self.assertRaisesRegex(ValueError, "unresolved MAP02 observer"):
            inspect_relocatable(obj)

    def test_complete_shared_object_cannot_impersonate_relocatable_evidence(self):
        obj = self.compile(self.all_exports(), shared=True)
        with self.assertRaisesRegex(ValueError, "relocatable ELF"):
            inspect_relocatable(obj)

    def test_non_elf_rejected(self):
        invalid = self.root / "not-an-ELF"
        invalid.write_bytes(b"invalid-original-code")
        with self.assertRaisesRegex(ValueError, "relocatable ELF"):
            inspect_relocatable(invalid)

    def test_input_objects_allow_normal_read_only_build_permissions(self):
        obj = self.compile(self.all_exports(), name="input-good")
        obj.chmod(0o644)
        initial = stable_object_input(obj)
        self.assertEqual(initial[0], hashlib.sha256(obj.read_bytes()).hexdigest())
        self.assertEqual(initial, stable_object_input(obj))

    def test_input_objects_detect_identical_byte_inode_replacement(self):
        obj = self.compile(self.all_exports(), name="input-swapped")
        obj.chmod(0o644)
        original = stable_object_input(obj)
        replacement = self.root / "identical-object.o"
        replacement.write_bytes(obj.read_bytes())
        replacement.chmod(0o644)
        os.replace(replacement, obj)
        self.assertNotEqual(original, stable_object_input(obj))

    def test_input_objects_reject_unsafe_permissions_and_hardlinks(self):
        obj = self.compile(self.all_exports(), name="input-unsafe")
        obj.chmod(0o666)
        with self.assertRaisesRegex(ValueError, "untrusted"):
            stable_object_input(obj)
        obj.chmod(0o644)
        linked = self.root / "input-hardlink.o"
        os.link(obj, linked)
        with self.assertRaisesRegex(ValueError, "untrusted"):
            stable_object_input(obj)

    def test_input_objects_reject_symlink_and_midread_inode_swap(self):
        obj = self.compile(self.all_exports(), name="input-race")
        obj.chmod(0o644)
        symlink = self.root / "input-symlink.o"
        symlink.symlink_to(obj)
        with self.assertRaises((ValueError, OSError)):
            stable_object_input(symlink)
        replacement = self.root / "input-replacement.o"
        replacement.write_bytes(obj.read_bytes())
        replacement.chmod(0o644)
        real_read = os.read
        swapped = False

        def read_swap(fd, count):
            nonlocal swapped
            data = real_read(fd, count)
            if data and not swapped:
                os.replace(replacement, obj)
                swapped = True
            return data

        with patch("tools.check_map02_public_reloc_link.os.read",
                   side_effect=read_swap):
            with self.assertRaisesRegex(ValueError, "identity changed"):
                stable_object_input(obj)
        self.assertTrue(swapped)

    def test_sealed_memory_input_cannot_change_after_source_copy(self):
        original = self.compile(self.all_exports(), name="seal-source")
        original.chmod(0o644)
        proof = stable_object_input(original)
        fd = sealed_input_fd(original, proof, index=0)
        try:
            required = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW |
                        fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
            self.assertEqual(fcntl.fcntl(fd, fcntl.F_GET_SEALS) & required,
                             required)
            with self.assertRaises(OSError):
                os.write(fd, b"modified")
            os.lseek(fd, 0, os.SEEK_SET)
            self.assertEqual(hashlib.sha256(os.read(fd, original.stat().st_size)
                                            ).hexdigest(), proof[0])
        finally:
            os.close(fd)

    def test_sealed_copy_rejects_midread_inode_replacement(self):
        original = self.compile(self.all_exports(), name="seal-race")
        original.chmod(0o644)
        proof = stable_object_input(original)
        replacement = self.root / "foreign-same-bytes.o"
        replacement.write_bytes(original.read_bytes())
        replacement.chmod(0o644)
        real_read = os.read
        switched = False

        def read_then_replace(fd, length):
            nonlocal switched
            data = real_read(fd, length)
            if data and not switched:
                switched = True
                os.replace(replacement, original)
            return data

        with patch("tools.check_map02_public_reloc_link.os.read",
                   side_effect=read_then_replace):
            with self.assertRaisesRegex(ValueError, "changed during sealed copy"):
                sealed_input_fd(original, proof, index=1)
        self.assertTrue(switched)

    def prepare_synthetic_original_objects(self):
        root = self.root / "pinned-upstream"
        pc = root / "platform" / "pc"
        built = pc / BUILD
        built.mkdir(parents=True)
        first = self.compile(
            "\n".join(f"void {name}(void) {{}}"
                      for name in REQUIRED_SYMBOLS[:5]), "original-cd")
        second = self.compile(
            "\n".join(f"void {name}(void) {{}}"
                      for name in REQUIRED_SYMBOLS[5:]), "original-gpu")
        game = built / "original-cd.o"
        gpu = built / "original-gpu.o"
        first.replace(game)
        second.replace(gpu)
        game.chmod(0o644)
        gpu.chmod(0o644)
        return root, game, gpu

    def test_sealed_source_function_sizes_match_linked_elf(self):
        obj = self.compile(self.all_exports(), name="sized-original")
        obj.chmod(0o644)
        fd = sealed_input_fd(obj, stable_object_input(obj), index=0)
        try:
            owners, sizes = inspect_sealed_export_origins(
                ["build-map02-cycle/sized-original.o"], [fd],
                with_sizes=True)
            self.assertEqual(set(owners), set(REQUIRED_SYMBOLS))
            self.assertTrue(all(size > 0 for size in sizes.values()))
            result = inspect_relocatable(
                f"/proc/self/fd/{fd}", pass_fds=(fd,),
                expected_source_sizes=sizes)
            self.assertEqual(result["original_cd_gpu_and_vram_exports_verified"],
                             len(REQUIRED_SYMBOLS))
            invalid = dict(sizes)
            invalid[REQUIRED_SYMBOLS[0]] += 1
            with self.assertRaisesRegex(ValueError, "size differs from sealed input"):
                inspect_relocatable(
                    f"/proc/self/fd/{fd}", pass_fds=(fd,),
                    expected_source_sizes=invalid)
        finally:
            os.close(fd)

    def test_zero_size_sealed_source_export_cannot_claim_provenance(self):
        name = REQUIRED_SYMBOLS[-1]
        obj = self.compile(
            "\n".join(f"void {symbol}(void) {{}}"
                      for symbol in REQUIRED_SYMBOLS if symbol != name) +
            f'\n__asm__(".text\\n.globl {name}'
            f'\\n.type {name}, @function'
            f'\\n{name}:\\n.size {name}, .-{name}\\n");\n',
            name="zero-size-sealed")
        obj.chmod(0o644)
        fd = sealed_input_fd(obj, stable_object_input(obj), index=0)
        try:
            with self.assertRaisesRegex(ValueError, "function size unavailable"):
                inspect_sealed_export_origins(
                    ["build-map02-cycle/zero-size-sealed.o"], [fd],
                    with_sizes=True)
        finally:
            os.close(fd)

    def test_source_elf_requires_valid_ident_and_header_versions(self):
        obj = self.compile("void LoadCdFile(void) {}\n",
                           name="elf-corrupt-version")
        original = obj.read_bytes()
        for index in (6, 20):  # EI_VERSION and e_version
            with self.subTest(index=index):
                mutated = bytearray(original)
                mutated[index] = 2
                obj.write_bytes(mutated)
                with obj.open("rb") as stream:
                    with self.assertRaisesRegex(ValueError, "requires x86-64"):
                        function_images(stream.fileno(), ("LoadCdFile",))
        obj.write_bytes(original)

    def test_elf_header_size_and_section_names_index_must_be_consistent(self):
        obj = self.compile("void LoadCdFile(void) {}\n",
                           name="elf-section-name-header")
        original = obj.read_bytes()
        header = list(EHDR.unpack_from(original))
        self.assertEqual(header[8], EHDR.size)
        self.assertGreater(header[13], 0)
        self.assertLess(header[13], header[12])
        shoff = header[6]
        self.assertEqual(SHDR.unpack_from(
            original, shoff + header[13] * SHDR.size)[1], 3)

        # Each mutation is based on the original compiler-generated ELF.
        for label, changed_index, replacement in (
                ("incorrect-header-byte-size", 8, EHDR.size - 1),
                ("out-of-range-section-name-index", 13, header[12])):
            with self.subTest(case=label):
                mutated = bytearray(original)
                fields = header.copy()
                fields[changed_index] = replacement
                EHDR.pack_into(mutated, 0, *fields)
                obj.write_bytes(mutated)
                with obj.open("rb") as stream:
                    with self.assertRaisesRegex(ValueError, "requires x86-64"):
                        function_images(stream.fileno(), ("LoadCdFile",))

        # Index 1 points to an ordinary section, not .shstrtab.
        fields = header.copy()
        fields[13] = next(
            i for i in range(1, header[12])
            if SHDR.unpack_from(original, shoff + i * SHDR.size)[1] != 3)
        mutated = bytearray(original)
        EHDR.pack_into(mutated, 0, *fields)
        obj.write_bytes(mutated)
        with obj.open("rb") as stream:
            with self.assertRaisesRegex(ValueError, "section name string table"):
                function_images(stream.fileno(), ("LoadCdFile",))

        obj.write_bytes(original)
        with obj.open("rb") as stream:
            self.assertIn(
                "LoadCdFile", function_images(stream.fileno(), ("LoadCdFile",)))

    def test_elf_symtab_cannot_use_non_string_section_for_names(self):
        obj = self.compile("void LoadCdFile(void) {}\n",
                           name="elf-fake-strtab")
        raw = bytearray(obj.read_bytes())
        header = EHDR.unpack_from(raw)
        shoff, shnum = header[6], header[12]
        symtabs = [(index, SHDR.unpack_from(raw, shoff + index * SHDR.size))
                   for index in range(shnum)
                   if SHDR.unpack_from(raw, shoff + index * SHDR.size)[1] == 2]
        self.assertEqual(len(symtabs), 1)
        index, symtab = symtabs[0]
        self.assertEqual(
            SHDR.unpack_from(raw, shoff + symtab[6] * SHDR.size)[1], 3)
        changed = list(symtab)
        changed[6] = 0  # SHT_NULL rather than SHT_STRTAB
        SHDR.pack_into(raw, shoff + index * SHDR.size, *changed)
        obj.write_bytes(raw)
        with obj.open("rb") as stream:
            with self.assertRaisesRegex(ValueError, "symbol string table invalid"):
                function_images(stream.fileno(), ("LoadCdFile",))

    def make_relocation_mutation_fixture(self, *, name):
        obj = self.compile(
            "extern int outside(void);\n"
            "int LoadCdFile(void) { return outside() + outside(); }\n",
            name=name)
        raw = bytearray(obj.read_bytes())
        header = EHDR.unpack_from(raw)
        section_offset, count = header[6], header[12]
        sections = [SHDR.unpack_from(raw, section_offset + i * SHDR.size)
                    for i in range(count)]
        for section in sections:
            if (section[1] == 4 and section[5] >= 2 * RELA.size
                    and section[9] == RELA.size
                    and section[7] < count
                    and sections[section[7]][2] & 0x4):
                return obj, raw, section, sections[section[7]]
        self.fail("expected at least two real executable-section ELF relocations")

    def test_elf_relocation_unknown_target_section_is_rejected(self):
        obj, raw, reloc, _ = self.make_relocation_mutation_fixture(
            name="relocation-forged-sh-info")
        header = EHDR.unpack_from(raw)
        shoff, shnum = header[6], header[12]
        section_index = next(
            index for index in range(shnum)
            if SHDR.unpack_from(raw, shoff + index * SHDR.size) == reloc)
        mutated = list(reloc)
        mutated[7] = shnum + 3  # sh_info points to no section
        SHDR.pack_into(raw, shoff + section_index * SHDR.size, *mutated)
        obj.write_bytes(raw)
        with obj.open("rb") as stream:
            with self.assertRaisesRegex(ValueError, "relocation target section invalid"):
                function_images(stream.fileno(), ("LoadCdFile",))

    def test_elf_relocation_outside_executable_section_is_rejected(self):
        obj, raw, reloc, target = self.make_relocation_mutation_fixture(
            name="relocation-outside")
        position, info, addend = RELA.unpack_from(raw, reloc[4])
        self.assertLess(position, target[5])
        RELA.pack_into(raw, reloc[4], target[5] + 8, info, addend)
        obj.write_bytes(raw)
        with obj.open("rb") as fp:
            with self.assertRaisesRegex(ValueError, "out-of-section relocation"):
                function_images(fp.fileno(), ("LoadCdFile",))

    def test_duplicate_overlapping_elf_relocations_are_rejected(self):
        obj, raw, reloc, _ = self.make_relocation_mutation_fixture(
            name="relocation-overlap")
        position, _, _ = RELA.unpack_from(raw, reloc[4])
        _, other_info, other_addend = RELA.unpack_from(
            raw, reloc[4] + RELA.size)
        RELA.pack_into(raw, reloc[4] + RELA.size,
                       position, other_info, other_addend)
        obj.write_bytes(raw)
        with obj.open("rb") as fp:
            with self.assertRaisesRegex(ValueError, "overlapping relocations"):
                function_images(fp.fileno(), ("LoadCdFile",))

    def test_unsupported_elf_relocation_kind_is_rejected(self):
        obj, raw, reloc, _ = self.make_relocation_mutation_fixture(
            name="relocation-unsupported")
        position, info, addend = RELA.unpack_from(raw, reloc[4])
        RELA.pack_into(raw, reloc[4], position,
                       (info & ~0xffffffff) | 0xfffffffe, addend)
        obj.write_bytes(raw)
        with obj.open("rb") as fp:
            with self.assertRaisesRegex(ValueError, "unsupported/out-of-function"):
                function_images(fp.fileno(), ("LoadCdFile",))

    def test_relocation_with_forged_symbol_index_is_rejected(self):
        obj, raw, reloc, _ = self.make_relocation_mutation_fixture(
            name="relocation-foreign-symbol-index")
        position, info, addend = RELA.unpack_from(raw, reloc[4])
        forged_info = (0xfffffffe << 32) | (info & 0xffffffff)
        RELA.pack_into(raw, reloc[4], position, forged_info, addend)
        obj.write_bytes(raw)
        with obj.open("rb") as fp:
            with self.assertRaisesRegex(ValueError, "relocation symbol index invalid"):
                function_images(fp.fileno(), ("LoadCdFile",))

    def test_relocation_straddling_start_of_required_func_is_rejected(self):
        obj = self.compile(
            "int padding_function(void) { return 42; }\n"
            "extern int outside(void);\n"
            "int LoadCdFile(void) { return outside() + outside(); }\n",
            name="relocation-cross-func")
        result = subprocess.run(
            ["readelf", "-W", "-s", str(obj)],
            check=True, capture_output=True, text=True)
        matching = [line.split() for line in result.stdout.splitlines()
                    if line.split()[-1:] == ["LoadCdFile"]]
        self.assertEqual(len(matching), 1)
        start = int(matching[0][1], 16)
        self.assertGreaterEqual(start, 4)
        raw = bytearray(obj.read_bytes())
        header = EHDR.unpack_from(raw)
        shoff, shnum = header[6], header[12]
        sections = [SHDR.unpack_from(raw, shoff + index * SHDR.size)
                    for index in range(shnum)]
        candidates = [
            sec for sec in sections
            if (sec[1] == 4 and sec[5] >= RELA.size
                and sec[7] < shnum
                and sections[sec[7]][2] & 0x4)
        ]
        self.assertTrue(candidates)
        reloc = candidates[0]
        _, info, addend = RELA.unpack_from(raw, reloc[4])
        # A four-byte PC-relative relocation placed two bytes before the
        # FUNC start reaches across its first two instruction bytes.
        RELA.pack_into(raw, reloc[4], start - 2,
                       (info & ~0xffffffff) | 4, addend)
        obj.write_bytes(raw)
        with obj.open("rb") as fp:
            with self.assertRaisesRegex(ValueError, "cross-function relocation"):
                function_images(fp.fileno(), ("LoadCdFile",))

    def test_real_relocatable_link_matches_nonrelocated_code(self):
        first = self.compile(
            "extern int ext(int);\n"
            "int LoadCdFile(void) { return ext(3); }\n"
            "int CdRead(void) { return ext(7); }\n",
            name="reloc-code-source")
        second = self.compile(
            "int ext(int v) { return v + 2; }\n"
            "void DrawOTag(void) { (void)ext(4); }\n",
            name="reloc-code-backend")
        combined = self.root / "reloc-code-combined.o"
        subprocess.run(["ld", "-r", "-o", str(combined),
                        str(first), str(second)],
                       capture_output=True, check=True, text=True)
        with first.open("rb") as fp:
            cd = function_images(fp.fileno(), ("LoadCdFile", "CdRead"))
        with second.open("rb") as fp:
            gpu = function_images(fp.fileno(), ("DrawOTag",))
        with combined.open("rb") as fp:
            linked = function_images(fp.fileno(),
                                     ("LoadCdFile", "CdRead", "DrawOTag"))
        report = compare_function_images({**cd, **gpu}, linked)
        self.assertGreater(report["source_link_function_code_bytes_checked"], 0)
        self.assertGreater(report["source_link_relocation_bytes_excluded"], 0)
        self.assertEqual(len(report["source_link_nonrelocated_function_code_sha256"]), 64)

        # A relocation displacement may be legitimately rewritten by ld.
        code, mask = linked["LoadCdFile"]
        self.assertTrue(mask)
        adjusted = bytearray(code)
        pos = min(mask)
        adjusted[pos] ^= 0x55
        changed = dict(linked)
        changed["LoadCdFile"] = (bytes(adjusted), mask)
        self.assertEqual(compare_function_images({**cd, **gpu}, changed), report)

        # Changing an actual non-relocation instruction must fail closed.
        bad = bytearray(code)
        good_pos = next(i for i in range(len(bad)) if i not in mask)
        bad[good_pos] ^= 0x11
        changed["LoadCdFile"] = (bytes(bad), mask)
        with self.assertRaisesRegex(ValueError, "unrelocated instruction bytes changed"):
            compare_function_images({**cd, **gpu}, changed)

    def test_output_only_relocation_cannot_hide_changed_instruction(self):
        # An extra linked relocation must not mask bytes absent from the
        # sealed original source relocation table, even if its size is valid.
        source = {"LoadCdFile": (b"\x55\xe8\x00\x00\x00\x00\x5d",
                                 frozenset({2, 3, 4, 5}))}
        forged = {"LoadCdFile": (b"\x90\xe8\x00\x00\x00\x00\x5d",
                                 frozenset({0, 2, 3, 4, 5}))}
        with self.assertRaisesRegex(ValueError, "relocated byte positions differ"):
            compare_function_images(source, forged)

    def test_source_only_relocation_cannot_hide_missing_output_relocation(self):
        source = {"DrawOTag": (b"\x90\x00\x00\x00\x00\xc3",
                               frozenset({1, 2, 3, 4}))}
        linked = {"DrawOTag": (b"\x90\x00\x00\x00\x00\xc3",
                               frozenset())}
        with self.assertRaisesRegex(ValueError, "relocated byte positions differ"):
            compare_function_images(source, linked)

    def test_out_of_bounds_relocation_mask_rejected(self):
        for bad_mask in (frozenset({-1}), frozenset({3})):
            with self.subTest(mask=bad_mask):
                with self.assertRaisesRegex(ValueError, "invalid relocated byte position"):
                    compare_function_images(
                        {"CdRead": (b"\x55\xc3", bad_mask)},
                        {"CdRead": (b"\x55\xc3", bad_mask)})

    def test_normalized_digest_binds_exact_relocation_byte_mask(self):
        # Both normalized images are identical: the newly excluded byte
        # is already zero. A code-only digest would silently collide.
        payload = bytes((0x90, 0x00, 0xc3))
        no_reloc = {"CdRead": (payload, frozenset())}
        zero_reloc = {"CdRead": (payload, frozenset({1}))}
        plain = compare_function_images(no_reloc, no_reloc)
        masked = compare_function_images(zero_reloc, zero_reloc)
        self.assertNotEqual(
            plain["source_link_nonrelocated_function_code_sha256"],
            masked["source_link_nonrelocated_function_code_sha256"])
        self.assertEqual(plain["source_link_function_code_bytes_checked"], 3)
        self.assertEqual(masked["source_link_function_code_bytes_checked"], 3)
        self.assertEqual(plain["source_link_relocation_bytes_excluded"], 0)
        self.assertEqual(masked["source_link_relocation_bytes_excluded"], 1)
        self.assertEqual(masked, compare_function_images(zero_reloc, zero_reloc))

    def test_relocation_mask_cannot_cover_entire_function(self):
        with self.assertRaisesRegex(ValueError, "no unrelocated function code"):
            compare_function_images(
                {"LoadCdFile": (b"AB", frozenset({0, 1}))},
                {"LoadCdFile": (b"CD", frozenset({0, 1}))})

    def test_machine_code_sha256_equal_before_and_after_real_ld_r(self):
        names = list(REQUIRED_SYMBOLS)
        first = self.compile(
            "\n".join(f"void {name}(void) {{}}"
                      for name in names[:5]), name="real-code-cd")
        second = self.compile(
            "extern void LoadCdFile(void);\n" +
            "\n".join(f"void {name}(void) {{ LoadCdFile(); }}"
                      for name in names[5:]), name="real-code-gpu")
        joined = self.root / "real-code-linked.o"
        subprocess.run(
            ["ld", "-r", "-o", str(joined), str(first), str(second)],
            check=True, capture_output=True, text=True, timeout=30)
        originals = {
            **function_code_sha256(first, names[:5]),
            **function_code_sha256(second, names[5:]),
        }
        self.assertEqual(function_code_sha256(joined, names), originals)

    def test_same_sized_machine_code_change_has_different_fingerprint(self):
        a = self.compile(
            "int LoadCdFile(void) { return 1; }\n", name="bytes-first")
        b = self.compile(
            "int LoadCdFile(void) { return 2; }\n", name="bytes-second")
        one = function_code_sha256(a, ["LoadCdFile"])
        two = function_code_sha256(b, ["LoadCdFile"])
        size_one = subprocess.run(
            ["nm", "-g", "-S", str(a)], capture_output=True,
            text=True, check=True).stdout.split()
        size_two = subprocess.run(
            ["nm", "-g", "-S", str(b)], capture_output=True,
            text=True, check=True).stdout.split()
        self.assertEqual(size_one[1], size_two[1])
        self.assertNotEqual(one, two)

    def test_each_required_export_is_owned_by_one_sealed_source_object(self):
        root, first, second = self.prepare_synthetic_original_objects()
        names = [f"{BUILD}/original-cd.o", f"{BUILD}/original-gpu.o"]
        files = [first, second]
        fds = [sealed_input_fd(path, stable_object_input(path), index=n)
               for n, path in enumerate(files)]
        try:
            owners = inspect_sealed_export_origins(names, fds)
            expected = {name: names[0] if i < 5 else names[1]
                        for i, name in enumerate(REQUIRED_SYMBOLS)}
            self.assertEqual(owners, expected)
        finally:
            for fd in fds:
                os.close(fd)

    def test_duplicate_required_export_across_sealed_objects_is_rejected(self):
        _, first, second = self.prepare_synthetic_original_objects()
        # Both valid .o files export the same required strong function.
        extra = self.compile(
            "\n".join(f"void {name}(void) {{}}"
                      for name in REQUIRED_SYMBOLS[5:]) +
            f"\nvoid {REQUIRED_SYMBOLS[0]}(void) {{}}\n",
            name="duplicate-owner")
        os.replace(extra, second)
        second.chmod(0o644)
        files = [first, second]
        fds = [sealed_input_fd(path, stable_object_input(path), index=n)
               for n, path in enumerate(files)]
        try:
            with self.assertRaisesRegex(ValueError, "sealed input export"):
                inspect_sealed_export_origins(["a.o", "b.o"], fds)
        finally:
            for fd in fds:
                os.close(fd)

    def test_weak_required_export_from_sealed_input_is_rejected(self):
        _, first, second = self.prepare_synthetic_original_objects()
        impostor = REQUIRED_SYMBOLS[-1]
        weakened = self.compile(
            "\n".join(f"void {name}(void) {{}}"
                      for name in REQUIRED_SYMBOLS[5:] if name != impostor) +
            f"\nvoid {impostor}(void) __attribute__((weak));\n"
            f"void {impostor}(void) {{}}\n", name="weak-owner")
        os.replace(weakened, second)
        second.chmod(0o644)
        fds = [sealed_input_fd(path, stable_object_input(path), index=n)
               for n, path in enumerate([first, second])]
        try:
            with self.assertRaisesRegex(ValueError, "sealed input export"):
                inspect_sealed_export_origins(["a.o", "b.o"], fds)
        finally:
            for fd in fds:
                os.close(fd)

    def test_full_partial_link_uses_sealed_fds_not_mutable_upstream_paths(self):
        root, game, gpu = self.prepare_synthetic_original_objects()
        files = [[f"{BUILD}/original-cd.o"], [f"{BUILD}/original-gpu.o"]]
        audited = {
            "original_game_translation_units_compiled": 1,
            "native_backend_and_observer_objects_compiled": 1,
        }
        real_run = subprocess.run
        observed = []
        inspectors = []
        witness_fds = []

        def record_link(command, *args, **kwargs):
            if command[0] == "ld" and "-r" in command:
                fds = kwargs.get("pass_fds", ())
                self.assertEqual(len(fds), 2)
                self.assertTrue(all(part.startswith("/proc/self/fd/")
                                    for part in command[4:]))
                self.assertEqual(command[4:],
                                 [f"/proc/self/fd/{fd}" for fd in fds])
                for fd in fds:
                    self.assertTrue(fcntl.fcntl(fd, fcntl.F_GET_SEALS)
                                    & fcntl.F_SEAL_WRITE)
                    with self.assertRaises(OSError):
                        os.write(fd, b"invalid")
                observed.append(True)
            if command[0] in ("readelf", "nm"):
                fds = kwargs.get("pass_fds", ())
                self.assertEqual(len(fds), 1)
                self.assertEqual(command[-1], f"/proc/self/fd/{fds[0]}")
                self.assertTrue(fcntl.fcntl(fds[0], fcntl.F_GET_SEALS)
                                & fcntl.F_SEAL_WRITE)
                # Only ELF inspection after the ld -r step contributes to
                # the output witness. Earlier nm calls audit the two inputs.
                if observed:
                    witness_fds.append(fds[0])
                    inspectors.append(command[0])
            return real_run(command, *args, **kwargs)

        with patch("tools.check_map02_public_reloc_link.preflight"), patch(
                "tools.check_map02_public_reloc_link.audit_objects",
                return_value=audited), patch(
                "tools.check_map02_public_reloc_link.make_inventory",
                return_value=files), patch(
                "tools.check_map02_public_reloc_link.subprocess.run",
                side_effect=record_link):
            report = audit_public_link(root, self.root / "bundle-unused",
                                       self.root / "sealed-link-result")
        self.assertEqual(observed, [True])
        # The relocation-aware byte witness reads sealed ELF bytes directly
        # with os.pread; it does not invoke two additional readelf probes.
        self.assertEqual(inspectors, ["readelf", "nm", "nm", "readelf", "readelf"])
        self.assertEqual(len(set(witness_fds)), 1)
        self.assertEqual(report["public_game_object_count"], 1)
        self.assertEqual(report["backend_and_observer_object_count"], 1)
        self.assertEqual(report["total_compiled_elf_objects"], 2)
        self.assertTrue(report["original_cd_gpu_source_function_sizes_matched"])
        self.assertTrue(report["original_cd_gpu_relocation_normalized_code_matched"])
        self.assertGreater(report["source_link_function_code_bytes_checked"], 0)
        self.assertGreater(report["source_link_function_code_bytes_checked"],
                           report["source_link_relocation_bytes_excluded"])
        self.assertEqual(len(report["source_link_nonrelocated_function_code_sha256"]), 64)
        self.assertEqual(report["verified_original_export_input_owners"], {
            name: f"{BUILD}/original-cd.o" if i < 5 else f"{BUILD}/original-gpu.o"
            for i, name in enumerate(REQUIRED_SYMBOLS)
        })
        expected_input_manifest = [
            {"path": path, "sha256": stable_object_input(source)[0]}
            for path, source in (
                (f"{BUILD}/original-cd.o", game),
                (f"{BUILD}/original-gpu.o", gpu),
            )
        ]
        expected_hash = hashlib.sha256(json.dumps(
            expected_input_manifest, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        self.assertEqual(report["ordered_object_input_manifest_sha256"],
                         expected_hash)
        self.assertFalse(report["fully_linked_game_executable"])
        self.assertFalse(report["actual_gameplay_executed"])

    def test_original_source_replaced_during_sealed_link_fails_closed(self):
        root, game, gpu = self.prepare_synthetic_original_objects()
        files = [[f"{BUILD}/original-cd.o"], [f"{BUILD}/original-gpu.o"]]
        audited = {
            "original_game_translation_units_compiled": 1,
            "native_backend_and_observer_objects_compiled": 1,
        }
        real_run = subprocess.run
        changed = []

        def replace_during_ld(command, *args, **kwargs):
            if command[0] == "ld" and "-r" in command:
                self.assertEqual(len(kwargs.get("pass_fds", ())), 2)
                replacement = game.with_name("foreign-same-bytes.o")
                replacement.write_bytes(game.read_bytes())
                replacement.chmod(0o644)
                os.replace(replacement, game)
                changed.append(True)
            return real_run(command, *args, **kwargs)

        with patch("tools.check_map02_public_reloc_link.preflight"), patch(
                "tools.check_map02_public_reloc_link.audit_objects",
                return_value=audited), patch(
                "tools.check_map02_public_reloc_link.make_inventory",
                return_value=files), patch(
                "tools.check_map02_public_reloc_link.subprocess.run",
                side_effect=replace_during_ld):
            with self.assertRaisesRegex(ValueError, "changed or swapped"):
                audit_public_link(root, self.root / "bundle-unused",
                                  self.root / "sealed-raced-link")
        self.assertEqual(changed, [True])

    def test_sealed_symbol_inspection_uses_one_immutable_deleted_file(self):
        obj = self.compile(self.all_exports(), name="symbol-snapshot")
        obj.chmod(0o600)
        proof = stable_relocatable_output(obj)
        fd = sealed_input_fd(obj, proof, index=2)
        try:
            obj.unlink()
            result = inspect_relocatable(
                f"/proc/self/fd/{fd}", pass_fds=(fd,))
            self.assertEqual(result["original_cd_gpu_and_vram_exports_verified"],
                             len(REQUIRED_SYMBOLS))
        finally:
            os.close(fd)

    def test_output_replaced_after_readelf_before_nm_fails_closed(self):
        root, game, gpu = self.prepare_synthetic_original_objects()
        files = [[f"{BUILD}/original-cd.o"], [f"{BUILD}/original-gpu.o"]]
        audited = {
            "original_game_translation_units_compiled": 1,
            "native_backend_and_observer_objects_compiled": 1,
        }
        output_dir = self.root / "replacement-during-symbol-audit"
        real_run = subprocess.run
        readers = []
        swapped = False
        linked_ready = False

        def swap_after_header(command, *args, **kwargs):
            nonlocal swapped, linked_ready
            # Source readelf/nm probes now run before ld -r. Only output
            # probes may trigger the simulated malicious path replacement.
            if command[0] in ("readelf", "nm") and linked_ready:
                fds = kwargs.get("pass_fds", ())
                self.assertEqual(len(fds), 1)
                self.assertEqual(command[-1], f"/proc/self/fd/{fds[0]}")
                readers.append(command[0])
            result = real_run(command, *args, **kwargs)
            if command[0] == "ld" and "-r" in command:
                linked_ready = True
            elif command[0] == "readelf" and linked_ready and not swapped:
                linked = output_dir / OUTPUT
                foreign = output_dir / "same-byte-foreign-inode.o"
                foreign.write_bytes(linked.read_bytes())
                foreign.chmod(0o600)
                os.replace(foreign, linked)
                swapped = True
            return result

        with patch("tools.check_map02_public_reloc_link.preflight"), patch(
                "tools.check_map02_public_reloc_link.audit_objects",
                return_value=audited), patch(
                "tools.check_map02_public_reloc_link.make_inventory",
                return_value=files), patch(
                "tools.check_map02_public_reloc_link.subprocess.run",
                side_effect=swap_after_header):
            with self.assertRaisesRegex(ValueError, "differs from linked proof"):
                audit_public_link(root, self.root / "bundle-unused", output_dir)
        self.assertTrue(swapped)
        # Source/output function bytes are now inspected by os.pread, so
        # subprocess instrumentation sees only five post-link readers.
        self.assertEqual(readers, ["readelf", "nm", "nm", "readelf", "readelf"])

    def test_partial_elf_double_read_proof_is_stable(self):
        obj = self.compile(self.all_exports(), name="stable")
        obj.chmod(0o600)
        proof = stable_relocatable_output(obj)
        self.assertEqual(proof[0], hashlib.sha256(obj.read_bytes()).hexdigest())
        self.assertEqual(stable_relocatable_output(obj, expected=proof), proof)

    def test_partial_elf_rejects_world_readable_symlink_and_hardlink(self):
        obj = self.compile(self.all_exports(), name="untrusted")
        # Do not depend on the runner's default umask.
        obj.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "metadata"):
            stable_relocatable_output(obj)
        obj.chmod(0o600)
        symlink = self.root / "partial-symlink.o"
        symlink.symlink_to(obj)
        with self.assertRaises((ValueError, OSError)):
            stable_relocatable_output(symlink)
        hardlink = self.root / "partial-hardlink.o"
        os.link(obj, hardlink)
        with self.assertRaisesRegex(ValueError, "metadata"):
            stable_relocatable_output(obj)

    def test_partial_elf_rejects_identical_bytes_different_inode(self):
        obj = self.compile(self.all_exports(), name="original")
        obj.chmod(0o600)
        proof = stable_relocatable_output(obj)
        replacement = self.root / "same-bytes-different-inode.o"
        replacement.write_bytes(obj.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, obj)
        with self.assertRaisesRegex(ValueError, "differs from linked proof"):
            stable_relocatable_output(obj, expected=proof)

    def test_partial_elf_rejects_path_swap_during_descriptor_read(self):
        obj = self.compile(self.all_exports(), name="during-read")
        obj.chmod(0o600)
        replacement = self.root / "swapped.o"
        replacement.write_bytes(obj.read_bytes())
        replacement.chmod(0o600)
        original_read = os.read
        swapped = False

        def read_and_swap(fd, count):
            nonlocal swapped
            data = original_read(fd, count)
            if data and not swapped:
                swapped = True
                os.replace(replacement, obj)
            return data

        with patch("tools.check_map02_public_reloc_link.os.read",
                   side_effect=read_and_swap):
            with self.assertRaisesRegex(ValueError, "inode or metadata changed"):
                stable_relocatable_output(obj)
        self.assertTrue(swapped)

    def test_make_inventory_ignores_inherited_untrusted_makefile(self):
        # Only tiny synthetic inventories are evaluated. A caller-supplied
        # MAKEFILES script must never run during the audit's GNU Make read.
        upstream = self.root / "upstream"
        pc = upstream / "platform" / "pc"
        pc.mkdir(parents=True)
        bundle = self.root / "private-bundle"
        bundle.mkdir()
        (pc / "Makefile").write_text(
            "VH_MAP02_PUBLIC_CODE_OBJS := build-map02-cycle/game.o\n"
            "VH_MAP02_PUBLIC_BACKEND_OBJS := build-map02-cycle/gpu.o\n",
            encoding="utf-8")
        (bundle / "map02_cycle.mk").write_text(
            "# Synthetic opt-in overlay\n", encoding="utf-8")
        hostile = self.root / "unexpected-makefile"
        hostile.write_text(
            "$(shell touch untrusted-makefile-parsed)\n", encoding="utf-8")
        marker = pc / "untrusted-makefile-parsed"
        injected = {
            "MAKEFILES": str(hostile),
            "MAKEFLAGS": "--no-print-directory",
            "PYTHONPATH": str(self.root / "foreign-python"),
        }
        with patch.dict(os.environ, injected):
            result = make_inventory(upstream, bundle)
        self.assertEqual(result, [
            ["build-map02-cycle/game.o"], ["build-map02-cycle/gpu.o"]])
        self.assertFalse(marker.exists())

    def test_cli_redacts_filesystem_paths_and_linker_errors(self):
        private_path = str(self.root / "owned-original-private-psx-image")
        arguments = [
            "check_map02_public_reloc_link", "pinned-upstream",
            "private-bundle", "new-partial-output"]
        for failure in (
                OSError("private file: " + private_path),
                subprocess.TimeoutExpired(["ld", private_path], 30),
                ValueError("ld stderr included " + private_path)):
            output = io.StringIO()
            with patch("sys.argv", arguments), patch(
                    "tools.check_map02_public_reloc_link.audit_public_link",
                    side_effect=failure), redirect_stderr(output):
                with self.assertRaises(SystemExit) as error:
                    main()
            self.assertEqual(error.exception.code, 2)
            self.assertNotIn(private_path, output.getvalue())
            self.assertIn("public relocatable audit failed", output.getvalue())


if __name__ == "__main__":
    unittest.main()
