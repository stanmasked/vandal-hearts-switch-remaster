// Stage502: release-DLL loader CONTRACT smoke, no emulator or PS1 game.
// Run as its own .NET Framework process in a temporary official BizHawk 2.11
// release tree. Mirrors upstream ExternalToolManager's entrypoint checks.
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Runtime.CompilerServices;
using System.Windows.Forms;
using BizHawk.Client.Common;
using BizHawk.Emulation.Common;

namespace VhMap02LoaderSmoke
{
    internal static class Program
    {
        private static string _root = "";
        private static string _stage = "initial";

        private static Assembly Resolve(object sender, ResolveEventArgs args)
        {
            var shortName = new AssemblyName(args.Name).Name;
            if (shortName == null || shortName.Contains("/") || shortName.Contains("\\"))
                return null;
            // BizHawk's managed assembly is *named* BizHawk.Client.EmuHawk,
            // but its official on-disk executable is called EmuHawk.exe.
            if (shortName == "BizHawk.Client.EmuHawk")
            {
                var emulatorExe = Path.Combine(_root, "EmuHawk.exe");
                return File.Exists(emulatorExe) ? Assembly.LoadFrom(emulatorExe) : null;
            }
            foreach (var candidate in new[]
            {
                Path.Combine(_root, shortName + ".dll"),
                Path.Combine(_root, "dll", shortName + ".dll"),
                Path.Combine(_root, shortName + ".exe")
            })
                if (File.Exists(candidate)) return Assembly.LoadFrom(candidate);
            return null;
        }

        [STAThread]
        private static int Main(string[] argv)
        {
            try
            {
                if (argv.Length != 2)
                    throw new InvalidOperationException("release root and plugin DLL required");
                _root = Path.GetFullPath(argv[0]);
                var plug = Path.GetFullPath(argv[1]);
                if (!File.Exists(Path.Combine(_root, "EmuHawk.exe"))
                    || !File.Exists(plug)
                    || !File.Exists(Path.Combine(_root, "dll", "BizHawk.Client.Common.dll")))
                    throw new InvalidOperationException("official release or plugin missing");

                Environment.SetEnvironmentVariable("VH_MAP02_CORE_EXPECTED_DLL_SHA256", null);
                AppDomain.CurrentDomain.AssemblyResolve += Resolve;
                _stage = "official-octoshock-disc-mount-metadata";
                AuditOfficialOctoshockDiscMountMetadata();
                _stage = "typed-assembly-load";
                RunSmoke(plug);
                Console.WriteLine(
                    "VH_MAP02_REAL_EXTERNAL_TOOL_LOADER_SMOKE_PASS"
                    + " metadata=1 activation=1 missing_core_fail_closed=1"
                    + " fake_octoshock_impersonation_rejected=1 fake_negative_gates=5"
                    + " exact_runtime_type_gate=1 in_memory_fake_witness_schema=0"
                    + " official_disc_mount_metadata=1"
                    + " synthetic_live_mount_gate=1"
                    + " official_nullhawk_service_injected=1"
                    + " official_nullhawk_snapshot_rejected=1"
                    + " owner_only_ntfs_folder_accepted=1"
                    + " publicly_readable_ntfs_folder_rejected=1"
                    + " synthetic_optin_fake_core_rejected=1"
                    + " emulator_process_started=0 original_disc=0 bios=0 bk2=0");
                return 0;
            }
            catch (TargetInvocationException error)
            {
                var inner = error.InnerException;
                var deeper = (inner as TypeInitializationException)?.InnerException;
                Console.Error.WriteLine(
                    "VH_MAP02_REAL_EXTERNAL_TOOL_LOADER_SMOKE_FAIL stage=" + _stage
                    + " exception_type=TargetInvocationException"
                    + " inner_type=" + (inner == null ? "unknown" : inner.GetType().Name)
                    + " deeper_type=" + (deeper == null ? "none" : deeper.GetType().Name)
                    + " authenticated=0");
                return 1;
            }
            catch (ReflectionTypeLoadException error)
            {
                // Only assembly basenames that satisfy this whitelist can be
                // shown. No exception messages, disk paths, media identifiers.
                var names = error.LoaderExceptions.OfType<FileNotFoundException>()
                    .Select(ex =>
                    {
                        try { return new AssemblyName(ex.FileName).Name; }
                        catch { return ""; }
                    })
                    .Where(name => name != null
                        && name.Length <= 80
                        && name.All(c => char.IsLetterOrDigit(c)
                            || c == '.' || c == '_' || c == '-'))
                    .Distinct().Take(8).ToArray();
                Console.Error.WriteLine(
                    "VH_MAP02_REAL_EXTERNAL_TOOL_LOADER_SMOKE_FAIL stage=" + _stage
                    + " exception_type=ReflectionTypeLoadException"
                    + " unresolved_assembly_names=" + string.Join(",", names)
                    + " authenticated=0");
                return 1;
            }
            catch (Exception error)
            {
                // Print only finite controlled phases and exception TYPE;
                // exception messages and paths can reveal private information.
                Console.Error.WriteLine(
                    "VH_MAP02_REAL_EXTERNAL_TOOL_LOADER_SMOKE_FAIL"
                    + " stage=" + _stage + " exception_type=" + error.GetType().Name
                    + " authenticated=0");
                return 1;
            }
        }

