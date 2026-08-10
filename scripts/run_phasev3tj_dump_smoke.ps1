param([string]$OutputDir="",[int]$TimeoutSeconds=60)
$ErrorActionPreference="Stop"
$root=Split-Path -Parent $PSScriptRoot
if(-not$OutputDir){$OutputDir=Join-Path $root "artifacts\phasev3tj-dump-smoke"}
$OutputDir=[IO.Path]::GetFullPath($OutputDir)
if(Test-Path $OutputDir){throw "Phase V3T-J dump smoke refuses to reuse output: $OutputDir"}
New-Item -ItemType Directory -Path $OutputDir|Out-Null
$tools=Join-Path $root "artifacts\phasev3tj-tools"
& (Join-Path $PSScriptRoot "build_phasev3tj_dump_collector.ps1") -OutputDir $tools
if($LASTEXITCODE-ne0){exit $LASTEXITCODE}
$fixture=Join-Path $tools "build\Release\phasev3tj_crash_fixture.exe"
$handler=Join-Path $tools "build\Release\phasev3tj_crash_handler.dll"
$helper=Join-Path $tools "build\Release\phasev3tj_dump_helper.exe"
$dump=Join-Path $OutputDir "fixture_access_violation_full.dmp"
$metadata=Join-Path $OutputDir "collector.json"
$fixtureStarted=[DateTimeOffset]::UtcNow
$fixtureProcess=Start-Process -FilePath $fixture -ArgumentList @($handler,$helper,$dump,$metadata) -PassThru -WindowStyle Hidden
if(-not$fixtureProcess.WaitForExit($TimeoutSeconds*1000)){
    Stop-Process -Id $fixtureProcess.Id -Force
    throw "Phase V3T-J fixture did not terminate without interaction within $TimeoutSeconds seconds"
}
$fixtureProcess.WaitForExit();$fixtureProcess.Refresh()
$fixtureExit=$fixtureProcess.ExitCode
$fixtureElapsed=([DateTimeOffset]::UtcNow-$fixtureStarted).TotalSeconds
$automation=[ordered]@{
    schema="campfire.phasev3tj.fixture-automation.v1"
    fixture_process_only=$true
    hidden_process=$true
    timeout_seconds=$TimeoutSeconds
    elapsed_seconds=[math]::Round($fixtureElapsed,3)
    interactive_input_supplied=$false
    exit_code=$fixtureExit
    exit_hex=('0x{0:X8}' -f ([int32]$fixtureExit))
    process_error_mode="SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX"
    thread_error_mode="SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX"
    wer_flags="WER_FAULT_REPORTING_NO_UI"
    kit_process_modified=$false
    machine_wide_configuration_changed=$false
}
$utf8NoBom=New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText((Join-Path $OutputDir "automation.json"),($automation|ConvertTo-Json)+[Environment]::NewLine,$utf8NoBom)
if(('0x{0:X8}' -f ([int32]$fixtureExit))-ne'0xC0000005'){throw "Phase V3T-J fixture did not exit with access violation: $fixtureExit"}
$python=Join-Path $root "_build\windows-x86_64\release\kit\python\python.exe"
$validation=Join-Path $OutputDir "dump_validation.json"
& $python (Join-Path $PSScriptRoot "analyze_phasev3tj_minidump.py") --dump $dump --metadata $metadata --output $validation
if($LASTEXITCODE-ne0){exit $LASTEXITCODE}
$result=Get-Content -Raw -Encoding UTF8 $validation|ConvertFrom-Json
if(-not$result.memory64_list_stream_present-or$result.collector.scope-ne"handler installed only in the isolated target process"-or$result.collector.machine_wide_configuration_changed){throw "Phase V3T-J targeted dump validation failed"}
Write-Host "Phase V3T-J targeted full-dump smoke PASS: $dump"
Write-Host ("Phase V3T-J fixture NO_UI automation PASS: {0:N3} seconds" -f $fixtureElapsed)
