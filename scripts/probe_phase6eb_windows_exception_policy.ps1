param(
    [Parameter(Mandatory = $true)][string]$LogPath,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [switch]$HoldLogExclusively
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")
$stream = $null
try {
    if ($HoldLogExclusively) {
        $stream = [IO.File]::Open([IO.Path]::GetFullPath($LogPath), [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    }
    $evidence = Get-CampfireWindowsExceptionEvidence -Path $LogPath
    [IO.File]::WriteAllText(
        [IO.Path]::GetFullPath($OutputPath),
        ($evidence | ConvertTo-Json -Depth 8) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false)
    )
} finally {
    if ($null -ne $stream) { $stream.Dispose() }
}
