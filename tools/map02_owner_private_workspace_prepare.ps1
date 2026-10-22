# Stage515: prepare an EMPTY owner-only NTFS directory for future local MAP02.
# Nothing is launched or copied. No path, SID or ACL text leaves the machine.
# Default is a read-only dry-run; creation requires the explicit -Create switch.
param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [switch]$Create
)
$ErrorActionPreference = 'Stop'
$created = $false
$full = $null
try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'Windows-only owner workspace'
    }
    if (-not [System.IO.Path]::IsPathRooted($Workspace)) {
        throw 'absolute workspace required'
    }
    $full = [System.IO.Path]::GetFullPath($Workspace)
    $parent = [System.IO.Directory]::GetParent($full)
    if ($null -eq $parent -or $null -eq $parent.Parent) {
        throw 'workspace may not be a drive root'
    }
    $leaf = [System.IO.Path]::GetFileName(
        $full.TrimEnd([char[]]@([char]92, [char]47)))
    if ([string]::IsNullOrWhiteSpace($leaf) -or
        $leaf.IndexOfAny([char[]]@([char]42, [char]63, [char]91, [char]93)) -ge 0) {
        throw 'unsafe output folder component'
    }
    if ([System.IO.File]::Exists($full) -or
        [System.IO.Directory]::Exists($full) -or
        (Test-Path -LiteralPath $full -ErrorAction SilentlyContinue)) {
        throw 'new workspace must not already exist'
    }
    # Check each ancestor without following a reparse point or placing captures
    # inside a Git checkout. The parent must exist; never create missing parents.
    for ($current = $parent; $null -ne $current; $current = $current.Parent) {
        if (-not $current.Exists) { throw 'existing parent required' }
        $item = Get-Item -LiteralPath $current.FullName -Force -ErrorAction Stop
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'no reparse-point ancestors'
        }
        $marker = Join-Path $current.FullName '.git'
        if (Test-Path -LiteralPath $marker -ErrorAction SilentlyContinue) {
            throw 'outside Git checkouts only'
        }
    }
    if (-not $Create) {
        Write-Output 'VH_MAP02_OWNER_PRIVATE_WORKSPACE_PREFLIGHT_OK created=0 original_media=0'
        exit 0
    }
    # The directory is empty until its protected DACL has been assigned and
    # independently verified. Never alter an existing folder or file.
    [void](New-Item -Path $parent.FullName -Name $leaf -ItemType Directory -ErrorAction Stop)
    $created = $true
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    if ($null -eq $user) { throw 'Windows user identity unavailable' }
    $acl = New-Object System.Security.AccessControl.DirectorySecurity
    $acl.SetOwner($user)
    $acl.SetAccessRuleProtection($true, $false)
    $acl.AddAccessRule(
        ([System.Security.AccessControl.FileSystemAccessRule]::new(
            $user, [System.Security.AccessControl.FileSystemRights]::FullControl,
            ([System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
             [System.Security.AccessControl.InheritanceFlags]::ObjectInherit),
            [System.Security.AccessControl.PropagationFlags]::None,
            [System.Security.AccessControl.AccessControlType]::Allow
        ))
    )
    [System.IO.Directory]::SetAccessControl($full, $acl)
    # This uses the SAME strict validator as Python and the BizHawk C# tool.
    $guard = Join-Path $PSScriptRoot 'map02_windows_private_output_acl.ps1'
    $signal = @( & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $guard -Directory $full )
    if ($LASTEXITCODE -ne 0 -or @($signal).Count -ne 1 -or
        [string]$signal -cne 'VH_MAP02_OWNER_PRIVATE_NTFS_ACL_OK') {
        throw 'owner-only DACL verification failed'
    }
    if (@(Get-ChildItem -LiteralPath $full -Force -ErrorAction Stop).Count -ne 0) {
        throw 'new private workspace must be empty'
    }
    $global:LASTEXITCODE = 0
    Write-Output 'VH_MAP02_OWNER_PRIVATE_WORKSPACE_READY created=1 acl=owner_only original_media=0'
    exit 0
} catch {
    # A failed attempt must never leave sensitive contents in a folder with
    # default inherited ACLs. Only remove a newly created EMPTY directory.
    if ($created -and $null -ne $full) {
        try {
            [System.IO.Directory]::Delete($full, $false)
        } catch {
            # Never recurse/delete files written by another process.
        }
    }
    Write-Output 'VH_MAP02_OWNER_PRIVATE_WORKSPACE_REJECTED created_or_acl_unverified=1'
    exit 1
}