        // Completely fictional IEmulator instances. They never simulate
        // a PlayStation, BIOS, disc, movie input, or a game frame. These are
        // dependency-injection test doubles, not actual core witnesses.
        private abstract class SyntheticEmulator : IEmulator
        {
            public IEmulatorServiceProvider ServiceProvider => null;
            public ControllerDefinition ControllerDefinition => null;
            public bool FrameAdvance(IController controller, bool render, bool renderSound = true)
                => throw new InvalidOperationException("no synthetic frame advancement");
            public virtual int Frame => 1666;
            public virtual string SystemId => "PSX";
            public bool DeterministicEmulation => true;
            public void ResetCounters() {}
            public void Dispose() {}
        }

        [CoreAttribute("Octoshock", "Stage503 invented-only stand-in")]
        private sealed class SyntheticOctoshock : SyntheticEmulator {}

        [CoreAttribute("Nymashock", "Stage503 invented-only stand-in")]
        private sealed class SyntheticNymashock : SyntheticEmulator {}

        [CoreAttribute("Octoshock", "Stage503 invented-only stand-in")]
        private sealed class SyntheticWrongPlatform : SyntheticEmulator
        {
            public override string SystemId => "GEN";
        }

        [CoreAttribute("Octoshock", "Stage503 invented-only stand-in")]
        private sealed class SyntheticNegativeFrame : SyntheticEmulator
        {
            public override int Frame => -1;
        }

        private sealed class SyntheticNoCoreAttribute : SyntheticEmulator {}

        private static void AssertBlocked(
            Form form, PropertyInfo property, MethodInfo snapshot,
            SyntheticEmulator invented)
        {
            property.SetValue(form, invented);
            ((IExternalToolForm)form).Restart();
            var button = form.Controls.OfType<Button>().Single();
            if (button.Enabled)
                throw new InvalidOperationException("unsafe save enabled on invalid fake core");
            try
            {
                snapshot.Invoke(form, new object[] { invented });
            }
            catch (TargetInvocationException ex)
            {
                if (ex.InnerException is InvalidOperationException) return;
                throw new InvalidOperationException("wrong fake-core rejection");
            }
            throw new InvalidOperationException("invalid fake core exported a witness");
        }

