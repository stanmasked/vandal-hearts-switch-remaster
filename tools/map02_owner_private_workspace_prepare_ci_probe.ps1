# Executed on real Windows NTFS with invented empty folders only.
# All output fixed and redacted; no owner data, original game or BK2 involved.
$ErrorActionPreference = 'Stop'
$base = Join-Path $env:RUNNER_TEMP ('vh-map02-ws515-fictional-' + [Guid]::NewGuid().ToString('N'))
$parent = Join-Path $base 'sandbox-parent'
$prepared = Join-Path $parent 'new-owner-workspace'
$gitRoot = Join-Path $parent 'fake-git-repo'
$prepare = Join-Path $PSScriptRoot 'map02_owner_private_workspace_prepare.ps1'
$guard = Join-Path $PSScriptRoot 'map02_windows_private_output_acl.ps1'

function Invoke-Preparation([string]$Target, [bool]$Create) {
    $arguments = @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                   '-File', $prepare, '-Workspace', $Target)
    if ($Create) { $arguments += '-Create' }
    $lines = @( & powershell.exe @arguments )
    return @{
        rc = $LASTEXITCODE
        lines = @($lines)
    }
}
function Assert-Result($Actual, [int]$Code, [string]$Message) {
    if ($Actual.rc -ne $Code -or @($Actual.lines).Count -ne 1 -or
        [string]$Actual.lines[0] -cne $Message) {
        throw 'synthetic workspace bootstrap exit/marker contract failed'
    }
}

try {
    [void][System.IO.Directory]::CreateDirectory($parent)
    $dry = Invoke-Preparation $prepared $false
    Assert-Result $dry 0 'VH_MAP02_OWNER_PRIVATE_WORKSPACE_PREFLIGHT_OK created=0 original_media=0'
    if (Test-Path -LiteralPath $prepared) { throw 'dry-run created a directory' }

    $created = Invoke-Preparation $prepared $true
    Assert-Result $created 0 'VH_MAP02_OWNER_PRIVATE_WORKSPACE_READY created=1 acl=owner_only original_media=0'
    if (-not [System.IO.Directory]::Exists($prepared)) {
        throw 'expected protected directory was not created'
    }
    $ok = @( & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $guard -Directory $prepared )
    if ($LASTEXITCODE -ne 0 -or @($ok).Count -ne 1 -or
        [string]$ok -cne 'VH_MAP02_OWNER_PRIVATE_NTFS_ACL_OK') {
        throw 'new private workspace was not accepted by strict NTFS guard'
    }
    # Check the Python subprocess path on Windows as a second independent
    # invocation route. This was fixed at Stage514, not mocked.
    python -c "from pathlib import Path; from tools.map02_windows_private_output_acl import require_windows_private_output; import sys; require_windows_private_output(Path(sys.argv[1]))" $prepared
    if ($LASTEXITCODE -ne 0) { throw 'Python strict NTFS check rejected new folder' }

    # Never overwrite pre-existing private files or modify their ACL.
    $sentinel = Join-Path $prepared 'synthetic-owner-sentinel.txt'
    [System.IO.File]::WriteAllText($sentinel, 'fiction-only')
    $second = Invoke-Preparation $prepared $true
    Assert-Result $second 1 'VH_MAP02_OWNER_PRIVATE_WORKSPACE_REJECTED created_or_acl_unverified=1'
    if ([System.IO.File]::ReadAllText($sentinel) -cne 'fiction-only') {
        throw 'existing owner fixture was overwritten'
    }

    # Explicit rejection of a fake Git checkout, never put captures there.
    [void][System.IO.Directory]::CreateDirectory($gitRoot)
    [void][System.IO.Directory]::CreateDirectory((Join-Path $gitRoot '.git'))
    $gitReject = Invoke-Preparation (Join-Path $gitRoot 'capture') $true
    Assert-Result $gitReject 1 'VH_MAP02_OWNER_PRIVATE_WORKSPACE_REJECTED created_or_acl_unverified=1'
    if ([System.IO.Directory]::Exists((Join-Path $gitRoot 'capture'))) {
        throw 'capture directory created inside fake Git checkout'
    }

    # A missing parent is rejected without producing any intermediate path.
    $noParent = Join-Path (Join-Path $base 'no-parent') 'capture'
    $miss = Invoke-Preparation $noParent $true
    Assert-Result $miss 1 'VH_MAP02_OWNER_PRIVATE_WORKSPACE_REJECTED created_or_acl_unverified=1'
    if ([System.IO.Directory]::Exists($noParent)) {
        throw 'bootstrap created absent intermediate directories'
    }
    $relative = Invoke-Preparation 'not-absolute-private-map02' $true
    Assert-Result $relative 1 'VH_MAP02_OWNER_PRIVATE_WORKSPACE_REJECTED created_or_acl_unverified=1'

    # An owner-private directory is deliberately made Everyone-readable
    # after creation. The *original* guard must still reject it.
    $acl = [System.IO.Directory]::GetAccessControl($prepared)
    $acl.AddAccessRule(
        ([System.Security.AccessControl.FileSystemAccessRule]::new(
            [System.Security.Principal.SecurityIdentifier]::new('S-1-1-0'),
            [System.Security.AccessControl.FileSystemRights]::ReadAndExecute,
            ([System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
             [System.Security.AccessControl.InheritanceFlags]::ObjectInherit),
            [System.Security.AccessControl.PropagationFlags]::None,
            [System.Security.AccessControl.AccessControlType]::Allow
        ))
    )
    [System.IO.Directory]::SetAccessControl($prepared, $acl)
    $denied = @( & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $guard -Directory $prepared )
    if ($LASTEXITCODE -eq 0 -or @($denied).Count -gt 0) {
        throw 'Everyone-readable target passed owner-only guard'
    }
    $global:LASTEXITCODE = 0
    Write-Output 'VH_MAP02_OWNER_PRIVATE_WORKSPACE_NTFS_FAKE_PASS dry=1 create=1 python_acl=1 existing_denied=1 git_denied=1 missing_parent_denied=1 relative_denied=1 everyone_denied=1 original_media=0'
} finally {
    Remove-Item -LiteralPath $base -Force -Recurse -ErrorAction SilentlyContinue
}
