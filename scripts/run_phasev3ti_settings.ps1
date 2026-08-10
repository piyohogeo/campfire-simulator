param([string]$OutputDir="")
$ErrorActionPreference="Stop"
$root=Split-Path -Parent $PSScriptRoot
$release=Join-Path $root "_build\windows-x86_64\release"
$kit=Join-Path $release "kit\kit.exe"
$app=Join-Path $release "apps\campfire.simulator.kit"
$probe=Join-Path $PSScriptRoot "probe_phasev3ti_settings.py"
if(-not$OutputDir){$OutputDir=Join-Path $root "artifacts\phasev3ti-settings"}
$OutputDir=[IO.Path]::GetFullPath($OutputDir)
if(Test-Path $OutputDir){throw "Phase V3T-I settings inventory refuses to reuse output: $OutputDir"}
New-Item -ItemType Directory -Path $OutputDir|Out-Null
$output=Join-Path $OutputDir "settings_inventory.json"
$log=Join-Path $OutputDir "kit.log"
&$kit @(
    $app,
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=180000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/app/window/hideUi=false",
    "--/app/window/width=1280",
    "--/app/window/height=720",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/log/file=$log",
    "--/phasev3ti/settingsOutput=$output",
    "--exec",$probe
)
if($LASTEXITCODE-ne0){exit $LASTEXITCODE}
$stageId="IRenderSettings::getRenderSettings failed getting a stage-id"
if((Select-String -LiteralPath $log -SimpleMatch $stageId).Count){throw "Phase V3T-I settings inventory rejected by RTX stage-ID gate"}
$result=Get-Content -Raw -Encoding UTF8 $output|ConvertFrom-Json
if($result.status-ne"ok"){throw "Phase V3T-I settings inventory failed"}
Write-Host "Phase V3T-I settings inventory complete: $output"
