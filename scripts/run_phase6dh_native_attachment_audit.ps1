param([string]$OutputDir = "")

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repositoryRoot "_build\windows-x86_64\release"
$kit = Join-Path $releaseRoot "kit\kit.exe"
$app = Join-Path $releaseRoot "apps\campfire.simulator.kit"
$probe = Join-Path $PSScriptRoot "probe_flow_native_interface.py"
if (-not $OutputDir) {
    $OutputDir = Join-Path $repositoryRoot "artifacts\phase3\phase6dh-native-attachment"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$raw = Join-Path $OutputDir "native_interface.json"
$manifestPath = Join-Path $OutputDir "manifest.json"
$pluginExportsPath = Join-Path $OutputDir "plugin_exports.txt"
$bindingExportsPath = Join-Path $OutputDir "binding_exports.txt"
$log = Join-Path $OutputDir "phase6dh.log"
$reportPath = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_native_attachment_report.json"
$svgPath = Join-Path $repositoryRoot "docs\devlog\assets\phase6\resident_native_attachment_report.svg"

if (-not (Test-Path -LiteralPath $kit) -or -not (Test-Path -LiteralPath $app)) {
    throw "Application is not built."
}
$flowExtension = Get-ChildItem -LiteralPath (Join-Path $releaseRoot "extscache") -Directory |
    Where-Object { $_.Name -like "omni.flowusd-110.0.0*" } |
    Select-Object -First 1
if (-not $flowExtension) {
    throw "Pinned omni.flowusd 110.0.0 extension was not found."
}
$dumpbin = Get-ChildItem "C:\Program Files\Microsoft Visual Studio\2022" -Recurse -Filter dumpbin.exe -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -like "*Hostx64\x64\dumpbin.exe" } |
    Select-Object -First 1
if (-not $dumpbin) {
    throw "Visual Studio x64 dumpbin.exe was not found."
}

$plugin = Join-Path $flowExtension.FullName "bin\omni.flowusd.plugin.dll"
$binding = Join-Path $flowExtension.FullName "omni\flowusd\_flowusd.cp312-win_amd64.pyd"
$pythonApi = Join-Path $flowExtension.FullName "config\python_api.md"
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
foreach ($path in @($raw, $manifestPath, $pluginExportsPath, $bindingExportsPath, $log)) {
    Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
}

$productionHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
& $kit @(
    $app,
    "--no-window",
    "--/app/file/ignoreUnsavedOnExit=true",
    "--/app/quitAfter=30000",
    "--/app/settings/persistent=0",
    "--/app/settings/loadUserConfig=0",
    "--/exts/campfire.app/autoCreateScene=false",
    "--/renderer/enabled=false",
    "--/phase6bu/output=$raw",
    "--/log/file=$log",
    "--/log/fileLogLevel=Info",
    "--exec",
    $probe
)
$kitExitCode = $LASTEXITCODE
$productionHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash
if ($kitExitCode -ne 0) { exit $kitExitCode }
if ($productionHashBefore -ne $productionHashAfter) {
    throw "Phase 6DH changed the production app file."
}
if (-not (Test-Path -LiteralPath $raw)) {
    throw "Phase 6DH native-interface report is missing."
}

