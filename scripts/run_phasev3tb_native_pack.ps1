param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$nativeSource = Join-Path $repositoryRoot "native\phase6au"
$probeScript = Join-Path $PSScriptRoot "probe_phasev3tb_native_pack.py"
if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phasev3tb" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$buildDir = Join-Path $OutputDir "native-build"
$probe = Join-Path $OutputDir "native_beauty_probe.json"
$captures = Join-Path $OutputDir "captures"
New-Item -ItemType Directory -Path $captures -Force | Out-Null

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$visualStudioRoot = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if ($LASTEXITCODE -ne 0 -or -not $visualStudioRoot) { throw "Visual Studio C++ x64 toolchain was not found." }
$developerCommand = Join-Path $visualStudioRoot "Common7\Tools\VsDevCmd.bat"
$environmentLines = & $env:ComSpec /d /s /c "`"$developerCommand`" -no_logo -arch=x64 -host_arch=x64 >nul && set"
if ($LASTEXITCODE -ne 0) { throw "Visual Studio developer environment initialization failed." }
foreach ($line in $environmentLines) {
    $separator = $line.IndexOf("=")
    if ($separator -gt 0) {
        Set-Item -Path ("Env:" + $line.Substring(0, $separator)) -Value $line.Substring($separator + 1)
    }
}
$developerPath = $environmentLines | Where-Object { $_ -match '^PATH=' } | Select-Object -First 1
if (-not $developerPath) { throw "Visual Studio developer PATH was not returned." }
$env:PATH = $developerPath.Substring($developerPath.IndexOf("=") + 1)
& cmake.exe -S $nativeSource -B $buildDir -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& cmake.exe --build $buildDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$nativeDll = Join-Path $buildDir "campfire_wood_native.dll"

& $kit @(
    $app,
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=10000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/app/viewport/defaults/fillViewport=false",
    "--/phasev3tb/output=$probe",
    "--/phasev3tb/captureDir=$captures",
    "--/phasev3tb/nativeLibrary=$nativeDll",
    "--exec",
    $probeScript
)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$result = Get-Content -LiteralPath $probe -Raw | ConvertFrom-Json
if ($result.status -ne "qualified") { throw "Phase V3T-B native pack did not qualify: $probe" }
Write-Host ("Phase V3T-B: status={0}, gates={1}/{2}, native p95={3:N4} ms, publication p95={4:N4} ms" -f $result.status, @($result.gates.psobject.Properties | Where-Object { $_.Value }).Count, @($result.gates.psobject.Properties).Count, $result.reference_comparison.twenty_logs.native_pack.p95_ms, $result.change_aware.changing_timing.total_ms.p95_ms)
