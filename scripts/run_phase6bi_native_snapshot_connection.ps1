param(
    [ValidateRange(3, 7)]
    [int]$RunCount = 3,
    [ValidateRange(20, 300)]
    [int]$Cycles = 60,
    [ValidateRange(1, 100)]
    [int]$WarmupCycles = 10,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$kitPython = Join-Path $repositoryRoot "_build\windows-x86_64\release\kit\python\python.exe"
$nativeSource = Join-Path $repositoryRoot "native\phase6au"
$benchmark = Join-Path $PSScriptRoot "benchmark_native_snapshot_connection.py"
$analyzer = Join-Path $PSScriptRoot "analyze_native_snapshot_connection.py"
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"

if (-not (Test-Path -LiteralPath $kitPython)) { throw "Application is not built." }
if ($WarmupCycles -ge $Cycles) { throw "WarmupCycles must be smaller than Cycles." }
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
$developerPath = $environmentLines | Where-Object { $_ -cmatch '^PATH=' } | Select-Object -First 1
if (-not $developerPath) { throw "Visual Studio developer PATH was not returned." }
$env:PATH = $developerPath.Substring($developerPath.IndexOf("=") + 1)
if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) { throw "cl.exe is unavailable." }

if (-not $OutputDir) { $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6bi" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$buildDir = Join-Path $OutputDir "native-build"
$rawReport = Join-Path $OutputDir "native_snapshot_connection_raw.json"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
& cmake.exe -S $nativeSource -B $buildDir -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& cmake.exe --build $buildDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$nativeDll = Join-Path $buildDir "campfire_wood_native.dll"
if (-not (Test-Path -LiteralPath $nativeDll)) { throw "Native DLL was not produced." }
& $kitPython $benchmark --dll $nativeDll --logs 20 --cycles $Cycles --warmup-cycles $WarmupCycles --runs $RunCount --output $rawReport
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $kitPython $analyzer --raw $rawReport
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