        // Two invented output folders: owner-only versus explicit Everyone.
        // The production GUI must reject the latter before FileMode.CreateNew.
        private static void AuditRealWitnessFolderAcl(Type entrypoint)
        {
            var check = entrypoint.GetMethod("RequireNonGitPrivateFolder",
                BindingFlags.NonPublic | BindingFlags.Static);
            if (check == null)
                throw new InvalidOperationException("private folder ACL gate absent");
            var dir = Path.Combine(Path.GetTempPath(),
                "vh-map02-owner-acl-test-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            try
            {
                using (var identity = WindowsIdentity.GetCurrent())
                {
                    var owner = identity.User;
                    if (owner == null)
                        throw new InvalidOperationException("Windows user SID missing");
                    var acl = new DirectorySecurity();
                    acl.SetOwner(owner);
                    acl.SetAccessRuleProtection(true, false);
                    acl.AddAccessRule(new FileSystemAccessRule(
                        owner, FileSystemRights.FullControl,
                        InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
                        PropagationFlags.None, AccessControlType.Allow));
                    Directory.SetAccessControl(dir, acl);
                    check.Invoke(null, new object[] { dir });

                    var everyone = new SecurityIdentifier("S-1-1-0");
                    acl.AddAccessRule(new FileSystemAccessRule(
                        everyone, FileSystemRights.ReadAndExecute,
                        InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
                        PropagationFlags.None, AccessControlType.Allow));
                    Directory.SetAccessControl(dir, acl);
                    var refused = false;
                    try
                    {
                        check.Invoke(null, new object[] { dir });
                    }
                    catch (TargetInvocationException ex)
                    {
                        refused = ex.InnerException is InvalidOperationException;
                    }
                    if (!refused)
                        throw new InvalidOperationException(
                            "private witness folder accepted Everyone NTFS access");
                }
            }
            finally
            {
                // The current owner still has FullControl in this fake test.
                Directory.Delete(dir, recursive: true);
            }
        }


        // Verify the exact public metadata contract consumed by the V5 live
        // mount witness. This loads only the official core assembly metadata:
        // it does not instantiate Octoshock or open a disc, BIOS or movie.
        private static void AuditOfficialOctoshockDiscMountMetadata()
        {
            var coreAssembly = Assembly.Load("BizHawk.Emulation.Cores");
            var coreType = coreAssembly.GetType(
                "BizHawk.Emulation.Cores.Sony.PSX.Octoshock", true);
            var trayOpen = coreType.GetProperty(
                "CurrentTrayOpen", BindingFlags.Public | BindingFlags.Instance);
            var mountedIndex = coreType.GetProperty(
                "CurrentDiscIndexMounted", BindingFlags.Public | BindingFlags.Instance);
            var discs = coreType.GetField(
                "Discs", BindingFlags.Public | BindingFlags.Instance);
            if (trayOpen == null || trayOpen.PropertyType != typeof(bool)
                || mountedIndex == null || mountedIndex.PropertyType != typeof(int)
                || discs == null
                || !typeof(System.Collections.ICollection).IsAssignableFrom(discs.FieldType)
                || !discs.FieldType.IsGenericType)
                throw new InvalidOperationException("official Octoshock disc metadata mismatch");

            var discTypes = discs.FieldType.GetGenericArguments();
            if (discTypes.Length != 1)
                throw new InvalidOperationException("official Octoshock disc collection mismatch");
            var name = discTypes[0].GetField(
                "Name", BindingFlags.Public | BindingFlags.Instance);
            if (name == null || name.FieldType != typeof(string))
                throw new InvalidOperationException("official Disc.Name metadata mismatch");
        }

        private static string FileSha256(string path)
        {
            using (var input = new FileStream(
                path, FileMode.Open, FileAccess.Read, FileShare.Read))
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(input))
                    .Replace("-", "").ToLowerInvariant();
        }

