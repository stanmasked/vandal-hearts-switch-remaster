# Stage506: invented Windows NTFS directories only, no PS1/BK2/BIOS.
# Tests the *real* PowerShell access-control guard, not localized icacls text.
$ErrorActionPreference = 'Stop'
$base = Join-Path $env:RUNNER_TEMP ('vh-map02-private-acl-fixture-' + [Guid]::NewGuid().ToString('N'))
$private = Join-Path $base 'owner-private'
$public = Join-Path $base 'world-readable'
try {
    [void][System.IO.Directory]::CreateDirectory($private)
    [void][System.IO.Directory]::CreateDirectory($public)
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    if ($null -eq $user) { throw 'Windows user SID unavailable' }
    $acl = New-Object System.Security.AccessControl.DirectorySecurity
    $acl.SetOwner($user)
    $acl.SetAccessRuleProtection($true, $false)
    $acl.AddAccessRule(
        (New-Object System.Security.AccessControl.FileSystemAccessRule(
            $user,
            [System.Security.AccessControl.FileSystemRights]::FullControl,
            ([System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
                [System.Security.AccessControl.InheritanceFlags]::ObjectInherit),
            [System.Security.AccessControl.PropagationFlags]::None,
            [System.Security.AccessControl.AccessControlType]::Allow
        ))
    )
    Set-Acl -LiteralPath $private -AclObject $acl
    Set-Acl -LiteralPath $public -AclObject $acl

    $guard = Join-Path $PSScriptRoot 'map02_windows_private_output_acl.ps1'
    $ok = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $guard -Directory $private
    if ($LASTEXITCODE -ne 0 -or @($ok).Count -ne 1 -or [string]$ok -cne
        'VH_MAP02_OWNER_PRIVATE_NTFS_ACL_OK') {
        throw 'owner-only directory was not accepted by genuine NTFS guard'
    }

    $badAcl = Get-Acl -LiteralPath $public
    $badAcl.AddAccessRule(
        (New-Object System.Security.AccessControl.FileSystemAccessRule(
            (New-Object System.Security.Principal.SecurityIdentifier('S-1-1-0')),
            [System.Security.AccessControl.FileSystemRights]::ReadAndExecute,
            ([System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
                [System.Security.AccessControl.InheritanceFlags]::ObjectInherit),
            [System.Security.AccessControl.PropagationFlags]::None,
            [System.Security.AccessControl.AccessControlType]::Allow
        ))
    )
    Set-Acl -LiteralPath $public -AclObject $badAcl
    $unexpected = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $guard -Directory $public
    if ($LASTEXITCODE -eq 0 -or @($unexpected).Count -gt 0) {
        throw 'Everyone-readable Windows capture directory was accepted'
    }
    Write-Output 'VH_MAP02_WINDOWS_OUTPUT_ACL_REAL_FIXTURE_PASS private=accepted everyone=denied media=0'
} finally {
    Remove-Item -LiteralPath $base -Recurse -Force -ErrorAction SilentlyContinue
}
