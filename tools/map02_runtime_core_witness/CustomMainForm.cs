// Optional owner-local BizHawk 2.11 External Tool, NOT part of public CI.
// Build inside a private BizHawk source checkout with the .csproj alongside.
// This observes the *loaded* IEmulator, unlike client.getconfig() which
// observes only PreferredCores; no BIOS, disc or movie is inspected.
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
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
                Text = "Write private core witness..."
            };
            _save.Click += SaveWitness;
            Controls.Add(_summary);
            Controls.Add(_save);
        }

        // EmuHawk injects RequiredService after constructor. Restart is also
        // called after a new movie session starts; do not cache the core.
        public override void Restart() => RefreshStatus();

        private void RefreshStatus()
        {
            var core = Emulator;
            if (core == null || core.SystemId != "PSX")
            {
                _summary.Text = "No loaded PSX core; capture disabled.";
                _save.Enabled = false;
                return;
            }
            var loadedName = core.Attributes().CoreName;
            if (loadedName != "Octoshock")
            {
                _summary.Text = "Actual loaded PSX core is not Octoshock.";
                _save.Enabled = false;
                return;
            }
            _summary.Text = "Loaded IEmulator reports PSX / Octoshock."
                + Environment.NewLine
                + "BIOS, disc image and BK2 replay are NOT verified.";
            _save.Enabled = true;
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
        }

        private static string Snapshot(IEmulator actualCore)
        {
            // A recorded BK2 Core header or configured preferred core is NOT
            // accepted as the identity: sample the currently injected core.
            if (actualCore == null || actualCore.SystemId != "PSX"
                || actualCore.Attributes().CoreName != "Octoshock"
                || actualCore.Frame < 0) throw new InvalidOperationException();

            using (var process = Process.GetCurrentProcess())
            {
                var start = process.StartTime.ToUniversalTime().Ticks;
                if (process.Id <= 0 || start <= 0) throw new InvalidOperationException();
                return "VH_MAP02_RUNTIME_CORE_WITNESS_V1\n"
                    + "system=PSX\n"
                    + "loaded_core=Octoshock\n"
                    + "core_source=IEmulator.Attributes.CoreName\n"
                    + "process_id=" + process.Id + "\n"
                    + "process_start_utc_ticks=" + start + "\n"
                    + "frame_count=" + actualCore.Frame + "\n"
                    + "bios=unverified\n"
                    + "disc=unverified\n"
                    + "movie_sync=unverified\n";
            }
        }

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
                    using (var writer = new StreamWriter(
                        output, new UTF8Encoding(false)))
                    {
                        writer.Write(payload);
                        writer.Flush();
                        output.Flush(true);
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