        // An invented Octoshock-named IEmulator must never create a receipt,
        // even when automatic writes are explicitly opted in.
        private static void AuditSyntheticAutomaticWitness(
            Type entrypoint, PropertyInfo property)
        {
            var snapshot = entrypoint.GetMethod(
                "Snapshot", BindingFlags.NonPublic | BindingFlags.Instance);
            if (snapshot == null) throw new InvalidOperationException();
            var key = "VH_MAP02_CORE_AUTOWRITE_PRIVATE_DIR";
            var hashKey = "VH_MAP02_CORE_EXPECTED_DLL_SHA256";
            var prior = Environment.GetEnvironmentVariable(key);
            var priorHash = Environment.GetEnvironmentVariable(hashKey);
            var dir = Path.Combine(Path.GetTempPath(),
                "vh-map02-synthetic-automatic-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            try
            {
                using (var identity = WindowsIdentity.GetCurrent())
                {
                    var owner = identity.User;
                    if (owner == null) throw new InvalidOperationException();
                    var acl = new DirectorySecurity();
                    acl.SetOwner(owner);
                    acl.SetAccessRuleProtection(true, false);
                    acl.AddAccessRule(new FileSystemAccessRule(
                        owner, FileSystemRights.FullControl,
                        InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
                        PropagationFlags.None, AccessControlType.Allow));
                    Directory.SetAccessControl(dir, acl);
                }
                var destination = Path.Combine(dir, "vh-map02-runtime-core-auto.txt");
                Environment.SetEnvironmentVariable(key, null);
                Environment.SetEnvironmentVariable(hashKey, null);
                using (var notOptedIn = (Form)Activator.CreateInstance(entrypoint))
                {
                    property.SetValue(notOptedIn, new SyntheticOctoshock());
                    ((IExternalToolForm)notOptedIn).Restart();
                    if (File.Exists(destination))
                        throw new InvalidOperationException("fake core wrote without opt-in");
                }

                Environment.SetEnvironmentVariable(key, dir);
                using (var optedIn = (Form)Activator.CreateInstance(entrypoint))
                {
                    var fake = new SyntheticOctoshock();
                    property.SetValue(optedIn, fake);
                    ((IExternalToolForm)optedIn).Restart();
                    var button = optedIn.Controls.OfType<Button>().Single();
                    if (button.Enabled || File.Exists(destination))
                        throw new InvalidOperationException("opted-in fake Octoshock was accepted");
                    var rejected = false;
                    try
                    {
                        snapshot.Invoke(optedIn, new object[] { fake });
                    }
                    catch (TargetInvocationException ex)
                    {
                        rejected = ex.InnerException is InvalidOperationException;
                    }
                    if (!rejected)
                        throw new InvalidOperationException("fake Octoshock snapshot was not rejected");
                    ((IExternalToolForm)optedIn).Restart();
                    if (File.Exists(destination))
                        throw new InvalidOperationException("fake witness was written on retry");
                }
            }
            finally
            {
                Environment.SetEnvironmentVariable(key, prior);
                Environment.SetEnvironmentVariable(hashKey, priorHash);
                Directory.Delete(dir, recursive: true);
            }
        }

        // Defer JIT resolution of BizHawk types until AssemblyResolve is hooked.
        [MethodImpl(MethodImplOptions.NoInlining)]
        private static void RunSmoke(string plug)
        {
                var assembly = Assembly.LoadFrom(plug);
                _stage = "assembly-references";
                if (!assembly.GetReferencedAssemblies().Any(
                        name => name.Name != null && name.Name.StartsWith("BizHawk.")))
                    throw new InvalidOperationException("no direct BizHawk reference");

                // Same core matching predicate as upstream 2.11
                // ExternalToolManager.GenerateToolTipFromFileName().
                _stage = "metadata-discovery";
                var candidates = assembly.GetTypes().Where(
                    type => typeof(IExternalToolForm).IsAssignableFrom(type)
                        && type.GetCustomAttributes(typeof(ExternalToolAttribute), true).Any()
                ).ToArray();
                if (candidates.Length != 1 || candidates[0].IsAbstract)
                    throw new InvalidOperationException("not exactly one external entrypoint");
                var entrypoint = candidates[0];
                _stage = "private-ntfs-acl-guard";
                AuditRealWitnessFolderAcl(entrypoint);
                var attribute = entrypoint.GetCustomAttributes(
                    typeof(ExternalToolAttribute), true
                ).Cast<ExternalToolAttribute>().Single();
                if (attribute.Name != "VH MAP02 Core Witness")
                    throw new InvalidOperationException("unexpected external tool name");

                _stage = "injection-property";
                var property = entrypoint.GetProperty("Emulator", BindingFlags.Instance
                    | BindingFlags.Public | BindingFlags.NonPublic);
                if (property == null || property.PropertyType != typeof(IEmulator)
                    || !property.CanWrite
                    || !property.GetCustomAttributes(
                        typeof(RequiredServiceAttribute), true).Any())
                    throw new InvalidOperationException("live IEmulator injection hook missing");

                _stage = "form-activation";
                using (var form = Activator.CreateInstance(entrypoint) as Form)
                {
                    if (form == null || !(form is IExternalToolForm))
                        throw new InvalidOperationException("external form constructor failed");
                    _stage = "uninitialized-control";
                    var saveButtons = form.Controls.OfType<Button>().ToArray();
                    if (saveButtons.Length != 1 || saveButtons[0].Enabled)
                        throw new InvalidOperationException(
                            "witness save must start disabled before core injection");
                    _stage = "null-core-restart";
                    // Keep the pre-injection case explicit: the form must not depend
                    // on a stale or framework-provided emulator reference.
                    property.SetValue(form, null);
                    ((IExternalToolForm)form).Restart();
                    if (saveButtons[0].Enabled)
                        throw new InvalidOperationException(
                            "save must remain disabled without a loaded IEmulator");

                    var snapshot = entrypoint.GetMethod(
                        "Snapshot", BindingFlags.NonPublic | BindingFlags.Instance);
                    if (snapshot == null || snapshot.ReturnType != typeof(string))
                        throw new InvalidOperationException("witness snapshot contract missing");

                    _stage = "synthetic-octoshock-impersonation";
                    AssertBlocked(form, property, snapshot, new SyntheticOctoshock());

                    _stage = "official-nullhawk-service-injection";
                    using (var genuineNoGameCore = new NullEmulator())
                    {
                        // Exercise BizHawk's own ServiceInjector with an actual
                        // official no-media core; this remains outside EmuHawk.
                        if (!ServiceInjector.UpdateServices(
                                genuineNoGameCore.ServiceProvider, form)
                            || !ReferenceEquals(
                                property.GetValue(form), genuineNoGameCore))
                            throw new InvalidOperationException(
                                "official no-media IEmulator service injection rejected");
                        ((IExternalToolForm)form).Restart();
                        var labels = form.Controls.OfType<Label>().ToArray();
                        if (labels.Length != 1
                            || labels[0].Text !=
                                "Injected IEmulator: NullHawk (no game); witness disabled."
                            || saveButtons[0].Enabled)
                            throw new InvalidOperationException(
                                "real NullEmulator does not fail closed with distinct status");
                        var rejected = false;
                        try
                        {
                            snapshot.Invoke(form, new object[] { genuineNoGameCore });
                        }
                        catch (TargetInvocationException ex)
                        {
                            rejected = ex.InnerException is InvalidOperationException;
                        }
                        if (!rejected)
                            throw new InvalidOperationException(
                                "real NullHawk must never export a PSX witness");
                    }

                    _stage = "synthetic-negative-core-gates";
                    AssertBlocked(form, property, snapshot, new SyntheticNymashock());
                    AssertBlocked(form, property, snapshot, new SyntheticWrongPlatform());
                    AssertBlocked(form, property, snapshot, new SyntheticNegativeFrame());
                    AssertBlocked(form, property, snapshot, new SyntheticNoCoreAttribute());
                    property.SetValue(form, null);
                    ((IExternalToolForm)form).Restart();
                    if (saveButtons[0].Enabled)
                        throw new InvalidOperationException("save not disabled after clearing core");
                }
                _stage = "synthetic-optin-fake-core-rejection";
                AuditSyntheticAutomaticWitness(entrypoint, property);
                _stage = "synthetic-official-disc-mount-gate";
                AuditSyntheticMountedDiscGate(entrypoint);

        }

        // Exercise the production V5 mount gate using an uninitialized object
        // of the official Octoshock type and synthetic Disc metadata. No core
        // constructor, frame, disc file, BIOS or movie is opened or executed.
        private static void AuditSyntheticMountedDiscGate(Type entrypoint)
        {
            var coreAssembly = Assembly.Load("BizHawk.Emulation.Cores");
            var coreType = coreAssembly.GetType(
                "BizHawk.Emulation.Cores.Sony.PSX.Octoshock", true);
            var tray = coreType.GetProperty(
                "CurrentTrayOpen", BindingFlags.Public | BindingFlags.Instance);
            var mountedIndex = coreType.GetProperty(
                "CurrentDiscIndexMounted", BindingFlags.Public | BindingFlags.Instance);
            var discsField = coreType.GetField(
                "Discs", BindingFlags.Public | BindingFlags.Instance);
            var nameFieldInfo = discsField?.FieldType.GetGenericArguments().Single()
                .GetField("Name", BindingFlags.Public | BindingFlags.Instance);
            var gate = entrypoint.GetMethod(
                "RequireMountedDiscMatchesSourceCueName",
                BindingFlags.NonPublic | BindingFlags.Instance);
            var autoKeyField = entrypoint.GetField(
                "AutomaticWitnessEnvironment", BindingFlags.NonPublic | BindingFlags.Static);
            var cueKeyField = entrypoint.GetField(
                "ExpectedDiscCueNameEnvironment", BindingFlags.NonPublic | BindingFlags.Static);
            var traySetter = tray?.GetSetMethod(true);
            var indexSetter = mountedIndex?.GetSetMethod(true);
            var autoKey = autoKeyField?.GetRawConstantValue() as string;
            var cueKey = cueKeyField?.GetRawConstantValue() as string;
            if (tray == null || tray.PropertyType != typeof(bool)
                || mountedIndex == null || mountedIndex.PropertyType != typeof(int)
                || discsField == null || !discsField.FieldType.IsGenericType
                || nameFieldInfo == null || nameFieldInfo.FieldType != typeof(string)
                || gate == null || traySetter == null || indexSetter == null
                || string.IsNullOrEmpty(autoKey) || string.IsNullOrEmpty(cueKey))
                throw new InvalidOperationException("official synthetic mount-gate contract missing");

            var priorAuto = Environment.GetEnvironmentVariable(autoKey);
            var priorCue = Environment.GetEnvironmentVariable(cueKey);
            const string expectedName = "vandal-hearts.cue";
            try
            {
                // The output directory is only an opt-in sentinel for this
                // direct helper call; no file write is performed by the gate.
                Environment.SetEnvironmentVariable(autoKey, null);
                Environment.SetEnvironmentVariable(cueKey, expectedName);
                using (var form = Activator.CreateInstance(entrypoint) as Form)
                {
                    if (form == null) throw new InvalidOperationException("mount-gate form unavailable");
                    var core = System.Runtime.Serialization.FormatterServices
                        .GetUninitializedObject(coreType);
                    var disc = System.Runtime.Serialization.FormatterServices
                        .GetUninitializedObject(nameFieldInfo.DeclaringType);
                    nameFieldInfo.SetValue(disc, expectedName);
                    var discs = Activator.CreateInstance(discsField.FieldType)
                        as System.Collections.IList;
                    if (discs == null) throw new InvalidOperationException("synthetic disc list unavailable");
                    discs.Add(disc);
                    discsField.SetValue(core, discs);
                    traySetter.Invoke(core, new object[] { false });
                    indexSetter.Invoke(core, new object[] { 1 });

                    var notOptedIn = gate.Invoke(form, new object[] { core });
                    if (!(notOptedIn is bool) || (bool)notOptedIn)
                        throw new InvalidOperationException("mount gate accepted absent auto opt-in");

                    Environment.SetEnvironmentVariable(autoKey, "synthetic-owner-private-output");
                    var accepted = gate.Invoke(form, new object[] { core });
                    if (!(accepted is bool) || !(bool)accepted)
                        throw new InvalidOperationException("matching synthetic disc mount rejected");

                    nameFieldInfo.SetValue(disc, "other.cue");
                    AssertMountGateRejected(gate, form, core, "wrong-name");
                    nameFieldInfo.SetValue(disc, expectedName);

                    traySetter.Invoke(core, new object[] { true });
                    AssertMountGateRejected(gate, form, core, "tray-open");
                    traySetter.Invoke(core, new object[] { false });

                    indexSetter.Invoke(core, new object[] { 0 });
                    AssertMountGateRejected(gate, form, core, "no-disc-mounted");
                    indexSetter.Invoke(core, new object[] { 1 });

                    discs.Clear();
                    AssertMountGateRejected(gate, form, core, "empty-disc-list");
                    discs.Add(disc);

                    var extra = System.Runtime.Serialization.FormatterServices
                        .GetUninitializedObject(nameFieldInfo.DeclaringType);
                    nameFieldInfo.SetValue(extra, expectedName);
                    discs.Add(extra);
                    AssertMountGateRejected(gate, form, core, "multiple-discs");
                    discs.RemoveAt(1);

                    Environment.SetEnvironmentVariable(cueKey, "folder/vandal-hearts.cue");
                    AssertMountGateRejected(gate, form, core, "cue-name-is-path");
                }
            }
            finally
            {
                Environment.SetEnvironmentVariable(autoKey, priorAuto);
                Environment.SetEnvironmentVariable(cueKey, priorCue);
            }
        }

        private static void AssertMountGateRejected(
            MethodInfo gate, object form, object core, string scenario)
        {
            try
            {
                gate.Invoke(form, new object[] { core });
            }
            catch (TargetInvocationException ex)
            {
                if (ex.InnerException is InvalidOperationException) return;
                throw new InvalidOperationException("synthetic mount gate threw unexpected error");
            }
            throw new InvalidOperationException("synthetic mount gate accepted " + scenario);
        }
    }
}
