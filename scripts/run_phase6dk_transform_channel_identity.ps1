param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$legacySource = Join-Path $repositoryRoot "native\phase6au"
$frameSource = Join-Path $repositoryRoot "native\phase6di"
$probe = Join-Path $PSScriptRoot "probe_phase6dk_transform_channel_identity.py"
$analyzer = Join-Path $PSScriptRoot "analyze_phase6dk_transform_channel_identity.py"
$probePython = (Get-Command python.exe -ErrorAction Stop).Source
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built."
}
if (-not (Test-Path -LiteralPath $vswhere)) {
    throw "Visual Studio locator was not found: $vswhere"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase6\phase6dk"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$legacyBuild = Join-Path $OutputDir "legacy-build"
$frameBuild = Join-Path $OutputDir "frame-build"
$rawReport = Join-Path $OutputDir "resident_transform_channel_raw.json"
$log = Join-Path $OutputDir "phase6dk.log"

$productionFiles = Get-ChildItem -LiteralPath $legacySource -File | Sort-Object FullName
$productionHashesBefore = @($productionFiles | ForEach-Object {
    "{0}:{1}" -f $_.Name, (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
})
$productionAppHashBefore = (Get-FileHash -LiteralPath $app -Algorithm SHA256).Hash

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

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
Remove-Item -LiteralPath $rawReport, $log -Force -ErrorAction SilentlyContinue
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
if (-not (Test-Path -LiteralPath $legacyDll) -or -not (Test-Path -LiteralPath $frameDll)) {
    throw "Phase 6DK native DLL build is incomplete."
}

& $kit @(
    $app,
    "--no-window",
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=30000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/renderer/enabled=false",
    "--/phase6dk/output=$rawReport",
    "--/phase6dk/legacyDll=$legacyDll",
    "--/phase6dk/frameDll=$frameDll",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info",
    "--exec",
    $probe
)
$kitExitCode = $LASTEXITCODE
if ($kitExitCode -ne 0) { exit $kitExitCode }
if (-not (Test-Path -LiteralPath $rawReport)) {
    throw "Phase 6DK raw report is missing."
}

$productionHashesAfter = @($productionFiles | ForEach-Object {
    "{0}:{1}" -f $_.Name, (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
})
$productionAppHashAfter = (Get-FileHash -LiteralPath $app -Algorithm SHA256).Hash
$nativeUnchanged = ($productionHashesBefore -join "|") -ceq ($productionHashesAfter -join "|")
$appUnchanged = $productionAppHashBefore -eq $productionAppHashAfter
$nativeUnchangedText = $nativeUnchanged.ToString().ToLowerInvariant()
$appUnchangedText = $appUnchanged.ToString().ToLowerInvariant()

& $probePython $analyzer --raw $rawReport --production-app-unchanged $appUnchangedText --production-native-source-unchanged $nativeUnchangedText
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
