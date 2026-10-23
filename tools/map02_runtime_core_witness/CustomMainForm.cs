// Optional owner-local BizHawk 2.11 External Tool, NOT part of public CI.
// Build inside a private BizHawk source checkout with the .csproj alongside.
// This observes the *loaded* IEmulator, unlike client.getconfig() which
// observes only PreferredCores; no BIOS, disc or movie is inspected.
using System;
using System.Diagnostics;
using System.IO;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Security.Cryptography;
using System.Text;
using System.Globalization;
using System.Collections.Generic;
#if VH_MAP02_UNIX_BUILD
using Mono.Unix.Native;
#endif
using System.Windows.Forms;
using BizHawk.Client.Common;
using BizHawk.Client.EmuHawk;
using BizHawk.Emulation.Common;

namespace VhMap02CoreWitness
{
    [ExternalTool("VH MAP02 Core Witness",
        Description = "Private actual-IEmulator core-name evidence (no media data)")]
    public sealed class CoreWitnessForm : ToolFormBase, IExternalToolForm
    {
        [RequiredService]
        public IEmulator Emulator { get; set; } = null!; // injected after construction

        private readonly Label _summary;
        private readonly Button _save;
        // One attempt per externally launched process. Never silently retry a
        // failed file write or overwrite a witness from an older process.
        private bool _automaticWitnessAttempted;
        private const string AutomaticWitnessFile = "vh-map02-runtime-core-auto.txt";
        private const string AutomaticWitnessEnvironment = "VH_MAP02_CORE_AUTOWRITE_PRIVATE_DIR";
        private const string ExpectedAssemblySha256Environment = "VH_MAP02_CORE_EXPECTED_DLL_SHA256";
        private const string ExpectedCoreAssemblySha256Environment = "VH_MAP02_CORE_EXPECTED_CORE_ASSEMBLY_SHA256";
        private const string ExpectedNativeModuleSha256Environment = "VH_MAP02_CORE_EXPECTED_NATIVE_MODULE_SHA256";
        private const string ExpectedRuntimeCoreType = "BizHawk.Emulation.Cores.Sony.PSX.Octoshock";
#if VH_MAP02_UNIX_BUILD
        private static readonly string[] NativeCoreModuleNames =
            { "liboctoshock.dll.so", "liboctoshock.so" };
#else
        private static readonly string[] NativeCoreModuleNames = { "octoshock.dll" };
#endif
        protected override string WindowTitleStatic => "VH MAP02 PSX core witness";

        public CoreWitnessForm()
        {
            UpdateWindowTitle(); // BizHawk FormBase forbids direct Text assignment
            Width = 520;
            Height = 165;
            StartPosition = FormStartPosition.CenterParent;
            _summary = new Label
            {
                Left = 12, Top = 12, Width = 478, Height = 55,
                Text = "Runtime IEmulator core not yet available."
            };
            _save = new Button
            {
                Left = 12, Top = 79, Width = 245, Height = 30,
                Text = "Write private core witness...",
                Enabled = false // fail closed before BizHawk injects a real core
            };
            _save.Click += SaveWitness;
            Controls.Add(_summary);
            Controls.Add(_save);
            // Owner-visible status starts unverified until BizHawk injects a core.
        }

        // EmuHawk injects RequiredService after constructor. Restart is also
        // called after a new movie session starts; do not cache the core.
        public override void Restart() => RefreshStatus();

