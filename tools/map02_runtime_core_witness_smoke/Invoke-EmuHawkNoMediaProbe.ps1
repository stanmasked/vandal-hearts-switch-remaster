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

    private static string Title(IntPtr hwnd) {
        var text = new StringBuilder(320);
        GetWindowText(hwnd, text, text.Capacity);
        return text.ToString();
    }

    // Bounded aggregate, never a process ID, handle, private path or title.
    // 0=all top-level process windows, 1=visible, 2=matching tool windows,
    // 3=matching Save buttons, 4=matching disabled Save buttons.
    public static int[] Probe(int processId) {
        var counts = new int[5];
        EnumWindows((window, param) => {
            uint owner;
            GetWindowThreadProcessId(window, out owner);
            if (owner != (uint)processId) return true;
            counts[0]++;
            if (IsWindowVisible(window)) counts[1]++;
            if (!IsWindowVisible(window)
                || Title(window) != "VH MAP02 PSX core witness") return true;
            counts[2]++;
            EnumChildWindows(window, (child, arg) => {
                var classname = new StringBuilder(40);
                GetClassName(child, classname, classname.Capacity);
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
# Only the registered external-tool filename is passed to the real host.
$hosted = Start-Process -FilePath $emulator -WorkingDirectory $root `
    -ArgumentList @('--open-ext-tool-dll', 'VhMap02CoreWitness.dll') -PassThru
try {
    $observed = $false
    $diagnostic = @(0, 0, 0, 0, 0)
    for ($i=0; $i -lt 50; $i++) {
        $hosted.Refresh()
        if ($hosted.HasExited) { throw 'no-media EmuHawk exited before tool appeared' }
        $diagnostic = [VhNoMediaWindows]::Probe($hosted.Id)
        if ($diagnostic[2] -eq 1 -and $diagnostic[3] -eq 1 -and $diagnostic[4] -eq 1) {
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
        $status = @(
            "VH_MAP02_REAL_EMUHAWK_NOMEDIA_DIAGNOSTIC"
            "same_windows_session=$sameSession"
            "process_window_found=$hasWindow"
            "visible_process_window_found=$hasVisibleWindow"
            "plugin_window_found=$hasTool"
            "save_button_found=$hasButton"
            "disabled_save_found=$hasDisabledButton"
            "real_octoshock_authenticated=0"
        ) -join ' '
        Write-Output $status
        throw 'no-media EmuHawk tool window was not witnessed'
    }

    Write-Output 'VH_MAP02_REAL_EMUHAWK_NOMEDIA_PLUGIN_UI_PASS genuine_process=1 actual_tool_window=1 save_disabled_no_psx=1 rom=0 bios=0 bk2=0 png=0 active_octoshock=unverified'
} finally {
    try {
        if (-not $hosted.HasExited) {
            Stop-Process -Id $hosted.Id -Force -ErrorAction Stop
        }
    } catch {
        # A dead emulator cannot expose private source bytes in this job.
    }
    $hosted.Dispose()
}
