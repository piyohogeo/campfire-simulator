param([string]$OutputDir="")
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
& $fixture $handler $helper $dump $metadata
$fixtureExit=$LASTEXITCODE
if(('0x{0:X8}' -f ([int32]$fixtureExit))-ne'0xC0000005'){throw "Phase V3T-J fixture did not exit with access violation: $fixtureExit"}
$python=Join-Path $root "_build\windows-x86_64\release\kit\python\python.exe"
$validation=Join-Path $OutputDir "dump_validation.json"
& $python (Join-Path $PSScriptRoot "analyze_phasev3tj_minidump.py") --dump $dump --metadata $metadata --output $validation
if($LASTEXITCODE-ne0){exit $LASTEXITCODE}
$result=Get-Content -Raw -Encoding UTF8 $validation|ConvertFrom-Json
if(-not$result.memory64_list_stream_present-or$result.collector.scope-ne"handler installed only in the isolated target process"-or$result.collector.machine_wide_configuration_changed){throw "Phase V3T-J targeted dump validation failed"}
Write-Host "Phase V3T-J targeted full-dump smoke PASS: $dump"