        private void RefreshStatus()
        {
            var core = Emulator;
            // Genuine BizHawk uses a NullEmulator when no ROM is loaded.
            // This exact *post-injection* status is only reached after
            // ToolManager invokes Restart() with a live IEmulator service.
            // It is UI-only; never claim PS1 or Octoshock authentication.
            if (core is NullEmulator
                && core.SystemId == VSystemID.Raw.NULL
                && core.Attributes()?.CoreName == "NullHawk")
            {
                _summary.Text = "Injected IEmulator: NullHawk (no game); witness disabled.";
                _save.Enabled = false;
                return;
            }
            if (core == null || core.SystemId != "PSX" || core.Frame < 0)
            {
                _summary.Text = "No loaded PSX core; capture disabled.";
                _save.Enabled = false;
                return;
            }
            var loadedName = core.Attributes()?.CoreName;
            if (loadedName != "Octoshock")
            {
                _summary.Text = "Actual loaded PSX core is not Octoshock.";
                _save.Enabled = false;
                return;
            }
            var runtimeType = core.GetType();
            if (!string.Equals(runtimeType.FullName, ExpectedRuntimeCoreType,
                    StringComparison.Ordinal)
                || !string.Equals(runtimeType.Assembly.GetName().Name,
                    "BizHawk.Emulation.Cores", StringComparison.Ordinal))
            {
                _summary.Text = "Octoshock name does not match the concrete BizHawk runtime type.";
                _save.Enabled = false;
                return;
            }
            try
            {
                // Core identity alone is insufficient: Octoshock's native
                // library must also be mapped in this exact EmuHawk process.
                FindLoadedNativeCoreModulePath();
            }
            catch (Exception)
            {
                _summary.Text = "Octoshock native module is not present; capture disabled.";
                _save.Enabled = false;
                return;
            }
            _summary.Text = "Concrete BizHawk PSX/Octoshock and native module are loaded."
                + Environment.NewLine
                + "BIOS, disc image and BK2 replay are NOT verified.";
            _save.Enabled = true;
            TryAutomaticWitness(core);
        }

