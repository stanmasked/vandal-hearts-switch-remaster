# Stage516: install ONLY an explicitly pinned local experimental BizHawk 2.11
# witness DLL. Windows PowerShell 5.1, no original game, BIOS, BK2 or PNG.
# Without -Install this is a no-write preflight. Never expose paths or hashes.
param(
    [Parameter(Mandatory=$true)][string]$BizHawkRoot,
    [Parameter(Mandatory=$true)][string]$SourceDll,
    [Parameter(Mandatory=$true)][string]$ExpectedDllSha256,
    [switch]$Install
)
$ErrorActionPreference = 'Stop'
$madeDirectory = $false
$madeFile = $false
$external = $null
$target = $null
try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'Windows only'
    }
    if ($ExpectedDllSha256 -cnotmatch '\A[a-fA-F0-9]{64}\z') {
        throw 'expected SHA256 is missing or malformed'
    }
    $expected = $ExpectedDllSha256.ToLowerInvariant()
    foreach ($name in @($BizHawkRoot, $SourceDll)) {
        if (-not [System.IO.Path]::IsPathRooted($name) -or
            $name.StartsWith('\\')) {
            throw 'absolute local filesystem path required'
        }
    }
    $root = [System.IO.Path]::GetFullPath($BizHawkRoot)
    $source = [System.IO.Path]::GetFullPath($SourceDll)
    if (-not [System.IO.Directory]::Exists($root) -or
        -not [System.IO.File]::Exists($source)) {
        throw 'private local installation inputs unavailable'
    }
    if ([System.IO.Path]::GetFileName($source) -cne 'VhMap02CoreWitness.dll') {
        throw 'experimental DLL filename mismatch'
    }
    # Reject reparse points and every ancestor .git marker, for BOTH inputs.
    # Do not follow junctions into a Git checkout or a shared image folder.
    foreach ($start in @($root, $source)) {
        $candidate = if ([System.IO.Directory]::Exists($start)) {
            [System.IO.DirectoryInfo]::new($start)
        } else {
            [System.IO.FileInfo]::new($start)
        }
        for ($cur = $candidate; $null -ne $cur; $cur = $cur.Parent) {
            if (($cur.Attributes -band
                [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'reparse-point path rejected'
            }
            if ($cur -is [System.IO.DirectoryInfo]) {
                $git = [System.IO.Path]::Combine($cur.FullName, '.git')
                if ([System.IO.File]::Exists($git) -or
                    [System.IO.Directory]::Exists($git)) {
                    throw 'installation paths must remain outside Git'
                }
            }
        }
    }
    # An expected official 2.11 installation has these exact assembly names.
    # This layout is not proof that the owner obtained the official release:
    # check the original 2.11 archive SHA256 separately before extracting it.
    foreach ($required in @(
        'EmuHawk.exe',
        'dll\BizHawk.Client.Common.dll',
        'dll\BizHawk.Emulation.Common.dll'
    )) {
        if (-not [System.IO.File]::Exists(
            [System.IO.Path]::Combine($root, $required))) {
            throw 'BizHawk executable or expected assemblies missing'
        }
    }
    $assemblyName = [System.Reflection.AssemblyName]::GetAssemblyName($source)
    if ($assemblyName.Name -cne 'VhMap02CoreWitness') {
        throw 'experimental DLL assembly identity mismatch'
    }
    $file = [System.IO.FileInfo]::new($source)
    if ($file.Length -le 0 -or $file.Length -gt 16777216) {
        throw 'unexpected experimental DLL size'
    }
    $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    if ($sourceHash.ToLowerInvariant() -cne $expected) {
        throw 'experimental DLL does not match owner-specified digest'
    }
    $external = [System.IO.Path]::Combine($root, 'ExternalTools')
    $target = [System.IO.Path]::Combine($external, 'VhMap02CoreWitness.dll')
    if ([System.IO.File]::Exists($external)) {
        throw 'ExternalTools is not a directory'
    }
    if ([System.IO.Directory]::Exists($external)) {
        if (([System.IO.DirectoryInfo]::new($external).Attributes -band
            [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'external tool directory cannot be a reparse point'
        }
    }
    if ([System.IO.File]::Exists($target) -or
        [System.IO.Directory]::Exists($target) -or
        (Test-Path -LiteralPath $target -ErrorAction SilentlyContinue)) {
        throw 'never replace an existing external tool'
    }
    if (-not $Install) {
        Write-Output 'VH_MAP02_OWNER_BIZHAWK_PLUGIN_PREFLIGHT_OK installed=0 media=0'
        exit 0
    }
    if (-not [System.IO.Directory]::Exists($external)) {
        [void][System.IO.Directory]::CreateDirectory($external)
        $madeDirectory = $true
    }
    # Open with CreateNew. A race cannot overwrite a previously installed DLL.
    $output = [System.IO.FileStream]::new(
        $target, [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    $madeFile = $true
    try {
        $inputFile = [System.IO.FileStream]::new(
            $source, [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
        try { $inputFile.CopyTo($output); $output.Flush($true) }
        finally { $inputFile.Dispose() }
    } finally { $output.Dispose() }
    # Verify both the bytes actually placed on disk and source stability.
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expected -or
        (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expected) {
        throw 'post-install SHA256 mismatch'
    }
    Write-Output 'VH_MAP02_OWNER_BIZHAWK_PLUGIN_INSTALLED_OK create_new=1 sha256_checked=1 media=0'
    exit 0
} catch {
    # Remove ONLY the freshly created file. No backups, recursive deletion or
    # changes to any existing emulator, plugin, game, config, firmware or BK2.
    if ($madeFile -and $null -ne $target) {
        try { [System.IO.File]::Delete($target) } catch {}
    }
    if ($madeDirectory -and $null -ne $external) {
        try { [System.IO.Directory]::Delete($external, $false) } catch {}
    }
    Write-Output 'VH_MAP02_OWNER_BIZHAWK_PLUGIN_INSTALL_REJECTED media=0'
    exit 1
}
