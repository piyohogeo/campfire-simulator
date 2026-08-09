param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\native\release"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$nativeSource = Join-Path $repositoryRoot "native\phase6au"
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$visualStudioRoot = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if ($LASTEXITCODE -ne 0 -or -not $visualStudioRoot) {
    throw "Visual Studio C++ x64 toolchain was not found."
}
$developerCommand = Join-Path $visualStudioRoot "Common7\Tools\VsDevCmd.bat"
$environmentLines = & $env:ComSpec /d /s /c "`"$developerCommand`" -no_logo -arch=x64 -host_arch=x64 >nul && set"
if ($LASTEXITCODE -ne 0) {
    throw "Visual Studio developer environment initialization failed."
}
foreach ($line in $environmentLines) {
    $separator = $line.IndexOf("=")
    if ($separator -gt 0) {
        Set-Item -Path ("Env:" + $line.Substring(0, $separator)) -Value $line.Substring($separator + 1)
    }
}
$developerPath = $environmentLines | Where-Object { $_ -match '^PATH=' } | Select-Object -First 1
if (-not $developerPath) {
    throw "Visual Studio developer PATH was not returned."
}
$env:PATH = $developerPath.Substring($developerPath.IndexOf("=") + 1)
& cmake.exe -S $nativeSource -B $OutputDir -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& cmake.exe --build $OutputDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$nativeDll = Join-Path $OutputDir "campfire_wood_native.dll"
if (-not (Test-Path -LiteralPath $nativeDll)) {
    throw "Native wood library was not produced: $nativeDll"
}
Write-Host "Native wood library ready: $nativeDll"
