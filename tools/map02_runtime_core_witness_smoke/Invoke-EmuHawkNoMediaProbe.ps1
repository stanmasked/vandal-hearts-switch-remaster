# Stage504: official BizHawk 2.11 GUI-process smoke, with ZERO game/BIOS/BK2.
# This invokes the real EmuHawk.exe and inspects only an exact plugin window
# title + disabled Save button belonging to that same emulator PID.
# It never clicks Save or creates/discloses gameplay evidence.
param(
  [Parameter(Mandatory=$true)][string]$BizHawkRoot,
  [Parameter(Mandatory=$true)][string]$PluginFile
)
$ErrorActionPreference = 'Stop'

Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
using System.Collections.Generic;
public static class VhNoMediaWindows {
    private delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr param);
    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumWindowsProc cb, IntPtr p);
    [DllImport("user32.dll")] private static extern bool EnumChildWindows(IntPtr parent, EnumWindowsProc cb, IntPtr p);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint id);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int cap);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern int GetClassName(IntPtr hwnd, StringBuilder name, int cap);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsWindowEnabled(IntPtr hwnd);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern IntPtr GetDlgItem(IntPtr hwnd, int id);
    [DllImport("user32.dll")] private static extern IntPtr SendMessage(IntPtr hwnd, uint msg, IntPtr w, IntPtr l);

    private static string Title(IntPtr hwnd) {
        var text = new StringBuilder(320);
        GetWindowText(hwnd, text, text.Capacity);
        return text.ToString();
    }

    // Classify only the process-owned native modal on a game-free,
    // short-lived public CI runner. Never reveal arbitrary message text,
    // paths, account names, hashes, resource IDs or private media.
    public static string ClassifyVisibleNativeModal(int pid) {
        string result = "none";
        EnumWindows((window, param) => {
            uint owner;
            GetWindowThreadProcessId(window, out owner);
            if (owner != (uint)pid || !IsWindowVisible(window)) return true;
            var cls = new StringBuilder(40);
            GetClassName(window, cls, cls.Capacity);
            if (cls.ToString() != "#32770") return true;
            string label = Title(window);
            if (label.Length > 0 && label.Length <= 65) {
                bool basic = true;
                foreach (char c in label) {
                    if (!(char.IsLetterOrDigit(c) || c == ' ' || c == '.' || c == '!' || c == '?'
                        || c == '-' || c == '(' || c == ')')) { basic = false; break; }
                }
                if (basic) result = label.Replace(' ', '_');
                else result = "unsafe_caption_redacted";
            } else result = "empty_or_long_caption";
            return false;
        }, IntPtr.Zero);
        return result;
    }

    // Approve only the exact trust dialog for the experimental DLL
    // freshly compiled from this PR against a SHA256-pinned BizHawk release.
    // No general dialogs, warning prompts, or other EXEs are confirmed.
    public static bool ApproveOnlyKnownToolTrustPrompt(int pid) {
        bool approved = false;
        EnumWindows((window, param) => {
            uint owner;
            GetWindowThreadProcessId(window, out owner);
            if (owner != (uint)pid || !IsWindowVisible(window)
                || Title(window) != "Confirm loading") return true;
            var classname = new StringBuilder(40);
            GetClassName(window, classname, classname.Capacity);
            if (classname.ToString() != "#32770") return true;
            bool expectedText = false;
            EnumChildWindows(window, (child, arg) => {
                var text = Title(child);
                if (text.Contains("Are you sure want to load this external tool?")
                    && text.Contains("Accept ONLY if you trust the source"))
                    expectedText = true;
                return true;
            }, IntPtr.Zero);
            if (!expectedText) return true;
            var yes = GetDlgItem(window, 6); // MessageBox IDYES
            if (yes == IntPtr.Zero) return true;
            var label = Title(yes);
            if (label != "&Yes" && label != "Yes") return true;
            SendMessage(yes, 0xF5U, IntPtr.Zero, IntPtr.Zero); // BM_CLICK
            approved = true;
            return false;
        }, IntPtr.Zero);
        return approved;
    }

    // Bounded aggregate, never a process ID, handle, private path or title.
    // 0=all top-level process windows, 1=visible, 2=matching tool windows,
    // 3=matching Save buttons, 4=matching disabled Save buttons,
    // 5=visible, process-owned first-load trust dialogs,
    // 6=exact "BizHawk" main title, 7=any visible native modal,
    // 8=exact post-ToolManager injection status for real NullEmulator.
    public static int[] Probe(int processId) {
        var counts = new int[9];
        EnumWindows((window, param) => {
            uint owner;
            GetWindowThreadProcessId(window, out owner);
            if (owner != (uint)processId) return true;
            counts[0]++;
            if (IsWindowVisible(window)) counts[1]++;
            if (IsWindowVisible(window) && Title(window) == "Confirm loading") counts[5]++;
            if (IsWindowVisible(window) && Title(window) == "BizHawk") counts[6]++;
            var cls = new StringBuilder(40);
            GetClassName(window, cls, cls.Capacity);
            if (IsWindowVisible(window) && cls.ToString() == "#32770") counts[7]++;
            if (!IsWindowVisible(window)
                || Title(window) != "VH MAP02 PSX core witness") return true;
            counts[2]++;
            EnumChildWindows(window, (child, arg) => {
                var classname = new StringBuilder(40);
                GetClassName(child, classname, classname.Capacity);
                if ((classname.ToString().StartsWith("WindowsForms10.STATIC.")
                     || classname.ToString() == "Static")
                    && Title(child) == "Injected IEmulator: NullHawk (no game); witness disabled.")
                    counts[8]++;
                if (classname.ToString().StartsWith("WindowsForms10.BUTTON.")
                    || classname.ToString() == "Button") {
                    if (Title(child) == "Write private core witness...") {
                        counts[3]++;
                        if (!IsWindowEnabled(child)) counts[4]++;
                    }
                }
                return true;
            }, IntPtr.Zero);
            return true;
        }, IntPtr.Zero);
        return counts;
    }
}
'@ -ReferencedAssemblies @('System.dll')

