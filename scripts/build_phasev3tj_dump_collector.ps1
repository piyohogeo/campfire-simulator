param([string]$OutputDir="")
$ErrorActionPreference="Stop"
$root=Split-Path -Parent $PSScriptRoot
if(-not$OutputDir){$OutputDir=Join-Path $root "artifacts\phasev3tj-tools"}
$OutputDir=[IO.Path]::GetFullPath($OutputDir)
$source=Join-Path $PSScriptRoot "phasev3tj_dump_collector"
$build=Join-Path $OutputDir "build\Release"
New-Item -ItemType Directory -Path $build -Force|Out-Null
$vswhere="C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
if(-not(Test-Path $vswhere)){throw "Visual Studio locator is unavailable"}
$installation=&$vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(-not$installation){throw "MSVC x64 tools are unavailable"}
$vsdev=Join-Path $installation "Common7\Tools\VsDevCmd.bat"
$collector=Join-Path $build "phasev3tj_dump_collector.exe"
$fixture=Join-Path $build "phasev3tj_crash_fixture.exe"
$handler=Join-Path $build "phasev3tj_crash_handler.dll"
$helper=Join-Path $build "phasev3tj_dump_helper.exe"
$collectorSource=Join-Path $source "dump_collector.cpp"
$fixtureSource=Join-Path $source "crash_fixture.cpp"
$handlerSource=Join-Path $source "crash_handler.cpp"
$helperSource=Join-Path $source "dump_helper.cpp"
$collectorObject=Join-Path $build "dump_collector.obj"
$fixtureObject=Join-Path $build "crash_fixture.obj"
$handlerObject=Join-Path $build "crash_handler.obj"
$helperObject=Join-Path $build "dump_helper.obj"
$collectorCommand="call `"$vsdev`" -no_logo -arch=x64 && cl.exe /nologo /std:c++17 /EHsc /O2 /DUNICODE /D_UNICODE /Fo:`"$collectorObject`" /Fe:`"$collector`" `"$collectorSource`" /link dbghelp.lib"
& cmd.exe /d /s /c $collectorCommand
if($LASTEXITCODE-ne0){exit $LASTEXITCODE}
$fixturePdb=Join-Path $build "phasev3tj_crash_fixture_compile.pdb"
$fixtureCommand="call `"$vsdev`" -no_logo -arch=x64 && cl.exe /nologo /std:c++17 /EHsc /Od /Zi /Fd:`"$fixturePdb`" /Fo:`"$fixtureObject`" /Fe:`"$fixture`" `"$fixtureSource`""
& cmd.exe /d /s /c $fixtureCommand
if($LASTEXITCODE-ne0){exit $LASTEXITCODE}
$handlerCommand="call `"$vsdev`" -no_logo -arch=x64 && cl.exe /nologo /std:c++17 /EHsc /O2 /LD /DUNICODE /D_UNICODE /Fo:`"$handlerObject`" /Fe:`"$handler`" `"$handlerSource`""
& cmd.exe /d /s /c $handlerCommand
if($LASTEXITCODE-ne0){exit $LASTEXITCODE}
$helperCommand="call `"$vsdev`" -no_logo -arch=x64 && cl.exe /nologo /std:c++17 /EHsc /O2 /DUNICODE /D_UNICODE /Fo:`"$helperObject`" /Fe:`"$helper`" `"$helperSource`" /link dbghelp.lib"
& cmd.exe /d /s /c $helperCommand
if($LASTEXITCODE-ne0){exit $LASTEXITCODE}
if(-not(Test-Path $collector)-or-not(Test-Path $fixture)-or-not(Test-Path $handler)-or-not(Test-Path $helper)){throw "Phase V3T-J dump tools were not produced"}
Write-Host "Phase V3T-J dump tools: handler=$handler helper=$helper rejected_debugger=$collector"
