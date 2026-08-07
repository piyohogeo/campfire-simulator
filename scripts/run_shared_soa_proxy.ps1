param(
    [ValidateRange(1, 50)]
    [int]$LogCount = 20,
    [ValidateRange(100, 100000)]
    [int]$ScalarSamples = 2000,
    [ValidateRange(3, 200)]
    [int]$BoundarySamples = 25,
    [ValidateRange(1, 7)]
    [int]$RunCount = 3,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"
$nativeSource = Join-Path $repositoryRoot "native\phase6au"
$benchmark = Join-Path $PSScriptRoot "benchmark_shared_soa_proxy.py"
$analyzer = Join-Path $PSScriptRoot "analyze_shared_soa_proxy.py"
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"

if (-not (Test-Path -LiteralPath $kitPython)) { throw "Application is not built." }
if (-not (Test-Path -LiteralPath $vswhere)) { throw "Visual Studio locator was not found." }
$visualStudioRoot = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if ($LASTEXITCODE -ne 0 -or -not $visualStudioRoot) { throw "A Visual Studio C++ x64 toolchain was not found." }
$developerCommand = Join-Path $visualStudioRoot "Common7\Tools\VsDevCmd.bat"
$environmentLines = & $env:ComSpec /d /s /c "`"$developerCommand`" -no_logo -arch=x64 -host_arch=x64 >nul && set"
if ($LASTEXITCODE -ne 0) { throw "Visual Studio environment initialization failed." }
foreach ($line in $environmentLines) {
    $separator = $line.IndexOf("=")
    if ($separator -gt 0) {
        Set-Item -Path ("Env:" + $line.Substring(0, $separator)) -Value $line.Substring($separator + 1)
    }
}
$developerPath = $environmentLines | Where-Object { $_ -match '^PATH=' } | Select-Object -First 1
if (-not $developerPath) { throw "Visual Studio developer PATH was not returned." }
$env:PATH = $developerPath.Substring($developerPath.IndexOf("=") + 1)
if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) { throw "cl.exe is unavailable." }

if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\shared-soa-proxy" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$buildDir = Join-Path $OutputDir "native-build"
$rawReport = Join-Path $OutputDir "shared_soa_proxy_raw.json"
$report = Join-Path $OutputDir "shared_soa_proxy_report.json"
$svg = Join-Path $repositoryRoot "docs\devlog\assets\phase6\shared_soa_proxy_report.svg"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
& cmake.exe -S $nativeSource -B $buildDir -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& cmake.exe --build $buildDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$nativeDll = Join-Path $buildDir "campfire_wood_native.dll"
if (-not (Test-Path -LiteralPath $nativeDll)) { throw "Native DLL was not produced." }
& $kitPython $benchmark --dll $nativeDll --logs $LogCount --scalar-samples $ScalarSamples --boundary-samples $BoundarySamples --runs $RunCount --output $rawReport
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $kitPython $analyzer --raw $rawReport --report $report --svg $svg
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