$root = [System.IO.Path]::GetFullPath($BizHawkRoot)
$emulator = Join-Path $root 'EmuHawk.exe'
$plugin = Join-Path $root 'ExternalTools/VhMap02CoreWitness.dll'
if (-not (Test-Path -LiteralPath $emulator -PathType Leaf) -or
    -not (Test-Path -LiteralPath $plugin -PathType Leaf)) {
    throw 'emulator executable or experimental external tool missing'
}
if ([System.IO.Path]::GetFullPath($PluginFile) -cne [System.IO.Path]::GetFullPath($plugin)) {
    throw 'loaded experimental DLL must be the verified release-root copy'
}

# Hardcoded no-media CLI: there is no --movie, --lua or disc argument.
# Fresh Windows CI runners have no usable sound hardware. Upstream
# MainForm displays a modal "Initialization Error" if the configured
# sound driver fails, blocking the external-tool startup hook. Supply
# only a disposable, synthetic CI config with SoundOutputMethod=Dummy.
# --gdi avoids unrelated GPU backend assumptions in no-game tests.
$ciConfig = Join-Path $env:RUNNER_TEMP 'vh-map02-only-nomedia-bizhawk211.json'
$settings = '{"LastWrittenFrom":"2.11","SoundOutputMethod":3}'
[System.IO.File]::WriteAllText($ciConfig, $settings, [System.Text.Encoding]::UTF8)
$stdout = Join-Path $env:RUNNER_TEMP 'vh-map02-gameless-emuhawk-output.txt'
$stderr = Join-Path $env:RUNNER_TEMP 'vh-map02-gameless-emuhawk-error.txt'
$hosted = Start-Process -FilePath $emulator -WorkingDirectory $root `
    -ArgumentList @("--config=$ciConfig", '--gdi',
        '--open-ext-tool-dll=VhMap02CoreWitness.dll') `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
