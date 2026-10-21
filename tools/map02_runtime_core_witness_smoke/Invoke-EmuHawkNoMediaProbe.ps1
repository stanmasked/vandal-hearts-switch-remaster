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

    public static bool HasDisabledWitnessWindow(int processId) {
        bool matched = false;
        EnumWindows((window, param) => {
            uint owner;
            GetWindowThreadProcessId(window, out owner);
            if (owner != (uint)processId || !IsWindowVisible(window)
                || Title(window) != "VH MAP02 PSX core witness") return true;

            int saveCount = 0;
            int disabledSaveCount = 0;
            EnumChildWindows(window, (child, arg) => {
                var classname = new StringBuilder(40);
                GetClassName(child, classname, classname.Capacity);
                if (classname.ToString() == "WindowsForms10.BUTTON.app.0"
                    || classname.ToString().StartsWith("WindowsForms10.BUTTON.")
                    || classname.ToString() == "Button") {
                    if (Title(child) == "Write private core witness...") {
                        saveCount++;
                        if (!IsWindowEnabled(child)) disabledSaveCount++;
                    }
                }
                return true;
            }, IntPtr.Zero);
            if (saveCount == 1 && disabledSaveCount == 1) matched = true;
            return true;
        }, IntPtr.Zero);
        return matched;
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
    for ($i=0; $i -lt 90; $i++) {
        $hosted.Refresh()
        if ($hosted.HasExited) { throw 'no-media EmuHawk exited before tool appeared' }
        if ([VhNoMediaWindows]::HasDisabledWitnessWindow($hosted.Id)) {
            $observed = $true
            break
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $observed) { throw 'no-media EmuHawk tool window was not witnessed' }

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
