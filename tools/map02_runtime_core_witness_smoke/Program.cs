// Stage502: release-DLL loader CONTRACT smoke, no emulator or PS1 game.
// Run as its own .NET Framework process in a temporary official BizHawk 2.11
// release tree. Mirrors upstream ExternalToolManager's entrypoint checks.
using System;
using System.IO;
using System.Linq;
using System.Reflection;
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

                AppDomain.CurrentDomain.AssemblyResolve += Resolve;
                _stage = "typed-assembly-load";
                RunSmoke(plug);
                Console.WriteLine(
                    "VH_MAP02_REAL_EXTERNAL_TOOL_LOADER_SMOKE_PASS"
                    + " metadata=1 activation=1 missing_core_fail_closed=1"
                    + " fake_iemulator_positive=1 fake_negative_gates=4"
                    + " in_memory_fake_witness_schema=1"
                    + " official_nullhawk_service_injected=1"
                    + " official_nullhawk_snapshot_rejected=1"
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
                snapshot.Invoke(null, new object[] { invented });
            }
            catch (TargetInvocationException ex)
            {
                if (ex.InnerException is InvalidOperationException) return;
                throw new InvalidOperationException("wrong fake-core rejection");
            }
            throw new InvalidOperationException("invalid fake core exported a witness");
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
                    ((IExternalToolForm)form).Restart();
                    if (saveButtons[0].Enabled)
                        throw new InvalidOperationException(
                            "save must remain disabled without a loaded IEmulator");

                    var snapshot = entrypoint.GetMethod(
                        "Snapshot", BindingFlags.NonPublic | BindingFlags.Static);
                    if (snapshot == null || snapshot.ReturnType != typeof(string))
                        throw new InvalidOperationException("witness snapshot contract missing");

                    _stage = "synthetic-positive-core-injection";
                    var fictional = new SyntheticOctoshock();
                    property.SetValue(form, fictional);
                    ((IExternalToolForm)form).Restart();
                    if (!saveButtons[0].Enabled)
                        throw new InvalidOperationException("valid invented PSX core was rejected");
                    var witness = snapshot.Invoke(null, new object[] { fictional }) as string;
                    // Test schema in memory only. Never print the witness, process
                    // ID/start time, any original SHA1, paths or game data.
                    var rows = witness?.Split('\n');
                    if (rows == null || rows.Length != 11
                        || rows[0] != "VH_MAP02_RUNTIME_CORE_WITNESS_V1"
                        || rows[1] != "system=PSX"
                        || rows[2] != "loaded_core=Octoshock"
                        || rows[3] != "core_source=IEmulator.Attributes.CoreName"
                        || !rows[4].StartsWith("process_id=")
                        || !rows[5].StartsWith("process_start_utc_ticks=")
                        || rows[6] != "frame_count=1666"
                        || rows[7] != "bios=unverified"
                        || rows[8] != "disc=unverified"
                        || rows[9] != "movie_sync=unverified"
                        || rows[10] != "")
                        throw new InvalidOperationException("synthetic witness schema invalid");

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
                            snapshot.Invoke(null, new object[] { genuineNoGameCore });
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

        }
    }
}