        private void TryAutomaticWitness(IEmulator actualCore)
        {
            // Opt-in is passed ONLY to this child by our private launcher.
            // No environment opt-in -> no automatic file or UI action.
            var targetDir = Environment.GetEnvironmentVariable(AutomaticWitnessEnvironment);
            if (string.IsNullOrEmpty(targetDir) || _automaticWitnessAttempted) return;
            _automaticWitnessAttempted = true;
            try
            {
                RequireNonGitPrivateFolder(targetDir);
                var payload = Snapshot(actualCore);
                var target = Path.Combine(targetDir, AutomaticWitnessFile);
                // Do not use an existing / symlinked destination. Exclusive
                // CreateNew prevents replacing stale/manual evidence.
                using (var output = new FileStream(
                    target, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                {
#if VH_MAP02_UNIX_BUILD
                    if (Syscall.chmod(target, FilePermissions.S_IRUSR | FilePermissions.S_IWUSR) != 0)
                        throw new InvalidOperationException();
#endif
                    using (var writer = new StreamWriter(output, new UTF8Encoding(false)))
                    {
                        writer.Write(payload);
                        writer.Flush();
                        output.Flush(true);
                    }
                }
                _summary.Text = "PSX/Octoshock automatic private core-only witness saved."
                    + Environment.NewLine
                    + "BIOS, disc, BK2 and MAP02 remain unverified.";
            }
            catch (Exception)
            {
                // Keep identifiers, folders and OS ACL details entirely local.
                // Owner capture must fail closed if the expected file is absent.
                _summary.Text = "Automatic private core witness rejected."
                    + Environment.NewLine
                    + "No original gameplay authentication claimed.";
            }
        }

        private static void RequireNonGitPrivateFolder(string folder)
        {
            var directory = new DirectoryInfo(Path.GetFullPath(folder));
            if (!directory.Exists) throw new InvalidOperationException();
            for (var current = directory; current != null; current = current.Parent)
            {
                if ((current.Attributes & FileAttributes.ReparsePoint) != 0)
                    throw new InvalidOperationException();
                var marker = Path.Combine(current.FullName, ".git");
                if (File.Exists(marker) || Directory.Exists(marker))
                    throw new InvalidOperationException();
            }
#if VH_MAP02_UNIX_BUILD
            // Linux x86_64 uses POSIX owner/mode checks. The Python launcher
            // repeats these checks before creating output; the tool independently
            // refuses group/world access and folders owned by another UID.
            if (Syscall.stat(directory.FullName, out var unixStat) != 0
                || unixStat.st_uid != Syscall.geteuid()
                || (unixStat.st_mode & (FilePermissions.S_IRWXG | FilePermissions.S_IRWXO)) != 0)
                throw new InvalidOperationException();
#else
            // A Windows folder can be publicly readable despite chmod(0700)
            // semantics elsewhere. Check the effective NTFS DACL, including
            // inherited ALLOW ACEs. No ACL or SID is ever logged or exported.
            using (var current = WindowsIdentity.GetCurrent())
            {
                var user = current.User;
                var acl = Directory.GetAccessControl(directory.FullName);
                var owner = acl.GetOwner(typeof(SecurityIdentifier))
                    as SecurityIdentifier;
                if (user == null || owner == null || owner.Value != user.Value)
                    throw new InvalidOperationException();
                var writableByOwner = false;
                foreach (FileSystemAccessRule entry in acl.GetAccessRules(
                    true, true, typeof(SecurityIdentifier)))
                {
                    if (entry.AccessControlType != AccessControlType.Allow)
                        continue;
                    var sid = (SecurityIdentifier)entry.IdentityReference;
                    var trusted = sid.Value == user.Value
                        || sid.Value == "S-1-5-18" // LOCAL SYSTEM
                        || sid.Value == "S-1-5-32-544"; // BUILTIN Administrators
                    if (!trusted) throw new InvalidOperationException();
                    if (sid.Value == user.Value
                        && (entry.FileSystemRights & FileSystemRights.WriteData)
                           == FileSystemRights.WriteData)
                        writableByOwner = true;
                }
                if (!writableByOwner) throw new InvalidOperationException();
            }
#endif
        }

        private static string FindLoadedNativeCoreModulePath()
        {
#if VH_MAP02_UNIX_BUILD
            // Process.Modules is not consistently implemented by Mono on Unix.
            // The kernel maps file is the authoritative list of this process's
            // mapped shared objects. Reject deleted/missing or ambiguous modules.
            var found = new HashSet<string>(StringComparer.Ordinal);
            foreach (var line in File.ReadLines("/proc/self/maps"))
            {
                var columns = line.Split(new[] { ' ' }, 6,
                    StringSplitOptions.RemoveEmptyEntries);
                if (columns.Length < 6) continue;
                var mapped = DecodeProcMapsPath(columns[5]);
                var deletedSuffix = " (deleted)";
                if (mapped.EndsWith(deletedSuffix, StringComparison.Ordinal))
                {
                    var deletedName = Path.GetFileName(mapped.Substring(
                        0, mapped.Length - deletedSuffix.Length));
                    if (Array.IndexOf(NativeCoreModuleNames, deletedName) >= 0)
                        throw new InvalidOperationException();
                    continue;
                }
                if (Array.IndexOf(NativeCoreModuleNames, Path.GetFileName(mapped)) < 0)
                    continue;
                if (!Path.IsPathRooted(mapped) || !File.Exists(mapped))
                    throw new InvalidOperationException();
                found.Add(Path.GetFullPath(mapped));
            }
            if (found.Count != 1) throw new InvalidOperationException();
            foreach (var path in found) return path;
            throw new InvalidOperationException();
#else
            string? found = null;
            using (var process = Process.GetCurrentProcess())
            {
                foreach (ProcessModule module in process.Modules)
                {
                    if (!string.Equals(module.ModuleName, NativeCoreModuleNames[0],
                            StringComparison.OrdinalIgnoreCase))
                        continue;
                    if (!string.IsNullOrEmpty(found))
                        throw new InvalidOperationException();
                    found = module.FileName;
                }
            }
            if (string.IsNullOrEmpty(found) || !Path.IsPathRooted(found)
                || !File.Exists(found))
                throw new InvalidOperationException();
            return found!;
#endif
        }

#if VH_MAP02_UNIX_BUILD
        private static string DecodeProcMapsPath(string value)
        {
            var result = new StringBuilder(value.Length);
            for (var i = 0; i < value.Length; i++)
            {
                if (value[i] == (char)92 && i + 3 < value.Length
                    && value[i + 1] >= '0' && value[i + 1] <= '7'
                    && value[i + 2] >= '0' && value[i + 2] <= '7'
                    && value[i + 3] >= '0' && value[i + 3] <= '7')
                {
                    var code = (value[i + 1] - '0') * 64
                        + (value[i + 2] - '0') * 8 + value[i + 3] - '0';
                    result.Append((char)code);
                    i += 3;
                }
                else result.Append(value[i]);
            }
            return result.ToString();
        }
#endif

        private static string FileSha256(string location)
        {
            // Hash the mapped module's on-disk file, not its in-memory pages.
            // FileShare.Read blocks ordinary concurrent writes while hashing.
            if (string.IsNullOrEmpty(location) || !Path.IsPathRooted(location)
                || !File.Exists(location)) throw new InvalidOperationException();
            using (var input = new FileStream(
                location, FileMode.Open, FileAccess.Read, FileShare.Read))
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(input))
                    .Replace("-", "").ToLowerInvariant();
        }

        private static string ExecutingAssemblyFileSha256()
        {
            // This hashes the file at the executing assembly location. It is
            // NOT cryptographic proof of CLR in-memory module bytes.
            return FileSha256(typeof(CoreWitnessForm).Assembly.Location);
        }

        private static void RequireOptionalSha256Pin(string environmentName, string actual)
        {
            var expected = Environment.GetEnvironmentVariable(environmentName);
            if (string.IsNullOrEmpty(expected)) return;
            if (!IsSha256Hex(expected)
                || !string.Equals(actual, expected, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException();
        }

        private static bool IsSha256Hex(string value)
        {
            if (value == null || value.Length != 64) return false;
            foreach (var c in value)
                if (!((c >= '0' && c <= '9')
                    || (c >= 'a' && c <= 'f')
                    || (c >= 'A' && c <= 'F'))) return false;
            return true;
        }

        private static string Snapshot(IEmulator actualCore)
        {
            // A recorded BK2 Core header or configured preferred core is NOT
            // accepted as the identity: sample the currently injected core.
            if (actualCore == null || actualCore.SystemId != "PSX"
                || actualCore.Attributes()?.CoreName != "Octoshock"
                || actualCore.Frame < 0) throw new InvalidOperationException();

            var runtimeType = actualCore.GetType();
            if (!string.Equals(runtimeType.FullName, ExpectedRuntimeCoreType,
                    StringComparison.Ordinal)
                || !string.Equals(runtimeType.Assembly.GetName().Name,
                    "BizHawk.Emulation.Cores", StringComparison.Ordinal))
                throw new InvalidOperationException();

            var coreAssemblySha256 = FileSha256(runtimeType.Assembly.Location);
            var nativeModulePath = FindLoadedNativeCoreModulePath();
            var nativeModuleName = Path.GetFileName(nativeModulePath);
            var nativeModuleSha256 = FileSha256(nativeModulePath);
            var executingAssemblySha256 = ExecutingAssemblyFileSha256();

            // Pins are optional, independently supplied local values. If set,
            // each must match before a witness is written. Missing pins do not
            // become implicit claims of official-file authenticity.
            RequireOptionalSha256Pin(ExpectedAssemblySha256Environment,
                executingAssemblySha256);
            RequireOptionalSha256Pin(ExpectedCoreAssemblySha256Environment,
                coreAssemblySha256);
            RequireOptionalSha256Pin(ExpectedNativeModuleSha256Environment,
                nativeModuleSha256);

            using (var process = Process.GetCurrentProcess())
            {
#if VH_MAP02_UNIX_BUILD
                var start = LinuxProcessStartUtcTicks(process.Id);
#else
                var start = process.StartTime.ToUniversalTime().Ticks;
#endif
                if (process.Id <= 0 || start <= 0) throw new InvalidOperationException();
                return "VH_MAP02_RUNTIME_CORE_WITNESS_V3\n"
                    + "system=PSX\n"
                    + "loaded_core=Octoshock\n"
                    + "core_source=IEmulator.Attributes.CoreName\n"
                    + "runtime_core_type=" + ExpectedRuntimeCoreType + "\n"
                    + "core_assembly_sha256=" + coreAssemblySha256 + "\n"
                    + "native_core_module_name=" + nativeModuleName + "\n"
                    + "native_core_module_sha256=" + nativeModuleSha256 + "\n"
                    + "tool_assembly_sha256=" + executingAssemblySha256 + "\n"
                    + "process_id=" + process.Id + "\n"
                    + "process_start_utc_ticks=" + start + "\n"
                    + "frame_count=" + actualCore.Frame + "\n"
                    + "bios=unverified\n"
                    + "disc=unverified\n"
                    + "movie_sync=unverified\n";
            }
        }

#if VH_MAP02_UNIX_BUILD
        [System.Runtime.InteropServices.DllImport("libc", EntryPoint = "sysconf", SetLastError = true)]
        private static extern long LinuxSysconf(int name);

        private static long LinuxProcessStartUtcTicks(int pid)
        {
            var stat = File.ReadAllText("/proc/self/stat");
            var close = stat.LastIndexOf(')');
            if (close < 0) throw new InvalidOperationException();
            var fields = stat.Substring(close + 1).Trim().Split(
                new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
            if (fields.Length <= 19) throw new InvalidOperationException();
            var pidText = stat.Substring(0, stat.IndexOf(' '));
            if (!int.TryParse(pidText, NumberStyles.None,
                    CultureInfo.InvariantCulture, out var observedPid)
                || observedPid != pid) throw new InvalidOperationException();
            if (!ulong.TryParse(fields[19], NumberStyles.None,
                    CultureInfo.InvariantCulture, out var startClockTicks))
                throw new InvalidOperationException();
            ulong bootTime = 0;
            var foundBootTime = false;
            foreach (var line in File.ReadLines("/proc/stat"))
            {
                if (!line.StartsWith("btime ", StringComparison.Ordinal)) continue;
                var parts = line.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length != 2 || !ulong.TryParse(parts[1], NumberStyles.None,
                        CultureInfo.InvariantCulture, out bootTime))
                    throw new InvalidOperationException();
                foundBootTime = true;
                break;
            }
            var hz = LinuxSysconf(2); // POSIX _SC_CLK_TCK on Linux.
            if (!foundBootTime || hz <= 0) throw new InvalidOperationException();
            var rate = checked((ulong)hz);
            // /proc/stat btime is UNIX seconds; witness V3 uses .NET UTC
            // ticks since 0001-01-01 (the 1970 offset is mandatory).
            var start = checked(621355968000000000UL
                + (checked(checked(bootTime * rate + startClockTicks)
                    * 10000000UL) / rate));
            if (start < 621355968000000000UL || start > 725811840000000000UL)
                throw new InvalidOperationException();
            return checked((long)start);
        }
#endif

        private void SaveWitness(object sender, EventArgs args)
        {
            try
            {
                using (var dialog = new FolderBrowserDialog
                {
                    Description = "Select an existing OWNER-PRIVATE folder outside Git",
                    ShowNewFolderButton = false
                })
                {
                    if (dialog.ShowDialog(this) != DialogResult.OK) return;
                    RequireNonGitPrivateFolder(dialog.SelectedPath);
                    var payload = Snapshot(Emulator);
                    var target = Path.Combine(dialog.SelectedPath,
                        "vh-map02-runtime-core-witness-"
                        + Guid.NewGuid().ToString("N") + ".txt");
                    // Exclusive creation; do not overwrite or append to media.
                    using (var output = new FileStream(
                        target, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                    {
#if VH_MAP02_UNIX_BUILD
                        if (Syscall.chmod(target, FilePermissions.S_IRUSR | FilePermissions.S_IWUSR) != 0)
                            throw new InvalidOperationException();
#endif
                        using (var writer = new StreamWriter(
                            output, new UTF8Encoding(false)))
                        {
                            writer.Write(payload);
                            writer.Flush();
                            output.Flush(true);
                        }
                    }
                    MessageBox.Show(this,
                        "A core-only witness was written privately. "
                        + "Do not upload it or confuse it with BIOS/MAP02 proof.",
                        "Core witness saved");
                }
            }
            catch (Exception)
            {
                // Do not leak absolute private source paths in diagnostics.
                MessageBox.Show(this,
                    "Core witness unavailable; no authenticated gameplay claim.",
                    "Core witness rejected");
            }
            RefreshStatus();
        }
    }
}