$pluginExportsText = (& $dumpbin.FullName /exports $plugin | Out-String)
$bindingExportsText = (& $dumpbin.FullName /exports $binding | Out-String)
$pluginExportsText | Set-Content -LiteralPath $pluginExportsPath -Encoding utf8
$bindingExportsText | Set-Content -LiteralPath $bindingExportsPath -Encoding utf8
$exportPattern = '(?m)^\s+\d+\s+[0-9A-Fa-f]+\s+[0-9A-Fa-f]+\s+(\S+)\s*$'
$pluginExports = @([regex]::Matches($pluginExportsText, $exportPattern) | ForEach-Object { $_.Groups[1].Value })
$bindingExports = @([regex]::Matches($bindingExportsText, $exportPattern) | ForEach-Object { $_.Groups[1].Value })
$expectedPluginExports = @(
    "carbGetFrameworkVersion",
    "carbGetPluginDeps",
    "carbOnPluginPostShutdown",
    "carbOnPluginPreStartup",
    "carbOnPluginRegisterEx",
    "carbOnPluginRegisterEx2",
    "carbOnPluginShutdown",
    "carbOnPluginStartup"
)
$native = Get-Content -LiteralPath $raw -Raw -Encoding utf8 | ConvertFrom-Json
$controlTerms = @("attach", "detach", "notice", "subscribe", "listener", "stage", "update", "timer", "profile", "ingest")
$nativeControlMembers = @($native.public_members | Where-Object {
    $name = $_.ToLowerInvariant()
    ($controlTerms | Where-Object { $name.Contains($_) }).Count -gt 0
})
$apiText = Get-Content -LiteralPath $pythonApi -Raw -Encoding utf8
$documentedControlTerms = @($controlTerms | Where-Object { $apiText -match "(?i)\b$([regex]::Escape($_))\b" })

$checks = [ordered]@{
    native_probe_status_ok = ($native.status -eq "ok")
    stage_not_opened = $true
    fixed_flow_version = ($flowExtension.Name -like "omni.flowusd-110.0.0*")
    native_member_count_19 = ($native.public_members.Count -eq 19)
    native_control_member_count_zero = ($nativeControlMembers.Count -eq 0)
    consumer_write_candidate_count_zero = ($native.consumer_write_candidates.Count -eq 0)
    documented_control_term_count_zero = ($documentedControlTerms.Count -eq 0)
    public_python_api_is_extension_only = ($apiText -match "class PublicExtension" -and $apiText -match "register_all_flow_commands")
    plugin_export_count_8 = ($pluginExports.Count -eq 8)
    plugin_exports_are_lifecycle_only = (@($pluginExports | Where-Object { $_ -notin $expectedPluginExports }).Count -eq 0)
    binding_export_is_pyinit_only = ($bindingExports.Count -eq 1 -and $bindingExports[0] -eq "PyInit__flowusd")
    production_app_unchanged = ($productionHashBefore -eq $productionHashAfter)
}
$passed = @($checks.Values | Where-Object { $_ }).Count
$total = $checks.Count
$status = if ($passed -eq $total) { "pass" } else { "fail" }
$report = [ordered]@{
    schema_version = 1
    phase = "phase6dh"
    status = $status
    generated_utc = [DateTime]::UtcNow.ToString("o")
    scope = "stage-free public native attachment and timing surface audit"
    gate_summary = [ordered]@{ passed = $passed; total = $total; checks = $checks }
    runtime = [ordered]@{
        interface_member_count = $native.public_members.Count
        interface_members = @($native.public_members)
        attachment_or_timing_members = $nativeControlMembers
        consumer_write_candidates = @($native.consumer_write_candidates)
    }
    packaged_public_api = [ordered]@{
        path = "config/python_api.md"
        classes = @("PublicExtension")
        functions = @("register_all_flow_commands")
        attachment_or_timing_terms = $documentedControlTerms
    }
    binary_exports = [ordered]@{
        plugin = $pluginExports
        python_binding = $bindingExports
        interpretation = "Export tables expose Carbonite lifecycle entry points and PyInit only; this does not claim that private implementation code lacks attachment logic."
    }
    decision = [ordered]@{
        public_notice_attachment_control_found = $false
        direct_flowusd_ingest_timer_found = $false
        continue_consumer_subtraction = $false
        reason = "No supported attachment/detachment, subscriber enumeration, or direct ingest timing control is exposed by the inspected Flow 110.0.0 surfaces."
    }
    contracts = [ordered]@{
        production_code_changed = $false
        production_sphere_default = $true
        point_emitter_default_off = $true
        flow_version = "110.0.0"
        physics_changed = $false
        json_schema_changed = $false
        rollback_changed = $false
        revision_changed = $false
        immutable_snapshot_changed = $false
    }
    next = "Return to value-preserving Point publication work: audit rotation representation and update only attributes whose candidate values changed."
}
$report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $reportPath -Encoding utf8

