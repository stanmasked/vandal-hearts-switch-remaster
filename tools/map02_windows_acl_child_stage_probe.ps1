# Stage514 diagnostic; ONLY used by synthetic Windows CI with fake files.
# Mirrors checks of the strict production ACL guard but exposes just an exit
# category (not path, principal, SID, ACL, stack trace, or Windows error).
param([Parameter(Mandatory=$true)][string]$Directory)
$ErrorActionPreference = 'Stop'
$stage = 1
try {
    if (-not [System.IO.Path]::IsPathRooted($Directory)) { exit 11 }
    $stage = 2
    $item = Get-Item -LiteralPath $Directory -Force -ErrorAction Stop
    if (-not $item.PSIsContainer) { exit 12 }
    $stage = 3
    $acl = [System.IO.Directory]::GetAccessControl($item.FullName)
    $stage = 4
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    if ($null -eq $user) { exit 13 }
    $stage = 5
    $owner = $acl.GetOwner([System.Security.Principal.SecurityIdentifier])
    if ($null -eq $owner -or $owner.Value -cne $user.Value) { exit 14 }
    $trusted = @($user.Value, 'S-1-5-18', 'S-1-5-32-544')
    $ownerCanWrite = $false
    $stage = 6
    $entries = $acl.GetAccessRules(
        $true, $true, [System.Security.Principal.SecurityIdentifier])
    $stage = 7
    foreach ($rule in $entries) {
        if ($rule.AccessControlType -ne
            [System.Security.AccessControl.AccessControlType]::Allow) { continue }
        if ($trusted -cnotcontains $rule.IdentityReference.Value) { exit 15 }
        if ($rule.IdentityReference.Value -ceq $user.Value) {
            $needed = [System.Security.AccessControl.FileSystemRights]::WriteData
            if (($rule.FileSystemRights -band $needed) -eq $needed) {
                $ownerCanWrite = $true
            }
        }
    }
    if (-not $ownerCanWrite) { exit 16 }
    exit 0
} catch {
    # Redacted stage only, never OS error text or owner identifier.
    exit (20 + $stage)
}
