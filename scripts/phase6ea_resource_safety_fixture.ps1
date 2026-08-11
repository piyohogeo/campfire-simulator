param(
    [Parameter(Mandatory = $true)][ValidateSet("wct_timeout", "lock_hold", "lock_once", "dump_timeout")][string]$Mode,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [string]$CanonicalCapturePath = "",
    [string]$SourcePath = "",
    [string]$FinalDumpPath = "",
    [int]$HoldSeconds = 5
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
. (Join-Path $PSScriptRoot "phase6ea_diagnostic_common.ps1")
$output = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $output -Force | Out-Null
$reportPath = Join-Path $output "fixture_result.json"

if ($Mode -eq "wct_timeout") {
    $python = (Get-Command python.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $helper = Join-Path $PSScriptRoot "phase6ea_wct_helper.py"
    $result = Invoke-Phase6EaGuardedHelper -FilePath $python -ArgumentList @($helper,"--output-path",(Join-Path $output "never.json"),"--object-name-boundary-fixture","--fixture-hang-seconds","300") -StdoutPath (Join-Path $output "helper.stdout.log") -StderrPath (Join-Path $output "helper.stderr.log") -TimeoutSeconds 1 -PrivateBytesLimit 268435456
    [IO.File]::WriteAllText($reportPath, ($result | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    exit 0
}

if ($Mode -in @("lock_hold", "lock_once")) {
    $lock = Enter-Phase6EaCaptureLock -CanonicalOutputPath $CanonicalCapturePath -TargetProcessId 42 -DumpPath "fixture.dmp"
    try {
        [IO.File]::WriteAllText((Join-Path $output "lock_acquired.txt"), "ok", [Text.UTF8Encoding]::new($false))
        if ($Mode -eq "lock_hold") { Start-Sleep -Seconds $HoldSeconds }
    } finally { Exit-Phase6EaCaptureLock -LockPath $lock }
    exit 0
}

if ($Mode -eq "dump_timeout") {
    $helper = Join-Path $PSScriptRoot "phase6ea_dump_helper.ps1"
    $result = Invoke-Phase6EaDumpHelper -HelperScript $helper -HelperArguments @("-FixtureSourcePath",[IO.Path]::GetFullPath($SourcePath),"-FixtureHangAfterBytes","4") -FinalDumpPath $FinalDumpPath -TimeoutSeconds 1 -PrivateBytesLimit 268435456 -MaximumDumpBytes 1073741824 -StdoutPath (Join-Path $output "dump.stdout.log") -StderrPath (Join-Path $output "dump.stderr.log")
    [IO.File]::WriteAllText($reportPath, ($result | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    exit 0
}
