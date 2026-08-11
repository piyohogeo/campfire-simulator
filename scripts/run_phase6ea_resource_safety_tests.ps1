param(
    [int]$TimeoutSeconds = 120,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
. (Join-Path $PSScriptRoot "phase6ea_diagnostic_common.ps1")

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $repoRoot "artifacts\phase6ea-resource-safety-suite"
}
$output = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $output -Force | Out-Null
$python = (Get-Command python.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$stdoutPath = Join-Path $output "unittest.stdout.log"
$stderrPath = Join-Path $output "unittest.stderr.log"

$previousLocation = Get-Location
try {
    Set-Location $repoRoot
    $guard = Invoke-Phase6EaGuardedHelper `
        -FilePath $python `
        -ArgumentList @("-m", "unittest", "-v", "scripts.test_phase6ea_diagnostic_resource_safety") `
        -StdoutPath $stdoutPath `
        -StderrPath $stderrPath `
        -TimeoutSeconds $TimeoutSeconds `
        -PrivateBytesLimit 536870912
} finally {
    Set-Location $previousLocation
}

$success = (
    -not $guard.timed_out -and
    -not $guard.private_bytes_exceeded -and
    $guard.process_absent -and
    $guard.exit_code -eq 0
)
$report = [ordered]@{
    schema = "campfire.phase6ea.resource-safety-suite.v1"
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    success = $success
    timeout_seconds = $TimeoutSeconds
    python = $python
    guard = $guard
}
[IO.File]::WriteAllText(
    (Join-Path $output "suite_result.json"),
    ($report | ConvertTo-Json -Depth 8) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)
$report | ConvertTo-Json -Depth 8
if (-not $success) { exit 1 }
