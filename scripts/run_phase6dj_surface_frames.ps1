param(
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$legacySource = Join-Path $repositoryRoot "native\phase6au"
$frameSource = Join-Path $repositoryRoot "native\phase6di"
$probe = Join-Path $PSScriptRoot "probe_phase6dj_surface_frames.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6dj_surface_frames.py"
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"

$probePython = (Get-Command python.exe -ErrorAction Stop).Source
& $probePython -c "import numpy"
if ($LASTEXITCODE -ne 0) {
    throw "The isolated frame probe requires an existing Python environment with NumPy."
}
if (-not (Test-Path -LiteralPath $vswhere)) {
    throw "Visual Studio locator was not found: $vswhere"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase6\phase6dj"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$legacyBuild = Join-Path $OutputDir "legacy-build"
$frameBuild = Join-Path $OutputDir "frame-build"
$rawReport = Join-Path $OutputDir "resident_surface_frame_raw.json"

$productionFiles = Get-ChildItem -LiteralPath $legacySource -File | Sort-Object FullName
$productionHashesBefore = @($productionFiles | ForEach-Object {
    "{0}:{1}" -f $_.Name, (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
})

$visualStudioRoot = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if ($LASTEXITCODE -ne 0 -or -not $visualStudioRoot) {
    throw "A Visual Studio C++ x64 toolchain was not found."
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
$developerPath = $environmentLines | Where-Object { $_ -cmatch '^PATH=' } | Select-Object -First 1
if (-not $developerPath) {
    throw "Visual Studio developer PATH was not returned."
}
$env:PATH = $developerPath.Substring($developerPath.IndexOf("=") + 1)
if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
    throw "Visual Studio developer environment did not expose cl.exe."
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
& cmake.exe -S $legacySource -B $legacyBuild -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& cmake.exe --build $legacyBuild
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& cmake.exe -S $frameSource -B $frameBuild -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& cmake.exe --build $frameBuild
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$legacyDll = Join-Path $legacyBuild "campfire_wood_native.dll"
$frameDll = Join-Path $frameBuild "campfire_surface_frame_spike.dll"
if (-not (Test-Path -LiteralPath $legacyDll)) {
    throw "Legacy native DLL was not produced: $legacyDll"
}
if (-not (Test-Path -LiteralPath $frameDll)) {
    throw "Frame spike DLL was not produced: $frameDll"
}

$productionHashesAfter = @($productionFiles | ForEach-Object {
    "{0}:{1}" -f $_.Name, (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
})
$productionUnchanged = ($productionHashesBefore -join "|") -ceq ($productionHashesAfter -join "|")
if (-not $productionUnchanged) {
    throw "Production Phase 6AU native sources changed during the isolated spike."
}

& $probePython $probe --legacy-dll $legacyDll --frame-dll $frameDll --output $rawReport --production-source-unchanged true
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $probePython $analyzer --raw $rawReport
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
