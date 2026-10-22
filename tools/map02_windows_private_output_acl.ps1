# Owner-local NTFS ACL audit for a directory holding private PS1 captures.
# Refuses access by ANY positive-allow trustee other than current user,
# BUILTIN Administrators, or LOCAL SYSTEM, including inherited grants.
# Never prints identities, folder paths, ACLs, secrets, or content.
param([Parameter(Mandatory=$true)][string]$Directory)
$ErrorActionPreference = 'Stop'
try {
    if (-not [System.IO.Path]::IsPathRooted($Directory)) { throw 'absolute path required' }
    $item = Get-Item -LiteralPath $Directory -Force -ErrorAction Stop
    if (-not $item.PSIsContainer) { throw 'directory required' }
    $acl = [System.IO.Directory]::GetAccessControl($item.FullName)
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    if ($null -eq $user) { throw 'identity unavailable' }
    $owner = $acl.GetOwner([System.Security.Principal.SecurityIdentifier])
    if ($null -eq $owner -or $owner.Value -cne $user.Value) {
        throw 'directory must be owned by the current user'
    }
    $trusted = @($user.Value, 'S-1-5-18', 'S-1-5-32-544')
    $ownerCanWrite = $false
    $entries = $acl.GetAccessRules($true, $true,
        [System.Security.Principal.SecurityIdentifier])
    foreach ($rule in $entries) {
        if ($rule.AccessControlType -ne
            [System.Security.AccessControl.AccessControlType]::Allow) {
            continue
        }
        $sid = $rule.IdentityReference.Value
        if ($trusted -cnotcontains $sid) {
            throw 'other principals must not be permitted by the directory ACL'
        }
        if ($sid -ceq $user.Value) {
            $needed = [System.Security.AccessControl.FileSystemRights]::WriteData
            if (($rule.FileSystemRights -band $needed) -eq $needed) {
                $ownerCanWrite = $true
            }
        }
    }
    if (-not $ownerCanWrite) { throw 'current user requires direct write permission' }
    Write-Output 'VH_MAP02_OWNER_PRIVATE_NTFS_ACL_OK'
    exit 0
} catch {
    # No paths, NTFS SIDs, ACL or localized exception messages in output.
    exit 1
}