try {
    $observed = $false
    $diagnostic = @(0, 0, 0, 0, 0, 0, 0, 0, 0)
    $ownPromptApproved = $false
    for ($i=0; $i -lt 60; $i++) {
        $hosted.Refresh()
        if ($hosted.HasExited) { throw 'no-media EmuHawk exited before tool appeared' }
        if (-not $ownPromptApproved) {
            $ownPromptApproved = [VhNoMediaWindows]::ApproveOnlyKnownToolTrustPrompt($hosted.Id)
        }
        $diagnostic = [VhNoMediaWindows]::Probe($hosted.Id)
        if ($diagnostic[2] -eq 1 -and $diagnostic[3] -eq 1
            -and $diagnostic[4] -eq 1 -and $diagnostic[8] -eq 1) {
            $observed = $true
            break
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $observed) {
        # These are simple bounded booleans only. Do not print PID,
        # window captions, stack traces, installation or media paths.
        $sameSession = [int]($hosted.SessionId -eq [System.Diagnostics.Process]::GetCurrentProcess().SessionId)
        $hasWindow = [int]($diagnostic[0] -gt 0)
        $hasVisibleWindow = [int]($diagnostic[1] -gt 0)
        $hasTool = [int]($diagnostic[2] -gt 0)
        $hasButton = [int]($diagnostic[3] -gt 0)
        $hasDisabledButton = [int]($diagnostic[4] -gt 0)
        $hasTrustPrompt = [int]($diagnostic[5] -gt 0)
        $hasMainWindow = [int]($diagnostic[6] -gt 0)
        $hasNativeModal = [int]($diagnostic[7] -gt 0)
        $nativeModalCaptionClass = [VhNoMediaWindows]::ClassifyVisibleNativeModal($hosted.Id)
        $injectedNullHawk = [int]($diagnostic[8] -eq 1)
        $status = @(
            "VH_MAP02_REAL_EMUHAWK_NOMEDIA_DIAGNOSTIC"
            "same_windows_session=$sameSession"
            "process_window_found=$hasWindow"
            "visible_process_window_found=$hasVisibleWindow"
            "plugin_window_found=$hasTool"
            "save_button_found=$hasButton"
            "disabled_save_found=$hasDisabledButton"
            "injected_nullhawk_label_observed=$injectedNullHawk"
            "tool_trust_prompt_seen=$hasTrustPrompt"
            "bizhawk_main_window_seen=$hasMainWindow"
            "native_modal_dialog_seen=$hasNativeModal"
            "native_modal_caption_class=$nativeModalCaptionClass"
            "own_tool_trust_confirmed=$([int]$ownPromptApproved)"
            "real_octoshock_authenticated=0"
        ) -join ' '
        Write-Output $status
        throw 'no-media EmuHawk tool window was not witnessed'
    }

    Write-Output 'VH_MAP02_REAL_EMUHAWK_NOMEDIA_PLUGIN_UI_PASS genuine_process=1 actual_tool_window=1 injected_nullhawk_service_observed=1 save_disabled_no_psx=1 rom=0 bios=0 bk2=0 png=0 active_octoshock=unverified'
} finally {
    try {
        if (-not $hosted.HasExited) {
            Stop-Process -Id $hosted.Id -Force -ErrorAction Stop
        }
    } catch {
        # A dead emulator cannot expose private source bytes in this job.
    }
    try {
        # Never print raw console output: it may include temporary paths.
        # Expose only a few fixed boolean classifications of the CLI result.
        $out = if (Test-Path -LiteralPath $stdout) {
            Get-Content -LiteralPath $stdout -Raw -ErrorAction SilentlyContinue
        } else { '' }
        $err = if (Test-Path -LiteralPath $stderr) {
            Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue
        } else { '' }
        $missingMenuItem = [int]("$out".Contains(
            'requested ext. tool dll VhMap02CoreWitness.dll could not be loaded'))
        $skippedAssembly = [int]("$out".Contains('ignoring <exttools>/'))
        $fatalStartup = [int]("$err".Contains('FATAL EXCEPTION'))
        Write-Output "VH_MAP02_EMUHAWK_CLI_SANITIZED_DIAGNOSTIC tool_not_available=$missingMenuItem ignored_tool_assembly=$skippedAssembly fatal_startup=$fatalStartup"
    } catch {
        Write-Output 'VH_MAP02_EMUHAWK_CLI_SANITIZED_DIAGNOSTIC unavailable=1'
    } finally {
        Remove-Item -LiteralPath $stdout, $stderr, $ciConfig -Force -ErrorAction SilentlyContinue
        $hosted.Dispose()
    }
}
