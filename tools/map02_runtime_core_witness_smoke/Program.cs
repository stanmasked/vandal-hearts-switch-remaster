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
                    + " emulator_process_started=0 original_disc=0 bios=0 bk2=0");
                return 0;
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
                    _stage = "null-core-restart";
                    ((IExternalToolForm)form).Restart();
                    _stage = "disabled-save-control";
                    var saveButtons = form.Controls.OfType<Button>().ToArray();
                    if (saveButtons.Length != 1 || saveButtons[0].Enabled)
                        throw new InvalidOperationException(
                            "save must be disabled without injected real PSX IEmulator");
                }

        }
    }
}