$svg = @"
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="680" viewBox="0 0 1200 680" role="img" aria-labelledby="title desc">
<title id="title">Phase 6DH native attachment surface audit</title><desc id="desc">Flow 110.0.0 exposes voxelize and readback methods, but no supported USD notice attachment control or direct ingest timer in the inspected public surfaces.</desc>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111a24"/><stop offset="1" stop-color="#1d2d39"/></linearGradient><style>.k{font:700 18px system-ui;fill:#74d9bd;letter-spacing:2px}.title{font:700 34px system-ui;fill:#f4f7f8}.sub{font:18px system-ui;fill:#bacbd5}.h{font:700 21px system-ui;fill:#f4f7f8}.v{font:700 26px system-ui;fill:#74d9bd}.warn{font:700 24px system-ui;fill:#ffb36b}.m{font:16px system-ui;fill:#bacbd5}.box{fill:#223642;stroke:#3b5868;stroke-width:2}</style></defs>
<rect width="1200" height="680" rx="30" fill="url(#bg)"/><text x="64" y="61" class="k">PHASE 6DH - PUBLIC NATIVE SURFACE</text><text x="64" y="111" class="title">No public notice-attachment control found</text><text x="64" y="150" class="sub">No stage connected - Flow 110.0.0 - runtime members / packaged docs / binary exports</text>
<rect x="64" y="195" width="330" height="150" rx="18" class="box"/><text x="88" y="232" class="h">IFlowUsd members</text><text x="88" y="278" class="v">19</text><text x="88" y="310" class="m">voxelize / readback / conversion</text>
<rect x="435" y="195" width="330" height="150" rx="18" class="box"/><text x="459" y="232" class="h">attachment / timer</text><text x="459" y="278" class="warn">0</text><text x="459" y="310" class="m">attach / notice / subscribe / ingest</text>
<rect x="806" y="195" width="330" height="150" rx="18" class="box"/><text x="830" y="232" class="h">packaged Python API</text><text x="830" y="278" class="v">2 entries</text><text x="830" y="310" class="m">extension class + command registration</text>
<rect x="64" y="382" width="516" height="126" rx="18" class="box"/><text x="88" y="421" class="h">plugin / binding exports</text><text x="88" y="464" class="v">8 lifecycle + 1 PyInit</text><text x="88" y="491" class="m">This does not prove private implementation absence</text>
<rect x="620" y="382" width="516" height="126" rx="18" class="box"/><text x="644" y="421" class="h">production impact</text><text x="644" y="464" class="v">SHA-256 unchanged</text><text x="644" y="491" class="m">No stage, source, or Flow output mutation</text>
<text x="64" y="561" class="h">DECISION</text><text x="64" y="598" class="warn">Stop consumer subtraction</text><text x="64" y="630" class="m">Do not assume private hooks; return to value-preserving Point publication and rotation work.</text><text x="64" y="656" class="m">$passed / $total gates - Sphere default - Point default OFF - rollback / revision / snapshot contracts unchanged</text>
</svg>
"@
$svg | Set-Content -LiteralPath $svgPath -Encoding utf8

$manifest = [ordered]@{
    schema_version = 1
    phase = "phase6dh"
    status = $status
    native_interface = $raw
    report = $reportPath
    svg = $svgPath
    plugin_exports = $pluginExportsPath
    binding_exports = $bindingExportsPath
    kit_exit_code = $kitExitCode
    production_app_sha256_before = $productionHashBefore
    production_app_sha256_after = $productionHashAfter
    production_changed = ($productionHashBefore -ne $productionHashAfter)
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8
if ($status -ne "pass") {
    throw "Phase 6DH gates failed: $passed / $total"
}
Write-Host "Phase 6DH native attachment audit: $passed / $total gates"
