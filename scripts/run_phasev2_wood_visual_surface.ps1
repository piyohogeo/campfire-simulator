param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$nativeSource = Join-Path $repositoryRoot "native\phase6au"
$probe = Join-Path $PSScriptRoot "probe_phasev2_wood_visual_surface.py"
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phasev2" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$buildDir = Join-Path $OutputDir "native-build"
$report = Join-Path $OutputDir "wood_visual_surface_report.json"

$visualStudioRoot = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if ($LASTEXITCODE -ne 0 -or -not $visualStudioRoot) { throw "A Visual Studio C++ x64 toolchain was not found." }
$developerCommand = Join-Path $visualStudioRoot "Common7\Tools\VsDevCmd.bat"
$environmentLines = & $env:ComSpec /d /s /c "`"$developerCommand`" -no_logo -arch=x64 -host_arch=x64 >nul && set"
if ($LASTEXITCODE -ne 0) { throw "Visual Studio environment initialization failed." }
foreach ($line in $environmentLines) {
    $separator = $line.IndexOf("=")
    if ($separator -gt 0) { Set-Item -Path ("Env:" + $line.Substring(0, $separator)) -Value $line.Substring($separator + 1) }
}
if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) { throw "Visual Studio environment did not expose cl.exe." }
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
& cmake.exe -S $nativeSource -B $buildDir -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& cmake.exe --build $buildDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$nativeDll = Join-Path $buildDir "campfire_wood_native.dll"
& $kit @(
    $app,
    "--no-window",
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=300",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/phasev2/output=$report",
    "--/phasev2/nativeLibrary=$nativeDll",
    "--exec",
    $probe
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($result.status -ne "ok") { throw "Wood visual V2 probe failed: $report" }
Write-Host ("Wood visual V2: {0}/{1} gates, 7200 total p95={2:N4} ms" -f @($result.gates.PSObject.Properties | Where-Object Value).Count, @($result.gates.PSObject.Properties).Count, $result.cases[1].timing.total_ms.p95_ms)
