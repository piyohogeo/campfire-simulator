param(
    [Parameter(Mandatory = $true)][int]$ProcessId,
    [Parameter(Mandatory = $true)][string]$ExpectedExecutable,
    [Parameter(Mandatory = $true)][datetime]$ExpectedStartTimeUtc,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [Parameter(Mandatory = $true)][string]$LifecyclePath,
    [Parameter(Mandatory = $true)][string]$LogPath,
    [Parameter(Mandatory = $true)][string]$MarkerPath,
    [int]$DebuggerTimeoutSeconds = 120,
    [ValidateRange(0, 60000)][int]$FixtureDelayMilliseconds = 0,
    [ValidateRange(0, 60000)][int]$FixtureCdbSleepMilliseconds = 0
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
. (Join-Path $PSScriptRoot "kit_shutdown_policy.ps1")

Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "diagnostic_child_process_started"
try {
    if ($FixtureDelayMilliseconds -gt 0) {
        Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "fixture_delay_started" -Details @{ milliseconds = $FixtureDelayMilliseconds }
        Start-Sleep -Milliseconds $FixtureDelayMilliseconds
    }
    $null = Invoke-CampfireLightweightNgxDiagnosticCore `
        -ProcessId $ProcessId `
        -ExpectedExecutable $ExpectedExecutable `
        -ExpectedStartTimeUtc $ExpectedStartTimeUtc `
        -OutputDir $OutputDir `
        -LifecyclePath $LifecyclePath `
        -LogPath $LogPath `
        -MarkerPath $MarkerPath `
        -DebuggerTimeoutSeconds $DebuggerTimeoutSeconds `
        -FixtureCdbSleepMilliseconds $FixtureCdbSleepMilliseconds
    Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "diagnostic_child_process_normal_exit"
    exit 0
} catch {
    Write-CampfireDiagnosticMarker -Path $MarkerPath -Marker "diagnostic_child_process_failed" -Details @{ error_type = $_.Exception.GetType().FullName; message = $_.Exception.Message }
    throw
}
