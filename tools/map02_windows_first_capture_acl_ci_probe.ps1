# Synthetic Stage513 owner-only/offline first-run acceptance on real NTFS.
# No PlayStation game, BIOS, BK2, private screenshot or user-specific PID.
$ErrorActionPreference = 'Stop'
$base = Join-Path $env:RUNNER_TEMP ('vh-map02-first-audit-ntfs-' + [Guid]::NewGuid().ToString('N'))
$workspace = Join-Path $base 'owner-private'
$first = Join-Path $workspace 'vh-map02-cold-01'
$env:VH_MAP02_FIRST_CAPTURE_WIN_FAKE_ROOT = $base

function Set-OwnerOnlyDacl([string]$path, $owner) {
    $acl = New-Object System.Security.AccessControl.DirectorySecurity
    $acl.SetOwner($owner)
    $acl.SetAccessRuleProtection($true, $false)
    $allow = [System.Security.AccessControl.FileSystemAccessRule]::new(
        $owner, [System.Security.AccessControl.FileSystemRights]::FullControl,
        ([System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
         [System.Security.AccessControl.InheritanceFlags]::ObjectInherit),
        [System.Security.AccessControl.PropagationFlags]::None,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    $acl.AddAccessRule($allow)
    Set-Acl -LiteralPath $path -AclObject $acl
}

try {
    [void][System.IO.Directory]::CreateDirectory($workspace)
    $owner = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    if ($null -eq $owner) { throw 'Windows synthetic fixture owner SID missing' }
    Set-OwnerOnlyDacl $workspace $owner
    [void][System.IO.Directory]::CreateDirectory($first)
    Set-OwnerOnlyDacl $first $owner

    # Assert both real NTFS DACLs *before* invoking Python. The guard prints
    # only a fixed accept marker or exits 1, never local paths or SIDs.
    $guard = Join-Path $PSScriptRoot 'map02_windows_private_output_acl.ps1'
    foreach ($folder in @($workspace, $first)) {
        $check = @( & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $guard -Directory $folder )
        if ($LASTEXITCODE -ne 0 -or @($check).Count -ne 1 -or
            [string]$check -cne 'VH_MAP02_OWNER_PRIVATE_NTFS_ACL_OK') {
            throw 'direct real NTFS guard rejected a synthetic owner-only directory'
        }
    }

    $utf8 = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText((Join-Path $base 'fake-movie.bk2'),
        'FICTIONAL_NO_GAME_MOVIE', $utf8)
    [System.IO.File]::WriteAllText((Join-Path $workspace 'vh-map02-review-plan.txt'),
        'FICTIONAL_NO_GAME_PLAN', $utf8)

    $process = "VH_MAP02_OWNER_EMUHAWK_PROCESS_START_V1`nprocess_id=4041`nprocess_start_utc_ticks=639000000000000123`n"
    [System.IO.File]::WriteAllText((Join-Path $first 'vh_emuhawk_process_identity.txt'),
        $process, $utf8)
    $witness = "VH_MAP02_RUNTIME_CORE_WITNESS_V1`nsystem=PSX`nloaded_core=Octoshock`ncore_source=IEmulator.Attributes.CoreName`nprocess_id=4041`nprocess_start_utc_ticks=639000000000000123`nframe_count=1800`nbios=unverified`ndisc=unverified`nmovie_sync=unverified`n"
    [System.IO.File]::WriteAllText((Join-Path $first 'vh-map02-runtime-core-auto.txt'),
        $witness, $utf8)

    python tests/map02_windows_first_capture_acl_probe.py owner
    if ($LASTEXITCODE -ne 0) { throw 'owner-only Windows first-capture read-only audit rejected' }

    $acl = Get-Acl -LiteralPath $workspace
    $everyone = [System.Security.Principal.SecurityIdentifier]::new('S-1-1-0')
    $acl.AddAccessRule(
        ([System.Security.AccessControl.FileSystemAccessRule]::new(
            $everyone, [System.Security.AccessControl.FileSystemRights]::ReadAndExecute,
            ([System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
             [System.Security.AccessControl.InheritanceFlags]::ObjectInherit),
            [System.Security.AccessControl.PropagationFlags]::None,
            [System.Security.AccessControl.AccessControlType]::Allow
        ))
    )
    Set-Acl -LiteralPath $workspace -AclObject $acl
    python tests/map02_windows_first_capture_acl_probe.py everyone
    if ($LASTEXITCODE -ne 0) { throw 'Everyone-readable Windows first-capture directory was not rejected' }

    Write-Output 'VH_MAP02_WINDOWS_FIRST_CAPTURE_REAL_NTFS_FAKE_PASS owner_only=accepted everyone=denied real_psx=0 original_bk2=0 screenshot=0'
} finally {
    Remove-Item -LiteralPath $base -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item Env:VH_MAP02_FIRST_CAPTURE_WIN_FAKE_ROOT -ErrorAction SilentlyContinue
}
